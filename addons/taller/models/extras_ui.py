from datetime import timedelta
from urllib.parse import quote

from odoo import models, fields, api
from odoo.exceptions import UserError


class ServiceOrderUiExtras(models.Model):
    _inherit = 'service.order'

    # ------------------------------------------------------------------ plantillas de WhatsApp
    def _ficha_wa_templates(self):
        self.ensure_one()
        raw = self.partner_id.phone
        if not raw:
            return []
        number = self._whatsapp_number(raw)
        self._ensure_token()
        name = self.partner_id.name or self.customer_name or ''
        device = ' '.join(filter(None, [self.device_brand, self.device_model])) or 'equipo'
        symbol = self.currency_id.symbol or ''
        total = '%s %s' % (symbol, '{:,.0f}'.format(self.total or 0).replace(',', '.'))
        balance = '%s %s' % (symbol, '{:,.0f}'.format(self.balance or 0).replace(',', '.'))
        link = self.public_url or ''
        status = self.status
        defs = [
            ('quote', 'Presupuesto', status == 'quote',
             'Hola %s, el presupuesto de su %s (orden %s) es de %s. Puede revisarlo y aprobarlo '
             'o rechazarlo desde este enlace: %s' % (name, device, self.name, total, link)),
            ('ready', 'Equipo listo para retirar', status == 'done',
             'Hola %s, su %s (orden %s) ya está listo para retirar. Total: %s. Lo esperamos.' % (
                 name, device, self.name, total)),
            ('progress', 'Aviso de avance', status in ('diagnosing', 'repairing'),
             'Hola %s, le escribimos por su %s (orden %s). Estamos trabajando en él y le '
             'avisaremos apenas esté listo.' % (name, device, self.name)),
            ('delay', 'Aviso de demora', bool(self.promise_date and self.promise_date < fields.Date.today()
                                              and status in ('draft', 'diagnosing', 'quote', 'repairing')),
             'Hola %s, le pedimos disculpas: su %s (orden %s) lleva algo más de lo previsto. '
             'Le avisamos en cuanto tengamos novedades.' % (name, device, self.name)),
            ('pickup', 'Recordatorio de retiro', status == 'done',
             'Hola %s, le recordamos que su %s (orden %s) sigue listo en el local para retirar.' % (
                 name, device, self.name)),
            ('balance', 'Recordatorio de saldo', bool(self.balance and self.balance > 0
                                                    and status in ('done', 'delivered')),
             'Hola %s, le recordamos que la orden %s tiene un saldo pendiente de %s. Gracias.' % (
                 name, self.name, balance)),
            ('tracking', 'Enlace de seguimiento', False,
             'Hola %s, puede seguir el estado de su equipo (orden %s) aquí: %s' % (name, self.name, link)),
            ('thanks', 'Agradecimiento y encuesta', status == 'delivered',
             'Hola %s, gracias por confiar en nosotros. ¿Nos cuenta cómo fue su experiencia con la '
             'orden %s? Solo toma un minuto: %s' % (name, self.name, link)),
        ]
        items = [{
            'key': key, 'label': label, 'suggested': suggested, 'text': text,
            'url': 'https://wa.me/%s?text=%s' % (number, quote(text)),
        } for key, label, suggested, text in defs]
        items.sort(key=lambda item: not item['suggested'])
        return items

    @api.model
    def ficha_log_wa(self, order_id, label):
        order = self.browse(int(order_id)).exists()
        if order:
            order.message_post(body='WhatsApp enviado al cliente: %s' % (label or '')[:80],
                               message_type='comment', subtype_xmlid='mail.mt_note')
        return True

    # ------------------------------------------------------------------ caja diaria
    @api.model
    def caja_data(self, date_str=None):
        if not self.env.user.has_group('taller.group_taller_manager'):
            raise UserError('La caja diaria es solo para responsables.')
        day = fields.Date.to_date(date_str) if date_str else fields.Date.context_today(self)
        Payment = self.env['service.payment']
        labels = dict(Payment._fields['method'].selection)
        payments = Payment.search([('date', '=', day)], order='id desc')
        totals = {key: 0.0 for key in labels}
        rows = []
        for pay in payments:
            totals[pay.method] += pay.amount
            rows.append({
                'id': pay.id,
                'order_id': pay.order_id.id,
                'order': pay.order_id.name,
                'customer': pay.order_id.partner_id.name or pay.order_id.customer_name or '',
                'method': pay.method,
                'method_label': labels[pay.method],
                'amount': pay.amount,
                'note': pay.note or '',
                'time': fields.Datetime.context_timestamp(self, pay.create_date).strftime('%H:%M')
                        if pay.create_date else '',
            })
        Sale = self.env['taller.sale']
        for sale in Sale.search([('date', '=', day), ('state', '=', 'done')], order='id desc'):
            totals[sale.method] += sale.total
            rows.append({
                'id': 'v%s' % sale.id,
                'order_id': False,
                'order': sale.name,
                'customer': sale.customer or 'Venta de mostrador',
                'method': sale.method,
                'method_label': labels[sale.method],
                'amount': sale.total,
                'note': ', '.join(sale.line_ids.mapped('name'))[:80],
                'time': fields.Datetime.context_timestamp(self, sale.create_date).strftime('%H:%M')
                        if sale.create_date else '',
            })
        week = []
        for offset in range(6, -1, -1):
            d = day - timedelta(days=offset)
            groups = Payment._read_group([('date', '=', d)], aggregates=['amount:sum'])
            sales = Sale._read_group([('date', '=', d), ('state', '=', 'done')], aggregates=['total:sum'])
            week.append({'date': d.strftime('%d/%m'),
                         'total': ((groups[0][0] if groups else 0) or 0) + ((sales[0][0] if sales else 0) or 0)})
        return {
            'date': day.isoformat(),
            'symbol': self.env.company.currency_id.symbol or '',
            'methods': [{'key': key, 'label': label, 'total': totals[key]} for key, label in labels.items()],
            'total': sum(totals.values()),
            'count': len(rows),
            'rows': rows,
            'week': week,
        }

    # ------------------------------------------------------------------ portada: resumen del dia
    @api.model
    def dash_extra(self):
        today = fields.Date.context_today(self)
        is_manager = self.env.user.has_group('taller.group_taller_manager')
        symbol = self.env.company.currency_id.symbol or ''
        labels = dict(self._fields['status'].selection)

        def row(order, extra=''):
            return {
                'id': order.id,
                'name': order.name,
                'customer': order.partner_id.name or order.customer_name or '',
                'device': ' '.join(filter(None, [order.device_brand, order.device_model])),
                'extra': extra,
                'status_label': labels.get(order.status, order.status),
            }

        late = self.search([('promise_date', '<', today),
                            ('status', 'in', ['draft', 'diagnosing', 'quote', 'repairing'])],
                           order='promise_date asc', limit=5)
        waiting = self.search([('status', '=', 'done'), ('date_ready', '<=', today - timedelta(days=3))],
                              order='date_ready asc', limit=5)
        quotes = self.search([('status', '=', 'quote'), ('quote_date', '<=', today - timedelta(days=2))],
                             order='quote_date asc', limit=5)
        low = self.env['service.part'].search([('low_stock', '=', True)], limit=5, order='stock asc')
        result = {
            'symbol': symbol,
            'is_manager': is_manager,
            'created_today': self.search_count([('date_received', '=', today)]),
            'delivered_today': self.search_count([('status', '=', 'delivered'), ('date_finished', '=', today)]),
            'attention': {
                'late': [row(o, 'Prometida %s' % o.promise_date.strftime('%d/%m')) for o in late],
                'waiting': [row(o, 'Lista desde %s' % o.date_ready.strftime('%d/%m')) for o in waiting],
                'quotes': [row(o, 'Enviado %s' % o.quote_date.strftime('%d/%m')) for o in quotes],
                'low_stock': [{'id': p.id, 'name': p.display_name, 'stock': p.stock, 'min': p.min_stock} for p in low],
            },
        }
        if is_manager:
            paid = self.env['service.payment']._read_group([('date', '=', today)], aggregates=['amount:sum'])
            sold = self.env['taller.sale']._read_group(
                [('date', '=', today), ('state', '=', 'done')], aggregates=['total:sum', '__count'])
            result['cash_today'] = ((paid[0][0] if paid else 0) or 0) + ((sold[0][0] if sold else 0) or 0)
            result['sales_today'] = (sold[0][1] if sold else 0) or 0
        return result
