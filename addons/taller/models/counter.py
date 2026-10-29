import base64
import binascii
import re

from odoo import models, fields, api
from odoo.exceptions import UserError

MAX_IMAGE_BYTES = 4 * 1024 * 1024
MAX_PHOTOS = 8

# acciones que el técnico puede ejecutar según el estado
TECH_ACTIONS = {
    'draft': [('start_diagnosis', 'Iniciar diagnóstico', True)],
    'diagnosing': [('send_quote', 'Enviar presupuesto', False),
                   ('start_repair', 'Iniciar reparación', True)],
    'quote': [('approve_quote', 'El cliente aprobó', True),
              ('reject_quote', 'El cliente rechazó', False)],
    'repairing': [('done', 'Marcar listo', True)],
    'done': [('deliver', 'Entregar', True)],
}
TECH_METHODS = {
    'start_diagnosis': 'action_start_diagnosis',
    'send_quote': 'action_send_quote',
    'start_repair': 'action_start_repair',
    'approve_quote': 'action_approve_quote',
    'reject_quote': 'action_reject_quote',
    'done': 'action_done',
    'deliver': 'action_deliver',
}


class ServiceOrderCounter(models.Model):
    _inherit = 'service.order'

    intake_signature = fields.Image(string='Firma de conformidad al ingreso', copy=False,
                                    attachment=True, max_width=600, max_height=300)

    # ------------------------------------------------------------------ utilidades
    @api.model
    def _counter_b64(self, data):
        """Devuelve el base64 limpio de una imagen enviada desde el navegador, o False."""
        if not data or not isinstance(data, str):
            return False
        data = re.sub(r'^data:[^;]+;base64,', '', data.strip())
        try:
            raw = base64.b64decode(data, validate=True)
        except (binascii.Error, ValueError):
            return False
        if not raw or len(raw) > MAX_IMAGE_BYTES:
            return False
        return data

    # ------------------------------------------------------------------ recepción
    @api.model
    def counter_init(self):
        is_manager = self.env.user.has_group('taller.group_taller_manager')
        users = []
        if is_manager:
            group = self.env.ref('taller.group_taller_technician')
            users_model = self.env['res.users']
            field = 'group_ids' if 'group_ids' in users_model._fields else 'groups_id'
            found = users_model.search([(field, 'in', group.id)])
            users = [{'id': u.id, 'name': u.name} for u in found]
        return {'is_manager': is_manager, 'uid': self.env.uid, 'users': users}

    @api.model
    def counter_search(self, query):
        query = (query or '').strip()
        if len(query) < 2:
            return {'partners': [], 'devices': []}
        partners = self.env['res.partner'].search(
            ['|', '|', ('name', 'ilike', query), ('phone', 'ilike', query),
             ('email', 'ilike', query)], limit=8)
        seen, devices = set(), []
        for order in self.search([('serial_number', 'ilike', query)], order='id desc', limit=30):
            key = (order.serial_number or '').strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            devices.append({
                'serial': order.serial_number,
                'brand': order.device_brand or '',
                'model': order.device_model or '',
                'device_type': order.device_type,
                'partner_id': order.partner_id.id,
                'partner_name': order.partner_id.name or order.customer_name or '',
                'partner_phone': order.partner_id.phone or '',
            })
            if len(devices) >= 5:
                break
        return {
            'partners': [{'id': p.id, 'name': p.name, 'phone': p.phone or ''} for p in partners],
            'devices': devices,
        }

    @api.model
    def counter_create_partner(self, name, phone):
        name = (name or '').strip()
        if not name:
            raise UserError('Escriba el nombre del cliente.')
        partner = self.env['res.partner'].create({'name': name, 'phone': (phone or '').strip()})
        return {'id': partner.id, 'name': partner.name, 'phone': partner.phone or ''}

    @api.model
    def counter_checklist(self, device_type):
        items = self.env['service.checklist.item'].search(
            ['|', ('device_type', '=', False), ('device_type', '=', device_type)])
        return [{'item_id': i.id, 'name': i.name} for i in items]

    @api.model
    def counter_history(self, serial):
        serial = (serial or '').strip()
        if not serial:
            return {'count': 0, 'orders': []}
        labels = dict(self._fields['status'].selection)
        orders = self.search([('serial_number', '=ilike', serial)], order='id desc', limit=5)
        return {
            'count': len(orders),
            'orders': [{
                'name': o.name,
                'date': o.date_received.strftime('%d/%m/%Y') if o.date_received else '',
                'status': labels.get(o.status, o.status),
            } for o in orders],
        }

    @api.model
    def counter_create(self, payload):
        payload = payload or {}
        partner_id = payload.get('partner_id')
        if not partner_id:
            raise UserError('Seleccione o cree el cliente.')
        device_type = payload.get('device_type') or 'other'
        if device_type not in dict(self._fields['device_type'].selection):
            raise UserError('Tipo de equipo no válido.')
        clean = lambda key, size=500: (payload.get(key) or '').strip()[:size]
        vals = {
            'partner_id': int(partner_id),
            'device_type': device_type,
            'device_brand': clean('brand', 80),
            'device_model': clean('model', 80),
            'serial_number': clean('serial', 80),
            'accessories': clean('accessories', 200),
            'issue_description': clean('problem', 2000),
            'physical_condition': clean('condition', 2000),
        }
        if payload.get('promise_date'):
            vals['promise_date'] = payload['promise_date']
        if payload.get('user_id') and self.env.user.has_group('taller.group_taller_manager'):
            vals['user_id'] = int(payload['user_id'])
        signature = self._counter_b64(payload.get('signature'))
        if signature:
            vals['intake_signature'] = signature
        photos = []
        for index, photo in enumerate((payload.get('photos') or [])[:MAX_PHOTOS]):
            data = self._counter_b64((photo or {}).get('data'))
            if data:
                photos.append((0, 0, {
                    'name': ((photo or {}).get('name') or 'Foto %s' % (index + 1))[:80],
                    'stage': 'intake',
                    'image': data,
                }))
        if photos:
            vals['photo_ids'] = photos

        order = self.create(vals)
        for check in payload.get('checks') or []:
            line = order.check_ids.filtered(lambda c: c.item_id.id == check.get('item_id'))[:1]
            if line and check.get('result') in ('ok', 'fail', 'na', 'untested'):
                line.write({'result': check['result'], 'note': (check.get('note') or '')[:200]})
        return {'id': order.id, 'name': order.name}

    # ------------------------------------------------------------------ vista del técnico
    @api.model
    def tech_orders(self, mode='open', mine=False):
        open_states = ['draft', 'diagnosing', 'quote', 'repairing']
        base = [('user_id', '=', self.env.uid)] if mine else []
        counts = {
            'open': self.search_count(base + [('status', 'in', open_states)]),
            'ready': self.search_count(base + [('status', '=', 'done')]),
            'late': self.search_count(base + [('status', 'in', open_states),
                                              ('promise_date', '<', fields.Date.today())]),
        }
        if mode == 'ready':
            domain = base + [('status', '=', 'done')]
        elif mode == 'late':
            domain = base + [('status', 'in', open_states), ('promise_date', '<', fields.Date.today())]
        elif mode == 'all':
            domain = base + [('status', '!=', 'cancel')]
        else:
            domain = base + [('status', 'in', open_states)]
        labels = dict(self._fields['status'].selection)
        today = fields.Date.today()
        orders = self.search(domain, order='promise_date asc, id desc', limit=60)
        items = []
        for order in orders:
            device = ' '.join(filter(None, [order.device_brand, order.device_model]))
            items.append({
                'id': order.id,
                'name': order.name,
                'customer': order.partner_id.name or order.customer_name or '',
                'phone': order.partner_id.phone or '',
                'device': device or dict(self._fields['device_type'].selection).get(order.device_type, ''),
                'device_type': order.device_type,
                'status': order.status,
                'status_label': labels.get(order.status, order.status),
                'promise': order.promise_date.strftime('%d/%m') if order.promise_date else '',
                'late': bool(order.promise_date and order.promise_date < today
                             and order.status in open_states),
                'problem': (order.issue_description or '')[:110],
                'total': order.total,
            })
        return {
            'counts': counts,
            'orders': items,
            'symbol': self.env.company.currency_id.symbol or '',
        }

    @api.model
    def tech_order_detail(self, order_id):
        order = self.browse(int(order_id)).exists()
        if not order:
            raise UserError('La orden ya no existe.')
        labels = dict(self._fields['status'].selection)
        phone = order.partner_id.phone or ''
        number = self._whatsapp_number(phone) if phone else ''
        return {
            'id': order.id,
            'name': order.name,
            'customer': order.partner_id.name or order.customer_name or '',
            'phone': phone,
            'tel': ('tel:+%s' % number) if number else '',
            'wa_url': ('https://wa.me/%s' % number) if number else '',
            'device': ' '.join(filter(None, [order.device_brand, order.device_model])),
            'serial': order.serial_number or '',
            'accessories': order.accessories or '',
            'problem': order.issue_description or '',
            'condition': order.physical_condition or '',
            'status': order.status,
            'status_label': labels.get(order.status, order.status),
            'failed_checks': [c.name for c in order.check_ids if c.result == 'fail'],
            'lines': [{'id': l.id, 'name': l.name, 'qty': l.quantity, 'price': l.unit_price,
                       'subtotal': l.subtotal} for l in order.line_ids],
            'labor': order.labor_cost,
            'total': order.total,
            'paid': order.paid_total,
            'balance': order.balance,
            'symbol': order.currency_id.symbol or '',
            'actions': [{'key': k, 'label': label, 'primary': primary}
                        for k, label, primary in TECH_ACTIONS.get(order.status, [])],
            'editable': order.status not in ('delivered', 'cancel'),
        }

    @api.model
    def tech_action(self, order_id, key):
        order = self.browse(int(order_id)).exists()
        if not order:
            raise UserError('La orden ya no existe.')
        allowed = [k for k, _label, _primary in TECH_ACTIONS.get(order.status, [])]
        if key not in allowed or key not in TECH_METHODS:
            raise UserError('Esa acción no está disponible para el estado actual de la orden.')
        getattr(order, TECH_METHODS[key])()
        return True

    @api.model
    def tech_search_parts(self, query):
        query = (query or '').strip()
        domain = ['|', ('name', 'ilike', query), ('code', 'ilike', query)] if query else []
        parts = self.env['service.part'].search(domain, limit=12)
        return [{'id': p.id, 'name': p.display_name, 'price': p.price, 'stock': p.stock}
                for p in parts]

    @api.model
    def tech_add_line(self, order_id, part_id, qty):
        order = self.browse(int(order_id)).exists()
        part = self.env['service.part'].browse(int(part_id)).exists()
        qty = float(qty or 1)
        if not order or not part or qty <= 0:
            raise UserError('Datos no válidos para agregar el repuesto.')
        self.env['service.order.line'].create({
            'order_id': order.id,
            'part_id': part.id,
            'name': part.name,
            'quantity': qty,
            'unit_price': part.price,
        })
        return True

    @api.model
    def tech_remove_line(self, line_id):
        line = self.env['service.order.line'].browse(int(line_id)).exists()
        if line:
            line.unlink()
        return True

    @api.model
    def tech_set_labor(self, order_id, amount):
        order = self.browse(int(order_id)).exists()
        if not order:
            raise UserError('La orden ya no existe.')
        order.labor_cost = max(float(amount or 0), 0.0)
        return True
