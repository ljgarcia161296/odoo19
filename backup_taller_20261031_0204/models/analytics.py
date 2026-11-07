from odoo import models, fields, api


class ServiceChecklistItem(models.Model):
    _name = 'service.checklist.item'
    _description = 'Punto de checklist de ingreso'
    _order = 'sequence, id'

    name = fields.Char(string='Punto a revisar', required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    device_type = fields.Selection([
        ('computer', 'Computadora'),
        ('phone', 'Celular'),
        ('tablet', 'Tablet'),
        ('other', 'Otro'),
    ], string='Aplica a', help='Déjelo vacío para que aplique a todos los equipos.')


class ServiceOrderCheck(models.Model):
    _name = 'service.order.check'
    _description = 'Chequeo de ingreso'
    _order = 'sequence, id'

    order_id = fields.Many2one('service.order', required=True, ondelete='cascade')
    item_id = fields.Many2one('service.checklist.item', string='Punto', ondelete='set null')
    name = fields.Char(string='Punto a revisar', required=True)
    sequence = fields.Integer(default=10)
    result = fields.Selection([
        ('untested', 'Sin probar'),
        ('ok', 'Funciona'),
        ('fail', 'No funciona'),
        ('na', 'No aplica'),
    ], string='Resultado', default='untested', required=True)
    note = fields.Char(string='Nota')


class ServiceOrderLineCost(models.Model):
    _inherit = 'service.order.line'

    unit_cost = fields.Monetary(string='Costo unitario', compute='_compute_unit_cost',
                                store=True, readonly=False, currency_field='currency_id')
    cost_subtotal = fields.Monetary(string='Costo', compute='_compute_cost_subtotal',
                                    store=True, currency_field='currency_id')
    margin = fields.Monetary(string='Margen', compute='_compute_cost_subtotal',
                             store=True, currency_field='currency_id')

    @api.depends('part_id')
    def _compute_unit_cost(self):
        for line in self:
            if line.part_id:
                line.unit_cost = line.part_id.cost

    @api.depends('quantity', 'unit_cost', 'subtotal')
    def _compute_cost_subtotal(self):
        for line in self:
            line.cost_subtotal = line.quantity * line.unit_cost
            line.margin = line.subtotal - line.cost_subtotal


class ServiceOrderAnalytics(models.Model):
    _inherit = 'service.order'

    parts_cost = fields.Monetary(string='Costo de repuestos', compute='_compute_margin',
                                 store=True, currency_field='currency_id')
    margin = fields.Monetary(string='Margen', compute='_compute_margin',
                             store=True, currency_field='currency_id')
    days_to_finish = fields.Float(string='Días hasta la entrega', compute='_compute_productivity',
                                  store=True, aggregator='avg')
    delivered_flag = fields.Integer(string='Entregadas', compute='_compute_productivity',
                                    store=True)
    reentry_flag = fields.Integer(string='Reingresos por garantía',
                                  compute='_compute_productivity', store=True)
    check_ids = fields.One2many('service.order.check', 'order_id', string='Chequeo de ingreso')

    @api.depends('total', 'line_ids.cost_subtotal')
    def _compute_margin(self):
        for order in self:
            order.parts_cost = sum(order.line_ids.mapped('cost_subtotal'))
            order.margin = order.total - order.parts_cost

    @api.depends('status', 'date_received', 'date_finished', 'warranty_of_id')
    def _compute_productivity(self):
        for order in self:
            delivered = order.status == 'delivered'
            order.delivered_flag = 1 if delivered and not order.warranty_of_id else 0
            order.reentry_flag = 1 if order.warranty_of_id else 0
            if delivered and order.date_received and order.date_finished:
                order.days_to_finish = (order.date_finished - order.date_received).days
            else:
                order.days_to_finish = False

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        for order in orders:
            order._load_checklist()
        return orders

    def _load_checklist(self):
        self.ensure_one()
        items = self.env['service.checklist.item'].search(
            ['|', ('device_type', '=', False), ('device_type', '=', self.device_type)])
        existing = self.check_ids.mapped('item_id')
        for item in items - existing:
            self.env['service.order.check'].create({
                'order_id': self.id,
                'item_id': item.id,
                'name': item.name,
                'sequence': item.sequence,
            })

    def action_load_checklist(self):
        for order in self:
            order._load_checklist()