import re
from datetime import timedelta
from urllib.parse import quote

from odoo import models, fields, api
from odoo.exceptions import UserError

MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']


class ServiceOrderGestion(models.Model):
    _inherit = 'service.order'

    wa_notified = fields.Char(string='Último estado avisado', copy=False)
    wa_survey_sent = fields.Boolean(string='Encuesta enviada', copy=False)
    quote_signature = fields.Image(string='Firma del presupuesto', copy=False, attachment=True,
                                   max_width=600, max_height=300)
    quote_signed_date = fields.Datetime(string='Presupuesto firmado el', copy=False, readonly=True)

    # ------------------------------------------------------------------ notificaciones en vivo
    def _gestion_notify(self, title, message, kind='info'):
        managers = self.env.ref('taller.group_taller_manager').sudo().user_ids
        for order in self:
            payload = {'id': order.id, 'title': title, 'message': message % order.name, 'kind': kind}
            for user in managers:
                self.env['bus.bus']._sendone(user.partner_id, 'taller_event', payload)

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        try:
            orders._gestion_notify('Nueva orden', 'Ingresó la orden %s')
        except Exception:
            pass
        return orders

    def action_approve_quote(self):
        res = super().action_approve_quote()
        try:
            self._gestion_notify('Presupuesto aprobado', 'El cliente aprobó %s', 'success')
        except Exception:
            pass
        return res

    def action_reject_quote(self):
        res = super().action_reject_quote()
        try:
            self._gestion_notify('Presupuesto rechazado', 'El cliente rechazó %s', 'warning')
        except Exception:
            pass
        return res

    # ------------------------------------------------------------------ panel de gestión
    @api.model
    def panel_data(self):
        is_manager = self.env.user.has_group('taller.group_taller_manager')
        today = fields.Date.context_today(self)
        params = self.env['ir.config_parameter'].sudo()
        symbol = self.env.company.currency_id.symbol or ''
        Payment = self.env['service.payment']
        Sale = self.env['taller.sale']

        # ---- alertas (para todos)
        alerts = []
        stuck = self.search([('status', 'in', ('diagnosing', 'repairing')),
                             ('write_date', '<', fields.Datetime.now() - timedelta(days=5))],
                            order='write_date asc', limit=8)
        for o in stuck:
            days = (fields.Datetime.now() - o.write_date).days
            alerts.append({'kind': 'stuck', 'icon': 'fa-hourglass-half', 'id': o.id,
                           'text': '%s sin movimiento hace %s días' % (o.name, days),
                           'sub': o.partner_id.name or o.customer_name or ''})
        for o in self.search([('status', '=', 'done'), ('date_ready', '<=', today - timedelta(days=7))],
                             order='date_ready asc', limit=5):
            alerts.append({'kind': 'abandoned', 'icon': 'fa-archive', 'id': o.id,
                           'text': '%s lista hace %s días y sin retirar' % (o.name, (today - o.date_ready).days),
                           'sub': o.partner_id.name or o.customer_name or ''})
        for o in self.search([('rating', 'in', ('1', '2')), ('rating_date', '>=', today - timedelta(days=14))], limit=5):
            alerts.append({'kind': 'rating', 'icon': 'fa-frown-o', 'id': o.id,
                           'text': 'Valoración baja en %s (%s/5)' % (o.name, o.rating),
                           'sub': o.rating_comment or ''})
        for part in self.env['service.part'].search([]).filtered(lambda p: p.min_stock and p.stock <= p.min_stock)[:6]:
            alerts.append({'kind': 'stock', 'icon': 'fa-cubes', 'id': 0,
                           'text': 'Stock bajo: %s (%g, mínimo %g)' % (part.display_name, part.stock, part.min_stock),
                           'sub': ''})
        # clientes que no volvieron: última orden entregada hace 120-365 días
        old = self.search([('status', '=', 'delivered'), ('date_finished', '<=', today - timedelta(days=120)),
                           ('date_finished', '>=', today - timedelta(days=365)), ('partner_id', '!=', False)],
                          order='date_finished desc', limit=200)
        recent_partners = set(self.search([('date_received', '>', today - timedelta(days=120)),
                                           ('partner_id', 'in', old.mapped('partner_id').ids)]).mapped('partner_id').ids)
        seen = set()
        for o in old:
            p = o.partner_id
            if p.id in recent_partners or p.id in seen:
                continue
            seen.add(p.id)
            alerts.append({'kind': 'lapsed', 'icon': 'fa-user-times', 'id': o.id,
                           'text': '%s no vuelve desde %s' % (p.name, o.date_finished.strftime('%d/%m/%Y')),
                           'sub': 'Buen momento para escribirle'})
            if len(seen) >= 5:
                break

        data = {'is_manager': is_manager, 'symbol': symbol, 'alerts': alerts}
        if not is_manager:
            return data

        # ---- ingresos últimos 6 meses
        months = []
        first = today.replace(day=1)
        for i in range(5, -1, -1):
            y, m = first.year, first.month - i
            while m < 1:
                m += 12
                y -= 1
            start = first.replace(year=y, month=m)
            nm, ny = (m + 1, y) if m < 12 else (1, y + 1)
            end = first.replace(year=ny, month=nm)
            pay = Payment._read_group([('date', '>=', start), ('date', '<', end)], aggregates=['amount:sum'])
            sale = Sale._read_group([('date', '>=', start), ('date', '<', end), ('state', '=', 'done')],
                                    aggregates=['total:sum'])
            received = self.search_count([('date_received', '>=', start), ('date_received', '<', end)])
            months.append({'label': MESES[m - 1], 'income': (pay[0][0] if pay else 0) + (sale[0][0] if sale else 0),
                           'orders': received})

        # ---- por técnico (mes actual) y tiempos
        month_start = first
        delivered = self.search([('status', '=', 'delivered'), ('date_finished', '>=', month_start)])
        by_tech = {}
        for o in delivered:
            name = o.user_id.name or 'Sin asignar'
            row = by_tech.setdefault(name, {'name': name, 'count': 0, 'amount': 0.0})
            row['count'] += 1
            row['amount'] += o.total
        techs = sorted(by_tech.values(), key=lambda r: -r['count'])
        days = [(o.date_finished - o.date_received).days for o in delivered if o.date_finished and o.date_received]
        avg_days = round(sum(days) / len(days), 1) if days else 0

        quotes = self.search([('quote_date', '>=', today - timedelta(days=90))])
        approved = quotes.filtered(lambda o: o.approved_date)
        rate = round(100.0 * len(approved) / len(quotes)) if quotes else 0
        ratings = self.search([('rating_value', '>', 0), ('rating_date', '>=', today - timedelta(days=90))])
        avg_rating = round(sum(ratings.mapped('rating_value')) / len(ratings), 1) if ratings else 0

        # ---- meta mensual
        goal = float(params.get_param('taller.monthly_goal', 0) or 0)
        current_income = months[-1]['income']
        data.update({
            'months': months, 'techs': techs, 'avg_days': avg_days, 'approval_rate': rate,
            'avg_rating': avg_rating, 'ratings_count': len(ratings),
            'goal': goal, 'income_month': current_income,
            'goal_pct': min(100, round(100.0 * current_income / goal)) if goal else 0,
        })
        return data

    @api.model
    def panel_set_goal(self, amount):
        if not self.env.user.has_group('taller.group_taller_manager'):
            raise UserError('Solo para responsables.')
        value = float(amount or 0)
        if value < 0:
            raise UserError('La meta no puede ser negativa.')
        self.env['ir.config_parameter'].sudo().set_param('taller.monthly_goal', str(value))
        return True

    # ------------------------------------------------------------------ mensajes pendientes
    def _wa_url(self, text):
        number = self._whatsapp_number(self.partner_id.phone)
        return ('https://wa.me/%s?text=%s' % (number, quote(text))) if number else ''

    @api.model
    def msgs_list(self):
        today = fields.Date.context_today(self)
        rows = []

        def add(order, kind, label, text):
            rows.append({
                'id': order.id, 'name': order.name, 'kind': kind, 'label': label,
                'customer': order.partner_id.name or order.customer_name or '',
                'device': ' '.join(filter(None, [order.device_brand, order.device_model])) or 'equipo',
                'phone': order.partner_id.phone or '', 'wa_url': order._wa_url(text),
            })

        company = self.env.company.name
        recent = fields.Datetime.now() - timedelta(days=14)
        for o in self.search([('status', 'in', ('draft', 'quote', 'done')), ('write_date', '>=', recent)],
                             order='id desc', limit=200):
            if o.wa_notified == o.status:
                continue
            o._ensure_token()
            name = o.partner_id.name or o.customer_name or ''
            device = ' '.join(filter(None, [o.device_brand, o.device_model])) or 'equipo'
            link = o.public_url
            if o.status == 'draft':
                add(o, 'draft', 'Equipo recibido',
                    'Hola %s, recibimos su %s (orden %s) en %s. Puede seguir el estado desde acá: %s' % (name, device, o.name, company, link))
            elif o.status == 'quote':
                add(o, 'quote', 'Presupuesto listo',
                    'Hola %s, el presupuesto de su %s (orden %s) es de %.2f. Puede revisarlo y aprobarlo acá: %s' % (name, device, o.name, o.total, link))
            else:
                add(o, 'done', 'Listo para retirar',
                    'Hola %s, su %s (orden %s) está listo para retirar. Total: %.2f. %s' % (name, device, o.name, o.total, link))
        for o in self.search([('status', '=', 'delivered'), ('wa_survey_sent', '=', False), ('rating', '=', False),
                              ('date_finished', '<=', today - timedelta(days=7)),
                              ('date_finished', '>=', today - timedelta(days=45))], order='date_finished desc', limit=60):
            o._ensure_token()
            name = o.partner_id.name or o.customer_name or ''
            add(o, 'survey', 'Encuesta posventa',
                'Hola %s, ¿cómo le fue con la reparación (orden %s)? Nos ayuda mucho su opinión, son 10 segundos: %s' % (name, o.name, o.public_url))
        return {'rows': rows}

    @api.model
    def msgs_mark(self, order_id, kind):
        order = self.browse(int(order_id)).exists()
        if not order:
            raise UserError('La orden ya no existe.')
        if kind == 'survey':
            order.with_context(tracking_disable=True).write({'wa_survey_sent': True})
        else:
            order.with_context(tracking_disable=True).write({'wa_notified': order.status})
        order.message_post(body='Aviso por WhatsApp enviado (%s).' % kind)
        return True

    # ------------------------------------------------------------------ registro de actividad
    @api.model
    def act_log(self, limit=150):
        if not self.env.user.has_group('taller.group_taller_manager'):
            raise UserError('Solo para responsables.')
        messages = self.env['mail.message'].sudo().search(
            [('model', '=', 'service.order'), ('message_type', 'in', ('comment', 'notification'))],
            order='id desc', limit=min(int(limit or 150), 400))
        rows = []
        for m in messages:
            body = re.sub(r'<[^>]+>', ' ', m.body or '')
            body = re.sub(r'\s+', ' ', body).strip()
            changes = []
            for t in m.tracking_value_ids:
                changes.append('%s: %s → %s' % (t.field_id.field_description,
                                                t.old_value_char or t.old_value_float or '—',
                                                t.new_value_char or t.new_value_float or '—'))
            if not body and not changes:
                continue
            order = self.browse(m.res_id).exists()
            rows.append({
                'id': m.res_id, 'order': order.name or '#%s' % m.res_id,
                'who': m.author_id.name or 'Sistema',
                'when': fields.Datetime.context_timestamp(self, m.date).strftime('%d/%m %H:%M') if m.date else '',
                'text': body[:220], 'changes': changes[:4],
            })
        return {'rows': rows}
