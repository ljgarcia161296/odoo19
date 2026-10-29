from datetime import timedelta

from odoo import models, fields, api


class ServicePartSupplier(models.Model):
    _name = 'service.part.supplier'
    _description = 'Precio de proveedor por repuesto'
    _order = 'sequence, price, id'

    part_id = fields.Many2one('service.part', string='Repuesto', required=True,
                              ondelete='cascade')
    partner_id = fields.Many2one('res.partner', string='Proveedor', required=True)
    sequence = fields.Integer(default=10,
                              help='El primero de la lista es el proveedor preferido.')
    supplier_code = fields.Char(string='Código del proveedor')
    currency_id = fields.Many2one(related='part_id.currency_id', store=True)
    price = fields.Monetary(string='Precio de compra', currency_field='currency_id')
    lead_days = fields.Integer(string='Días de entrega')
    last_update = fields.Date(string='Último precio', default=fields.Date.today)

    _part_partner_uniq = models.Constraint(
        'unique(part_id, partner_id)',
        'Ese proveedor ya está cargado para este repuesto.')

    def write(self, vals):
        if 'price' in vals and 'last_update' not in vals:
            vals = dict(vals, last_update=fields.Date.today())
        return super().write(vals)


class ServicePartSuppliers(models.Model):
    _inherit = 'service.part'

    supplier_ids = fields.One2many('service.part.supplier', 'part_id', string='Proveedores')

    def action_create_purchase(self):
        groups = {}
        for part in self:
            info = part.supplier_ids[:1]
            price = info.price if info else part.cost
            qty = max(part.min_stock * 2 - part.stock, 1.0)
            groups.setdefault(info.partner_id.id or False, []).append(
                (0, 0, {'part_id': part.id, 'quantity': qty, 'unit_cost': price}))
        purchases = self.env['service.purchase']
        for partner_id, lines in groups.items():
            purchases |= self.env['service.purchase'].create(
                {'partner_id': partner_id, 'line_ids': lines})
        if len(purchases) == 1:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'service.purchase',
                'res_id': purchases.id,
                'view_mode': 'form',
            }
        return {
            'type': 'ir.actions.act_window',
            'name': 'Compras sugeridas',
            'res_model': 'service.purchase',
            'view_mode': 'list,form',
            'domain': [('id', 'in', purchases.ids)],
        }


class ServicePurchaseSuppliers(models.Model):
    _inherit = 'service.purchase'

    def action_receive(self):
        res = super().action_receive()
        Supplier = self.env['service.part.supplier'].sudo()
        for purchase in self.filtered(lambda p: p.state == 'received' and p.partner_id):
            for line in purchase.line_ids:
                if not line.unit_cost:
                    continue
                info = Supplier.search([
                    ('part_id', '=', line.part_id.id),
                    ('partner_id', '=', purchase.partner_id.id),
                ], limit=1)
                if info:
                    info.write({'price': line.unit_cost})
                else:
                    Supplier.create({
                        'part_id': line.part_id.id,
                        'partner_id': purchase.partner_id.id,
                        'price': line.unit_cost,
                    })
        return res


class ServicePurchaseLineSuppliers(models.Model):
    _inherit = 'service.purchase.line'

    @api.onchange('part_id')
    def _onchange_part_id(self):
        super()._onchange_part_id()
        partner = self.purchase_id.partner_id
        if self.part_id and partner:
            info = self.part_id.supplier_ids.filtered(lambda s: s.partner_id == partner)[:1]
            if info:
                self.unit_cost = info.price


class ServiceOrderTanda5(models.Model):
    _inherit = 'service.order'

    order_qty = fields.Integer(string='Órdenes', default=1)
    recurrent_flag = fields.Integer(string='Reincidencia', compute='_compute_recurrent',
                                    store=True)
    history_count = fields.Integer(string='Historial del equipo',
                                   compute='_compute_history_count')
    last_quote_followup = fields.Date(string='Último seguimiento de presupuesto', copy=False)

    @api.depends('serial_number', 'date_received', 'warranty_of_id')
    def _compute_recurrent(self):
        days = int(self.env['ir.config_parameter'].sudo().get_param('taller.recurrence_days', 90))
        for order in self:
            flag = 0
            serial = (order.serial_number or '').strip()
            if serial and order.date_received and not order.warranty_of_id and order.id:
                limit = order.date_received - timedelta(days=days)
                others = self.search_count([
                    ('serial_number', '=ilike', serial),
                    ('id', '!=', order.id),
                    ('status', '=', 'delivered'),
                    ('date_finished', '>=', limit),
                    ('date_finished', '<=', order.date_received),
                ])
                flag = 1 if others else 0
            order.recurrent_flag = flag

    def _compute_history_count(self):
        for order in self:
            serial = (order.serial_number or '').strip()
            if serial and order.id:
                order.history_count = self.search_count([
                    ('serial_number', '=ilike', serial),
                    ('id', '!=', order.id),
                ])
            else:
                order.history_count = 0

    def action_view_device_history(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Historial del equipo',
            'res_model': 'service.order',
            'view_mode': 'list,form',
            'domain': [('serial_number', '=ilike', (self.serial_number or '').strip()),
                       ('id', '!=', self.id)],
        }

    @api.model
    def _cron_quote_followup(self):
        days = int(self.env['ir.config_parameter'].sudo().get_param('taller.quote_followup_days', 3))
        today = fields.Date.today()
        limit = today - timedelta(days=days)
        managers = self.env.ref('taller.group_taller_manager').user_ids
        orders = self.search([('status', '=', 'quote'), ('quote_date', '!=', False),
                              ('quote_date', '<=', limit)])
        for order in orders:
            if order.last_quote_followup and order.last_quote_followup > limit:
                continue
            note = ('El presupuesto %s lleva más de %s días sin respuesta. '
                    'Use el botón WhatsApp para consultarle al cliente.') % (order.name, days)
            for user in (order.user_id or managers):
                order.activity_schedule('mail.mail_activity_data_todo',
                                        summary='Seguir presupuesto', note=note, user_id=user.id)
            order.last_quote_followup = today