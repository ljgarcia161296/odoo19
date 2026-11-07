from odoo import models, api

CHANNEL = 'taller'
QUIET_FIELDS = {'last_quote_followup', 'access_token'}


class ServiceOrderLive(models.Model):
    _inherit = 'service.order'

    @api.model
    def get_live_profile(self):
        """Perfil del usuario para los avisos en vivo. Falla si no tiene acceso al taller."""
        self.search([], limit=1)
        return {
            'enabled': True,
            'uid': self.env.uid,
            'is_manager': self.env.user.has_group('taller.group_taller_manager'),
        }

    def _taller_push(self, event, **extra):
        bus = self.env['bus.bus'].sudo()
        labels = dict(self._fields['status'].selection)
        for order in self:
            payload = {
                'event': event,
                'id': order.id,
                'name': order.name,
                'status': order.status,
                'status_label': labels.get(order.status, ''),
                'user_id': order.user_id.id or False,
                'by': self.env.uid,
            }
            payload.update(extra)
            bus._sendone(CHANNEL, 'taller/order', payload)

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        orders._taller_push('created')
        return orders

    def write(self, vals):
        track_status = 'status' in vals
        old = {order.id: order.status for order in self} if track_status else {}
        res = super().write(vals)
        if track_status:
            for order in self:
                if old.get(order.id) != order.status:
                    order._taller_push('status', old_status=old.get(order.id))
        elif any(k not in QUIET_FIELDS and not k.startswith(('message_', 'activity_'))
                 for k in vals):
            self._taller_push('changed')
        if vals.get('rating') in ('1', '2'):
            bus = self.env['bus.bus'].sudo()
            for order in self:
                bus._sendone(CHANNEL, 'taller/rating_low', {
                    'id': order.id, 'name': order.name, 'rating': order.rating,
                    'by': self.env.uid,
                })
        return res


class ServicePartMoveLive(models.Model):
    _inherit = 'service.part.move'

    @api.model_create_multi
    def create(self, vals_list):
        moves = super().create(vals_list)
        parts = moves.filtered(lambda m: m.move_type == 'out').mapped('part_id').filtered('low_stock')
        bus = self.env['bus.bus'].sudo()
        for part in parts:
            bus._sendone(CHANNEL, 'taller/low_stock', {
                'id': part.id,
                'name': part.display_name,
                'stock': part.stock,
                'min_stock': part.min_stock,
                'by': self.env.uid,
            })
        return moves
