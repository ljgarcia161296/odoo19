from datetime import timedelta

from odoo import models, fields, api
from odoo.exceptions import UserError
from odoo.tools import html2plaintext

from .counter import TECH_ACTIONS

STEPS = [
    ('draft', 'Recibido'),
    ('diagnosing', 'Diagnóstico'),
    ('quote', 'Presupuesto'),
    ('repairing', 'Reparación'),
    ('done', 'Listo'),
    ('delivered', 'Entregado'),
]
OPEN_STATES = ['draft', 'diagnosing', 'quote', 'repairing']
FICHA_FIELDS = {
    'issue_description', 'physical_condition', 'accessories', 'device_brand',
    'device_model', 'serial_number', 'promise_date', 'notify_customer',
}
BOARD_COLUMNS = [
    ('draft', 'Recibidos'),
    ('diagnosing', 'En diagnóstico'),
    ('quote', 'Esperando aprobación'),
    ('repairing', 'En reparación'),
    ('done', 'Listos para retirar'),
    ('delivered', 'Entregados (7 días)'),
]
BOARD_FORWARD = {
    ('draft', 'diagnosing'): 'action_start_diagnosis',
    ('diagnosing', 'quote'): 'action_send_quote',
    ('diagnosing', 'repairing'): 'action_start_repair',
    ('quote', 'repairing'): 'action_approve_quote',
    ('repairing', 'done'): 'action_done',
    ('done', 'delivered'): 'action_deliver',
}
STATUS_ORDER = [key for key, _label in STEPS]
MAX_PER_COLUMN = 25


