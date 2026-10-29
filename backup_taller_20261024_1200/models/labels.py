from urllib.parse import quote

from odoo import models, fields, api


class ServiceOrderPhoto(models.Model):
    _name = 'service.order.photo'
    _description = 'Foto de orden de servicio'
    _order = 'id'

    order_id = fields.Many2one('service.order', required=True, ondelete='cascade')
    name = fields.Char(string='Descripción')
    stage = fields.Selection([
        ('intake', 'Ingreso'),
        ('delivery', 'Entrega'),
    ], string='Momento', default='intake', required=True)
    image = fields.Image(string='Foto', max_width=800, max_height=800,
                         attachment=True, required=True)


class ServiceOrderLabels(models.Model):
    _inherit = 'service.order'

    photo_ids = fields.One2many('service.order.photo', 'order_id', string='Fotos')
    delivery_signature = fields.Image(string='Firma de quien retira', copy=False,
                                      attachment=True, max_width=600, max_height=300)
    delivery_signed_by = fields.Char(string='Retiró', copy=False)
    qr_value = fields.Char(string='Valor del QR', compute='_compute_qr_value')

    def _compute_qr_value(self):
        base = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        for order in self:
            url = '%s/web#id=%s&model=service.order&view_type=form' % (base, order.id)
            order.qr_value = quote(url, safe='')