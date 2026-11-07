from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError


class ServiceCatalog(models.Model):
    _name = 'service.catalog'
    _description = 'Servicio del catálogo'
    _order = 'name'

    name = fields.Char(string='Servicio', required=True)
    active = fields.Boolean(default=True)
    currency_id = fields.Many2one('res.currency',
                                  default=lambda self: self.env.company.currency_id)
    price = fields.Monetary(string='Mano de obra', currency_field='currency_id')


class ServicePayment(models.Model):
    _name = 'service.payment'
    _description = 'Pago de orden de servicio'
    _order = 'date desc, id desc'

    order_id = fields.Many2one('service.order', string='Orden', required=True,
                               ondelete='cascade')
    date = fields.Date(string='Fecha', default=fields.Date.today, required=True)
    currency_id = fields.Many2one(related='order_id.currency_id', store=True)
    amount = fields.Monetary(string='Monto', required=True, currency_field='currency_id')
    method = fields.Selection([
        ('cash', 'Efectivo'),
        ('transfer', 'Transferencia'),
        ('card', 'Tarjeta'),
        ('other', 'Otro'),
    ], string='Forma de pago', default='cash', required=True)
    note = fields.Char(string='Nota')

    @api.constrains('amount')
    def _check_amount(self):
        for payment in self:
            if payment.amount <= 0:
                raise ValidationError('El monto del pago debe ser mayor que cero.')


class ServiceOrderExt(models.Model):
    _inherit = 'service.order'

    quote_date = fields.Date(string='Fecha del presupuesto', copy=False, readonly=True)
    approved_date = fields.Date(string='Fecha de aprobación', copy=False, readonly=True)

    service_ids = fields.Many2many('service.catalog', string='Servicios')

    payment_ids = fields.One2many('service.payment', 'order_id', string='Pagos')
    paid_total = fields.Monetary(string='Pagado', compute='_compute_balance', store=True,
                                 currency_field='currency_id')
    balance = fields.Monetary(string='Saldo', compute='_compute_balance', store=True,
                              currency_field='currency_id')

    no_charge = fields.Boolean(string='Sin cargo (garantía)', copy=False)
    warranty_of_id = fields.Many2one('service.order', string='Garantía de',
                                     copy=False, readonly=True)
    reentry_count = fields.Integer(string='Reingresos', compute='_compute_reentry_count')

    @api.depends('service_ids')
    def _compute_labor_cost(self):
        for order in self:
            if order.service_ids:
                order.labor_cost = sum(order.service_ids.mapped('price'))

    @api.depends('payment_ids.amount', 'total')
    def _compute_balance(self):
        for order in self:
            paid = sum(order.payment_ids.mapped('amount'))
            order.paid_total = paid
            order.balance = order.total - paid

    def _compute_reentry_count(self):
        for order in self:
            order.reentry_count = self.search_count([('warranty_of_id', '=', order.id)])

    def action_send_quote(self):
        for order in self:
            if not order.total:
                raise UserError('Cargue repuestos o mano de obra antes de enviar el presupuesto.')
        self.write({'status': 'quote', 'quote_date': fields.Date.today()})

    def action_approve_quote(self):
        self.write({'status': 'repairing', 'approved_date': fields.Date.today()})
        for order in self:
            order.message_post(body='Presupuesto aprobado por el cliente.')

    def action_reject_quote(self):
        self.write({'status': 'cancel'})
        for order in self:
            order.message_post(body='Presupuesto rechazado por el cliente.')

    def action_warranty_reentry(self):
        self.ensure_one()
        if self.warranty_status != 'active':
            raise UserError('La garantía de esta orden está vencida o no tiene días de garantía. '
                            'Cree una orden nueva si corresponde cobrar.')
        new = self.create({
            'partner_id': self.partner_id.id,
            'customer_name': self.customer_name,
            'device_type': self.device_type,
            'device_brand': self.device_brand,
            'device_model': self.device_model,
            'serial_number': self.serial_number,
            'user_id': self.user_id.id,
            'issue_description': 'Reingreso por garantía de %s.\nProblema original: %s' % (
                self.name, self.issue_description or ''),
            'warranty_of_id': self.id,
            'no_charge': True,
            'warranty_days': 0,
        })
        self.message_post(body='Reingreso por garantía: %s' % new.name)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'service.order',
            'res_id': new.id,
            'view_mode': 'form',
        }

    def action_view_reentries(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Reingresos por garantía',
            'res_model': 'service.order',
            'view_mode': 'list,form',
            'domain': [('warranty_of_id', '=', self.id)],
        }