from odoo import models, api


class ServiceOrderSearch(models.Model):
    _inherit = 'service.order'

    @api.model
    def global_search(self, query):
        """Búsqueda rápida (Ctrl+K): órdenes y clientes. Respeta los permisos del usuario."""
        query = (query or '').strip()
        if len(query) < 2:
            return {'orders': [], 'partners': []}
        labels = dict(self._fields['status'].selection)
        orders = self.search([
            '|', '|', '|', '|',
            ('name', 'ilike', query),
            ('serial_number', 'ilike', query),
            ('customer_name', 'ilike', query),
            ('partner_id.name', 'ilike', query),
            ('partner_id.phone', 'ilike', query),
        ], order='id desc', limit=8)
        partners = self.env['res.partner'].search([
            '|', '|',
            ('name', 'ilike', query),
            ('phone', 'ilike', query),
            ('email', 'ilike', query),
        ], limit=5)
        return {
            'orders': [{
                'id': o.id,
                'name': o.name,
                'customer': o.partner_id.name or o.customer_name or '',
                'device': ' '.join(filter(None, [o.device_brand, o.device_model])),
                'serial': o.serial_number or '',
                'status': o.status,
                'status_label': labels.get(o.status, o.status),
            } for o in orders],
            'partners': [{'id': p.id, 'name': p.name, 'phone': p.phone or ''} for p in partners],
        }
