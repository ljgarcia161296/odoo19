from odoo import models, fields


class ResPartner(models.Model):
    _inherit = 'res.partner'

    service_order_count = fields.Integer(string='Órdenes de servicio',
                                         compute='_compute_service_order_count')

    def _compute_service_order_count(self):
        data = self.env['service.order'].sudo()._read_group(
            [('partner_id', 'in', self.ids)], ['partner_id'], ['__count'])
        counts = {partner.id: count for partner, count in data}
        for partner in self:
            partner.service_order_count = counts.get(partner.id, 0)

    def action_view_service_orders(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Órdenes de Servicio',
            'res_model': 'service.order',
            'view_mode': 'list,form',
            'domain': [('partner_id', '=', self.id)],
            'context': {'default_partner_id': self.id},
        }