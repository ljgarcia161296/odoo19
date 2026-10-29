from odoo import models, fields, api
from odoo.exceptions import AccessError

TV_COLUMNS = [
    ('draft', 'Recibidos'),
    ('diagnosing', 'En diagnóstico'),
    ('quote', 'Esperando aprobación'),
    ('repairing', 'En reparación'),
    ('done', 'Listos para retirar'),
]
OPEN_STATES = ['draft', 'diagnosing', 'quote', 'repairing']
MAX_PER_COLUMN = 8


class ServiceOrderTv(models.Model):
    _inherit = 'service.order'

    @api.model
    def tv_data(self):
        """Datos del tablero para la pantalla del taller. Muestra solo datos poco sensibles."""
        if not self.env.user.has_group('taller.group_taller_manager'):
            raise AccessError('Solo los administradores pueden abrir el tablero.')
        today = fields.Date.today()
        orders = self.sudo().search([('status', 'in', [k for k, _l in TV_COLUMNS])],
                                    order='promise_date asc, id desc')
        grouped = {key: [] for key, _label in TV_COLUMNS}
        for order in orders:
            grouped[order.status].append(order)
        device_labels = dict(self._fields['device_type'].selection)
        columns, late = [], 0
        for key, label in TV_COLUMNS:
            cards = []
            for order in grouped[key]:
                is_late = bool(order.promise_date and order.promise_date < today
                               and order.status in OPEN_STATES)
                late += 1 if is_late else 0
                if len(cards) < MAX_PER_COLUMN:
                    first = ((order.partner_id.name or order.customer_name or '').split() or [''])[0]
                    device = ' '.join(filter(None, [order.device_brand, order.device_model]))
                    cards.append({
                        'id': order.id,
                        'name': order.name,
                        'first_name': first,
                        'device': device or device_labels.get(order.device_type, ''),
                        'promise': order.promise_date.strftime('%d/%m') if order.promise_date else '',
                        'late': is_late,
                    })
            columns.append({
                'key': key, 'label': label, 'count': len(grouped[key]),
                'orders': cards, 'more': max(len(grouped[key]) - len(cards), 0),
            })
        return {
            'columns': columns,
            'late': late,
            'ready': len(grouped['done']),
            'company': self.env.company.name,
        }