class ServiceOrderFicha(models.Model):
    _inherit = 'service.order'

    # ------------------------------------------------------------------ ficha de la orden
    def _ficha_timeline(self):
        self.ensure_one()
        messages = self.env['mail.message'].sudo().search(
            [('model', '=', self._name), ('res_id', '=', self.id)],
            order='date desc, id desc', limit=60)
        items = []
        for message in messages:
            changes = [{
                'field': tracking.field_id.field_description,
                'old': tracking.old_value_char or '',
                'new': tracking.new_value_char or '',
            } for tracking in message.tracking_value_ids]
            text = html2plaintext(message.body or '').strip()
            if not changes and not text:
                continue
            if changes:
                kind = 'change'
            else:
                kind = 'note' if message.message_type == 'comment' else 'system'
            when = fields.Datetime.context_timestamp(self, message.date).strftime('%d/%m %H:%M')
            items.append({
                'id': message.id,
                'when': when,
                'author': message.author_id.name or 'Sistema',
                'kind': kind,
                'changes': changes,
                'text': text,
            })
        return items

    def _ficha_link(self, method):
        try:
            return getattr(self, method)()['url']
        except UserError:
            return ''

    @api.model
    def ficha_get(self, order_id):
        order = self.browse(int(order_id)).exists()
        if not order:
            raise UserError('La orden ya no existe.')
        today = fields.Date.today()
        is_manager = self.env.user.has_group('taller.group_taller_manager')
        status_labels = dict(self._fields['status'].selection)
        type_labels = dict(self._fields['device_type'].selection)
        method_labels = dict(self.env['service.payment']._fields['method'].selection)
        warranty_labels = dict(self._fields['warranty_status'].selection)
        keys = [key for key, _label in STEPS]
        current = keys.index(order.status) if order.status in keys else -1
        steps = [{
            'key': key, 'label': label,
            'state': 'done' if i < current else ('current' if i == current else 'todo'),
        } for i, (key, label) in enumerate(STEPS)]
        late = bool(order.promise_date and order.promise_date < today and order.status in OPEN_STATES)
        phone = order.partner_id.phone or ''
        invoice = order.invoice_id
        return {
            'id': order.id,
            'name': order.name,
            'status': order.status,
            'status_label': status_labels.get(order.status, order.status),
            'steps': steps,
            'late': late,
            'recurrent': bool(order.recurrent_flag),
            'no_charge': bool(order.no_charge),
            'is_manager': is_manager,
            'editable': order.status not in ('delivered', 'cancel'),
            'partner': {
                'id': order.partner_id.id,
                'name': order.partner_id.name or order.customer_name or '',
                'phone': phone,
                'email': order.partner_id.email or '',
            },
            'device': {
                'type': order.device_type,
                'type_label': type_labels.get(order.device_type, ''),
                'brand': order.device_brand or '',
                'model': order.device_model or '',
                'serial': order.serial_number or '',
                'accessories': order.accessories or '',
            },
            'problem': order.issue_description or '',
            'condition': order.physical_condition or '',
            'promise_date': order.promise_date.isoformat() if order.promise_date else '',
            'date_received': order.date_received.strftime('%d/%m/%Y') if order.date_received else '',
            'date_ready': order.date_ready.strftime('%d/%m/%Y') if order.date_ready else '',
            'date_finished': order.date_finished.strftime('%d/%m/%Y') if order.date_finished else '',
            'user': {'id': order.user_id.id or False, 'name': order.user_id.name or ''},
            'users': self.counter_init()['users'] if is_manager else [],
            'warranty': {
                'days': order.warranty_days,
                'end': order.warranty_end.strftime('%d/%m/%Y') if order.warranty_end else '',
                'status': order.warranty_status,
                'label': warranty_labels.get(order.warranty_status, ''),
            },
            'lines': [{
                'id': line.id, 'name': line.name, 'qty': line.quantity,
                'price': line.unit_price, 'subtotal': line.subtotal,
            } for line in order.line_ids],
            'labor': order.labor_cost,
            'parts_total': order.parts_total,
            'total': order.total,
            'paid': order.paid_total,
            'balance': order.balance,
            'symbol': order.currency_id.symbol or '',
            'payments': [{
                'id': pay.id,
                'date': pay.date.strftime('%d/%m/%Y') if pay.date else '',
                'amount': pay.amount,
                'method': method_labels.get(pay.method, pay.method),
                'note': pay.note or '',
            } for pay in order.payment_ids],
            'checks': [{
                'id': check.id, 'name': check.name, 'result': check.result, 'note': check.note or '',
            } for check in order.check_ids],
            'photos': [{
                'id': photo.id,
                'name': photo.name or '',
                'stage': photo.stage,
                'url': '/web/image/service.order.photo/%s/image' % photo.id,
            } for photo in order.photo_ids],
            'has_intake_signature': bool(order.intake_signature),
            'actions': [{'key': k, 'label': label, 'primary': primary}
                        for k, label, primary in TECH_ACTIONS.get(order.status, [])],
            'links': {
                'public_url': order.public_url or '',
                'tel': ('tel:+%s' % self._whatsapp_number(phone)) if phone else '',
                'wa_url': order._ficha_link('action_whatsapp') if phone else '',
                'wa_track_url': order._ficha_link('action_whatsapp_link') if phone else '',
            },
            'approved_date': order.approved_date.strftime('%d/%m/%Y') if order.approved_date else '',
            'quote_date': order.quote_date.strftime('%d/%m/%Y') if order.quote_date else '',
            'invoice': {'id': invoice.id, 'name': invoice.name or 'Borrador', 'state': invoice.state}
                       if invoice else None,
            'can_invoice': bool(is_manager and order.status in ('done', 'delivered')
                                and not invoice and order.total and not order.no_charge),
            'rating': order.rating or '',
            'rating_comment': order.rating_comment or '',
            'timeline': order._ficha_timeline(),
        }

    @api.model
    def ficha_write(self, order_id, vals):
        order = self.browse(int(order_id)).exists()
        if not order:
            raise UserError('La orden ya no existe.')
        clean = {}
        for key, value in (vals or {}).items():
            if key in FICHA_FIELDS:
                clean[key] = value if value not in ('', None) else False
            elif key == 'user_id' and self.env.user.has_group('taller.group_taller_manager'):
                clean['user_id'] = int(value) if value else False
        if clean:
            order.write(clean)
        return True

    @api.model
    def ficha_check(self, check_id, result):
        check = self.env['service.order.check'].browse(int(check_id)).exists()
        if check and result in ('ok', 'fail', 'na', 'untested'):
            check.write({'result': result})
        return True

    @api.model
    def ficha_add_payment(self, order_id, amount, method, note=''):
        order = self.browse(int(order_id)).exists()
        amount = float(amount or 0)
        methods = dict(self.env['service.payment']._fields['method'].selection)
        if not order or amount <= 0 or method not in methods:
            raise UserError('Indique un monto mayor que cero y la forma de pago.')
        self.env['service.payment'].create({
            'order_id': order.id, 'amount': amount, 'method': method, 'note': (note or '')[:200],
        })
        return True

    @api.model
    def ficha_add_note(self, order_id, text):
        order = self.browse(int(order_id)).exists()
        text = (text or '').strip()
        if not order or not text:
            raise UserError('Escriba la nota.')
        order.message_post(body=text[:2000], message_type='comment', subtype_xmlid='mail.mt_note')
        return True

    @api.model
    def ficha_add_photo(self, order_id, name, data, stage='intake'):
        order = self.browse(int(order_id)).exists()
        image = self._counter_b64(data)
        if not order or not image:
            raise UserError('No se pudo leer la foto.')
        self.env['service.order.photo'].create({
            'order_id': order.id,
            'name': (name or 'Foto')[:80],
            'stage': stage if stage in ('intake', 'delivery') else 'intake',
            'image': image,
        })
        return True

    # ------------------------------------------------------------------ tablero
    @api.model
    def board_data(self, search='', mine=False, late_only=False):
        today = fields.Date.today()
        domain = []
        search = (search or '').strip()
        if search:
            domain += ['|', '|', '|', ('name', 'ilike', search), ('customer_name', 'ilike', search),
                       ('partner_id.name', 'ilike', search), ('serial_number', 'ilike', search)]
        if mine:
            domain.append(('user_id', '=', self.env.uid))
        if late_only:
            domain += [('promise_date', '<', today), ('status', 'in', OPEN_STATES)]
        open_keys = [key for key, _label in BOARD_COLUMNS[:-1]]
        domain += ['|', ('status', 'in', open_keys), '&', ('status', '=', 'delivered'),
                   ('date_finished', '>=', today - timedelta(days=7))]
        orders = self.search(domain, order='promise_date asc, id desc', limit=400)
        type_labels = dict(self._fields['device_type'].selection)
        grouped = {key: [] for key, _label in BOARD_COLUMNS}
        for order in orders:
            grouped[order.status].append(order)
        columns = []
        for key, label in BOARD_COLUMNS:
            cards = []
            for order in grouped[key][:MAX_PER_COLUMN]:
                tech = order.user_id.name or ''
                cards.append({
                    'id': order.id,
                    'name': order.name,
                    'customer': order.partner_id.name or order.customer_name or '',
                    'device': ' '.join(filter(None, [order.device_brand, order.device_model]))
                              or type_labels.get(order.device_type, ''),
                    'device_type': order.device_type,
                    'promise': order.promise_date.strftime('%d/%m') if order.promise_date else '',
                    'late': bool(order.promise_date and order.promise_date < today
                                 and order.status in OPEN_STATES),
                    'total': order.total,
                    'balance': order.balance,
                    'recurrent': bool(order.recurrent_flag),
                    'tech': tech,
                    'tech_initial': tech[:1].upper(),
                    'days': (today - order.date_received).days if order.date_received else 0,
                })
            columns.append({
                'key': key, 'label': label, 'count': len(grouped[key]),
                'cards': cards, 'more': max(len(grouped[key]) - len(cards), 0),
            })
        return {'columns': columns, 'symbol': self.env.company.currency_id.symbol or ''}

    @api.model
    def board_move(self, order_id, target):
        order = self.browse(int(order_id)).exists()
        if not order:
            raise UserError('La orden ya no existe.')
        if order.status == target:
            return True
        method = BOARD_FORWARD.get((order.status, target))
        if method:
            getattr(order, method)()
        elif (order.status in STATUS_ORDER and target in STATUS_ORDER
              and order.status != 'delivered'
              and STATUS_ORDER.index(target) < STATUS_ORDER.index(order.status)):
            order.write({'status': target})
        else:
            raise UserError('Mueva la orden un paso a la vez, siguiendo el flujo. '
                            'Para otros cambios use los botones de la orden.')
        return True
