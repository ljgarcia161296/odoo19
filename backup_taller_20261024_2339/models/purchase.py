from odoo import models, fields, api
from odoo.exceptions import UserError


class ServicePurchase(models.Model):
    _name = 'service.purchase'
    _description = 'Compra de repuestos'
    _inherit = ['mail.thread']
    _order = 'date desc, id desc'

    name = fields.Char(string='Número', default='Nuevo', copy=False, readonly=True)
    partner_id = fields.Many2one('res.partner', string='Proveedor', tracking=True)
    date = fields.Date(string='Fecha', default=fields.Date.today)
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('ordered', 'Pedida'),
        ('received', 'Recibida'),
        ('cancel', 'Cancelada'),
    ], string='Estado', default='draft', copy=False, tracking=True)
    currency_id = fields.Many2one('res.currency',
                                  default=lambda self: self.env.company.currency_id)
    line_ids = fields.One2many('service.purchase.line', 'purchase_id', string='Repuestos')
    total = fields.Monetary(string='Total', compute='_compute_total', store=True,
                            currency_field='currency_id')
    note = fields.Text(string='Notas')

    @api.depends('line_ids.subtotal')
    def _compute_total(self):
        for purchase in self:
            purchase.total = sum(purchase.line_ids.mapped('subtotal'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                vals['name'] = self.env['ir.sequence'].next_by_code('service.purchase') or 'Nuevo'
        return super().create(vals_list)

    def action_order(self):
        for purchase in self:
            if not purchase.line_ids:
                raise UserError('Agregue al menos un repuesto a la compra.')
        self.write({'state': 'ordered'})

    def action_receive(self):
        for purchase in self:
            if purchase.state == 'received':
                continue
            if not purchase.line_ids:
                raise UserError('Agregue al menos un repuesto a la compra.')
            for line in purchase.line_ids:
                self.env['service.part.move'].create({
                    'part_id': line.part_id.id,
                    'move_type': 'in',
                    'quantity': line.quantity,
                    'note': 'Compra %s' % purchase.name,
                })
            purchase.state = 'received'

    def action_cancel(self):
        if self.filtered(lambda p: p.state == 'received'):
            raise UserError('Una compra recibida no se puede cancelar.')
        self.write({'state': 'cancel'})

    def action_draft(self):
        self.write({'state': 'draft'})


class ServicePurchaseLine(models.Model):
    _name = 'service.purchase.line'
    _description = 'Línea de compra de repuestos'

    purchase_id = fields.Many2one('service.purchase', required=True, ondelete='cascade')
    part_id = fields.Many2one('service.part', string='Repuesto', required=True)
    quantity = fields.Float(string='Cantidad', default=1.0)
    currency_id = fields.Many2one(related='purchase_id.currency_id', store=True)
    unit_cost = fields.Monetary(string='Costo unitario', currency_field='currency_id')
    subtotal = fields.Monetary(string='Subtotal', compute='_compute_subtotal',
                               store=True, currency_field='currency_id')

    @api.onchange('part_id')
    def _onchange_part_id(self):
        if self.part_id:
            self.unit_cost = self.part_id.cost

    @api.depends('quantity', 'unit_cost')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.unit_cost


class ServicePartAlerts(models.Model):
    _name = 'service.part'
    _description = 'Repuesto de inventario'
    _inherit = ['service.part', 'mail.thread', 'mail.activity.mixin']

    @api.model
    def _cron_low_stock_activities(self):
        managers = self.env.ref('taller.group_taller_manager').user_ids
        for part in self.search([('low_stock', '=', True)]):
            pending = self.env['mail.activity'].search_count([
                ('res_model', '=', 'service.part'),
                ('res_id', '=', part.id),
                ('summary', '=', 'Reponer stock'),
            ])
            if pending:
                continue
            note = '%s: hay %g, el mínimo es %g.' % (part.display_name, part.stock, part.min_stock)
            for user in managers:
                part.activity_schedule('mail.mail_activity_data_todo',
                                       summary='Reponer stock', note=note, user_id=user.id)

    def action_create_purchase(self):
        lines = []
        for part in self:
            qty = max(part.min_stock * 2 - part.stock, 1.0)
            lines.append((0, 0, {'part_id': part.id, 'quantity': qty, 'unit_cost': part.cost}))
        purchase = self.env['service.purchase'].create({'line_ids': lines})
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'service.purchase',
            'res_id': purchase.id,
            'view_mode': 'form',
        }

    @api.model
    def action_suggest_purchase(self):
        parts = self.search([('low_stock', '=', True)])
        if not parts:
            raise UserError('No hay repuestos con stock bajo.')
        return parts.action_create_purchase()