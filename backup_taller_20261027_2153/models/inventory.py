from odoo import models, fields, api
from odoo.exceptions import ValidationError


class ServicePart(models.Model):
    _name = 'service.part'
    _description = 'Repuesto de inventario'
    _order = 'name'

    name = fields.Char(string='Repuesto', required=True)
    code = fields.Char(string='Código', copy=False)
    active = fields.Boolean(default=True)
    currency_id = fields.Many2one('res.currency',
                                  default=lambda self: self.env.company.currency_id)
    cost = fields.Monetary(string='Costo', currency_field='currency_id')
    price = fields.Monetary(string='Precio de venta', currency_field='currency_id')
    min_stock = fields.Float(string='Stock mínimo')
    move_ids = fields.One2many('service.part.move', 'part_id', string='Movimientos')
    stock = fields.Float(string='Stock', compute='_compute_stock', store=True)
    low_stock = fields.Boolean(string='Stock bajo', compute='_compute_low_stock', store=True)

    _rec_names_search = ['name', 'code']

    _code_uniq = models.Constraint('unique(code)', 'El código del repuesto ya existe.')

    @api.depends('move_ids.signed_qty')
    def _compute_stock(self):
        for part in self:
            part.stock = sum(part.move_ids.mapped('signed_qty'))

    @api.depends('stock', 'min_stock')
    def _compute_low_stock(self):
        for part in self:
            part.low_stock = bool(part.min_stock) and part.stock <= part.min_stock

    @api.depends('code', 'name')
    def _compute_display_name(self):
        for part in self:
            part.display_name = '[%s] %s' % (part.code, part.name) if part.code else part.name


class ServicePartMove(models.Model):
    _name = 'service.part.move'
    _description = 'Movimiento de stock'
    _order = 'date desc, id desc'

    part_id = fields.Many2one('service.part', string='Repuesto', required=True,
                              ondelete='restrict')
    date = fields.Datetime(string='Fecha', default=fields.Datetime.now, required=True)
    move_type = fields.Selection([
        ('in', 'Entrada'),
        ('out', 'Salida'),
        ('adjust', 'Ajuste'),
    ], string='Tipo', default='in', required=True)
    quantity = fields.Float(string='Cantidad', required=True,
                            help='Entradas y salidas en positivo. En un ajuste, use un número negativo para restar.')
    signed_qty = fields.Float(string='Variación', compute='_compute_signed_qty', store=True)
    order_id = fields.Many2one('service.order', string='Orden', ondelete='set null')
    note = fields.Char(string='Nota')

    @api.depends('move_type', 'quantity')
    def _compute_signed_qty(self):
        for move in self:
            move.signed_qty = -move.quantity if move.move_type == 'out' else move.quantity

    @api.constrains('move_type', 'quantity')
    def _check_quantity(self):
        for move in self:
            if move.move_type in ('in', 'out') and move.quantity <= 0:
                raise ValidationError('En entradas y salidas la cantidad debe ser mayor que cero.')