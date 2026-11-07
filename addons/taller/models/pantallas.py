import calendar as pycal
import re
from datetime import date, timedelta
from urllib.parse import quote

from odoo import models, fields, api
from odoo.exceptions import UserError

PURCHASE_STATES = {'draft': 'Borrador', 'ordered': 'Pedida', 'received': 'Recibida', 'cancel': 'Cancelada'}


class ServiceOrderPantallas(models.Model):
    _inherit = 'service.order'

    @api.model
    def _whatsapp_number(self, raw):
        number = re.sub(r'\D', '', raw or '')
        if number.startswith('00'):
            number = number[2:]
        elif number.startswith('0'):
            number = '598' + number[1:]
        elif len(number) == 8 and number.startswith('9'):
            number = '598' + number
        return number

    @api.model
    def _need_manager(self):
        if not self.env.user.has_group('taller.group_taller_manager'):
            raise UserError('Esta pantalla es solo para responsables.')

    # ------------------------------------------------------------------ calendario propio
    @api.model
    def cal_data(self, year=None, month=None):
        today = fields.Date.context_today(self)
        year = int(year or today.year)
        month = int(month or today.month)
        start = date(year, month, 1)
        end = date(year, month, pycal.monthrange(year, month)[1])
        orders = self.search([('promise_date', '>=', start), ('promise_date', '<=', end),
                              ('status', '!=', 'cancel')], order='promise_date, id')
        labels = dict(self._fields['status'].selection)
        days = {}
        for o in orders:
            days.setdefault(o.promise_date.isoformat(), []).append({
                'id': o.id, 'name': o.name,
                'customer': o.partner_id.name or o.customer_name or '',
                'device': ' '.join(filter(None, [o.device_brand, o.device_model])),
                'status': o.status, 'status_label': labels.get(o.status, o.status),
                'late': bool(o.promise_date < today and o.status in ('draft', 'diagnosing', 'quote', 'repairing')),
                'movable': o.status not in ('delivered', 'cancel'),
            })
        names = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto',
                 'septiembre', 'octubre', 'noviembre', 'diciembre']
        first_weekday = start.weekday()  # lunes = 0
        cells = []
        for i in range(first_weekday):
            cells.append({'empty': True, 'key': 'e%s' % i})
        for d in range(1, end.day + 1):
            iso = date(year, month, d).isoformat()
            cells.append({'empty': False, 'key': iso, 'iso': iso, 'day': d, 'today': iso == today.isoformat(),
                          'items': days.get(iso, [])})
        return {
            'year': year, 'month': month, 'title': '%s %s' % (names[month - 1].capitalize(), year),
            'cells': cells, 'total': len(orders),
        }

    @api.model
    def cal_move(self, order_id, iso):
        order = self.browse(int(order_id)).exists()
        if not order:
            raise UserError('La orden ya no existe.')
        if order.status in ('delivered', 'cancel'):
            raise UserError('No se puede cambiar la fecha de una orden entregada o cancelada.')
        new_date = fields.Date.to_date(iso)
        order.write({'promise_date': new_date})
        return True

    # ------------------------------------------------------------------ compras
    @api.model
    def compras_list(self):
        self._need_manager()
        purchases = self.env['service.purchase'].search([], limit=80)
        symbol = self.env.company.currency_id.symbol or ''
        return {
            'symbol': symbol,
            'rows': [{
                'id': p.id, 'name': p.name, 'supplier': p.partner_id.name or 'Sin proveedor',
                'date': p.date.strftime('%d/%m/%Y') if p.date else '',
                'state': p.state, 'state_label': PURCHASE_STATES.get(p.state, p.state),
                'total': p.total,
                'items': ', '.join('%g x %s' % (l.quantity, l.part_id.name) for l in p.line_ids)[:140],
            } for p in purchases],
        }

    @api.model
    def compras_action(self, purchase_id, op):
        self._need_manager()
        purchase = self.env['service.purchase'].browse(int(purchase_id)).exists()
        methods = {'order': 'action_order', 'receive': 'action_receive',
                   'cancel': 'action_cancel', 'draft': 'action_draft'}
        if not purchase or op not in methods:
            raise UserError('Acción no válida.')
        getattr(purchase, methods[op])()
        return True

    # ------------------------------------------------------------------ garantias
    @api.model
    def garantias_list(self):
        today = fields.Date.context_today(self)
        orders = self.search([('status', '=', 'delivered'), ('warranty_days', '>', 0),
                              ('warranty_end', '>=', today - timedelta(days=60))], order='warranty_end asc')
        rows = []
        for o in orders:
            left = (o.warranty_end - today).days
            phone = o.partner_id.phone
            number = self._whatsapp_number(phone) if phone else ''
            name = o.partner_id.name or o.customer_name or ''
            device = ' '.join(filter(None, [o.device_brand, o.device_model])) or 'equipo'
            if left >= 0:
                text = ('Hola %s, le recordamos que la garantía de la reparación de su %s (orden %s) '
                        'vence el %s. Si notó algún problema, escríbanos.') % (
                    name, device, o.name, o.warranty_end.strftime('%d/%m/%Y'))
            else:
                text = ('Hola %s, le escribimos del taller. Esperamos que su %s siga funcionando bien. '
                        'Quedamos a su disposición.') % (name, device)
            rows.append({
                'id': o.id, 'name': o.name, 'customer': name, 'phone': phone or '', 'device': device,
                'end': o.warranty_end.strftime('%d/%m/%Y'), 'days_left': left,
                'kind': 'expired' if left < 0 else ('soon' if left <= 7 else 'active'),
                'wa_url': ('https://wa.me/%s?text=%s' % (number, quote(text))) if number else '',
            })
        return {'rows': rows}

    @api.model
    def garantia_reentry(self, order_id):
        order = self.browse(int(order_id)).exists()
        if not order:
            raise UserError('La orden ya no existe.')
        action = order.action_warranty_reentry()
        return action.get('res_id')

    # ------------------------------------------------------------------ configuracion
    @api.model
    def cfg_get(self):
        self._need_manager()
        company = self.env.company
        params = self.env['ir.config_parameter'].sudo()
        return {
            'name': company.name or '',
            'phone': company.phone or '',
            'email': company.email or '',
            'street': company.street or '',
            'city': company.city or '',
            'website': company.website or '',
            'has_logo': bool(company.logo),
            'logo_url': '/web/image/res.company/%s/logo?unique=%s' % (
                company.id, company.write_date.strftime('%Y%m%d%H%M%S') if company.write_date else ''),
            'warranty_days': int(params.get_param('taller.default_warranty_days', 30) or 0),
            'terms': params.get_param('taller.pdf_terms', '') or '',
        }

    @api.model
    def cfg_save(self, vals, logo=None):
        self._need_manager()
        company = self.env.company
        write = {}
        for key in ('name', 'phone', 'email', 'street', 'city', 'website'):
            if key in (vals or {}):
                value = (vals[key] or '').strip()
                if key == 'name' and not value:
                    raise UserError('El nombre del taller no puede quedar vacío.')
                write[key] = value or False
        if logo:
            image = self._counter_b64(logo)
            if image:
                write['logo'] = image
        if write:
            company.sudo().write(write)
        params = self.env['ir.config_parameter'].sudo()
        if 'warranty_days' in (vals or {}):
            days = int(vals['warranty_days'] or 0)
            if days < 0 or days > 3650:
                raise UserError('Los días de garantía deben estar entre 0 y 3650.')
            params.set_param('taller.default_warranty_days', str(days))
        if 'terms' in (vals or {}):
            params.set_param('taller.pdf_terms', (vals['terms'] or '').strip()[:1500])
        return True
