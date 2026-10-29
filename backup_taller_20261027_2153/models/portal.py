import re
import secrets
from urllib.parse import quote

from odoo import models, fields, api
from odoo.exceptions import UserError


class ServiceOrderPortal(models.Model):
    _inherit = 'service.order'

    access_token = fields.Char(string='Token de seguimiento', copy=False, index=True,
                               readonly=True)
    public_url = fields.Char(string='Enlace de seguimiento', compute='_compute_public_url')
    public_qr_value = fields.Char(compute='_compute_public_url')
    rating = fields.Selection([
        ('1', '1 - Muy mala'),
        ('2', '2 - Mala'),
        ('3', '3 - Regular'),
        ('4', '4 - Buena'),
        ('5', '5 - Excelente'),
    ], string='Valoración', copy=False, tracking=True)
    rating_comment = fields.Text(string='Comentario del cliente', copy=False)
    rating_date = fields.Date(string='Fecha de valoración', copy=False)
    rating_value = fields.Integer(string='Puntaje', compute='_compute_rating_value',
                                  store=True, aggregator='avg')

    _access_token_uniq = models.Constraint(
        'unique(access_token)', 'El token de seguimiento debe ser único.')

    @api.depends('access_token')
    def _compute_public_url(self):
        base = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        for order in self:
            url = '%s/taller/estado/%s' % (base, order.access_token) if order.access_token else ''
            order.public_url = url
            order.public_qr_value = quote(url, safe='') if url else ''

    @api.depends('rating')
    def _compute_rating_value(self):
        for order in self:
            order.rating_value = int(order.rating) if order.rating else 0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals.setdefault('access_token', secrets.token_urlsafe(16))
        return super().create(vals_list)

    def write(self, vals):
        res = super().write(vals)
        if vals.get('rating') in ('1', '2'):
            managers = self.env.ref('taller.group_taller_manager').user_ids
            for order in self:
                note = 'El cliente valoró la orden %s con %s.' % (order.name, order.rating)
                for user in (order.user_id | managers):
                    order.activity_schedule('mail.mail_activity_data_todo',
                                            summary='Valoración baja', note=note,
                                            user_id=user.id)
        return res

    def _ensure_token(self):
        for order in self.filtered(lambda o: not o.access_token):
            order.access_token = secrets.token_urlsafe(16)
        return True

    @staticmethod
    def _whatsapp_number(raw):
        number = re.sub(r'\D', '', raw or '')
        if number.startswith('00'):
            number = number[2:]
        elif number.startswith('0'):
            number = '598' + number[1:]
        elif len(number) == 8 and number.startswith('9'):
            number = '598' + number
        return number

    def action_whatsapp_link(self):
        self.ensure_one()
        raw = self.partner_id.phone
        if not raw:
            raise UserError('El cliente no tiene celular ni teléfono cargado.')
        self._ensure_token()
        number = self._whatsapp_number(raw)
        name = self.partner_id.name or self.customer_name or ''
        if self.status == 'delivered':
            text = ('Hola %s, gracias por confiar en nosotros. ¿Nos cuenta cómo fue su '
                    'experiencia con la orden %s? Solo toma un minuto: %s') % (
                name, self.name, self.public_url)
        else:
            text = 'Hola %s, puede seguir el estado de su equipo (orden %s) aquí: %s' % (
                name, self.name, self.public_url)
        return {
            'type': 'ir.actions.act_url',
            'url': 'https://wa.me/%s?text=%s' % (number, quote(text)),
            'target': 'new',
        }