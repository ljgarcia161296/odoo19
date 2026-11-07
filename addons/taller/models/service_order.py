import re
from datetime import timedelta
from urllib.parse import quote

from odoo import models, fields, api
from odoo.exceptions import UserError


class ServiceOrder(models.Model):
    _name = 'service.order'
    _description = 'Orden de Servicio Técnico'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_received desc, id desc'

    name = fields.Char(string='Número de Orden', required=True, copy=False,
                       readonly=True, default='Nuevo')
    partner_id = fields.Many2one('res.partner', string='Cliente', tracking=True)
    customer_name = fields.Char(string='Nombre del cliente', compute='_compute_customer_name',
                                store=True, readonly=False, tracking=True)
    customer_phone = fields.Char(related='partner_id.phone', string='Teléfono')
    device_type = fields.Selection([
        ('computer', 'Computadora'),
        ('phone', 'Celular'),
        ('tablet', 'Tablet'),
        ('other', 'Otro'),
    ], string='Tipo de Equipo', default='computer', required=True)
    issue_description = fields.Text(string='Descripción del Problema')
    device_brand = fields.Char(string='Marca')
    device_model = fields.Char(string='Modelo')
    serial_number = fields.Char(string='N° de serie / IMEI')
    accessories = fields.Char(string='Accesorios recibidos')
    physical_condition = fields.Text(string='Estado físico al ingreso')
    status = fields.Selection([
        ('draft', 'Recibido'),
        ('diagnosing', 'En diagnóstico'),
        ('quote', 'Esperando aprobación'),
        ('repairing', 'En reparación'),
        ('done', 'Listo'),
        ('delivered', 'Entregado'),
        ('cancel', 'Cancelado'),
    ], string='Estado', default='draft', required=True, copy=False,
        tracking=True, group_expand='_expand_status')
    date_received = fields.Date(string='Fecha de Ingreso', default=fields.Date.today)
    date_finished = fields.Date(string='Fecha de Entrega')
    warranty_days = fields.Integer(
        string='Días de garantía',
        default=lambda self: int(self.env['ir.config_parameter'].sudo().get_param(
            'taller.default_warranty_days', 30) or 0))
    warranty_end = fields.Date(string='Garantía hasta', compute='_compute_warranty_end', store=True)
    warranty_status = fields.Selection([
        ('none', 'Sin garantía'),
        ('active', 'En garantía'),
        ('expired', 'Vencida'),
    ], string='Estado de garantía', compute='_compute_warranty_status')
    user_id = fields.Many2one('res.users', string='Técnico',
                              default=lambda self: self.env.user, tracking=True)

    currency_id = fields.Many2one('res.currency',
                                  default=lambda self: self.env.company.currency_id)
    line_ids = fields.One2many('service.order.line', 'order_id', string='Repuestos')
    stock_consumed = fields.Boolean(string='Stock descontado', copy=False, readonly=True)
    notify_customer = fields.Boolean(string='Avisar al cliente por correo', default=True)
    promise_date = fields.Date(string='Fecha prometida', tracking=True)
    date_ready = fields.Date(string='Fecha en que quedó listo', copy=False, readonly=True)
    is_late = fields.Boolean(string='Atrasada', compute='_compute_is_late')
    labor_cost = fields.Monetary(string='Mano de obra', currency_field='currency_id',
                                 compute='_compute_labor_cost', store=True, readonly=False)
    parts_total = fields.Monetary(string='Total repuestos', compute='_compute_totals',
                                  store=True, currency_field='currency_id')
    total = fields.Monetary(string='Total', compute='_compute_totals',
                            store=True, currency_field='currency_id')

    @api.model
    def _expand_status(self, groups, domain, order=None):
        return [key for key, _label in self._fields['status'].selection]

    @api.depends('line_ids.subtotal', 'labor_cost', 'no_charge')
    def _compute_totals(self):
        for order in self:
            parts = sum(order.line_ids.mapped('subtotal'))
            order.parts_total = parts
            order.total = 0.0 if order.no_charge else parts + order.labor_cost

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                vals['name'] = self.env['ir.sequence'].next_by_code('service.order') or 'Nuevo'
        return super().create(vals_list)

    @api.depends('partner_id.name')
    def _compute_customer_name(self):
        for order in self:
            if order.partner_id:
                order.customer_name = order.partner_id.name

    @api.depends('date_finished', 'warranty_days')
    def _compute_warranty_end(self):
        for order in self:
            if order.date_finished and order.warranty_days:
                order.warranty_end = order.date_finished + timedelta(days=order.warranty_days)
            else:
                order.warranty_end = False

    @api.depends('warranty_end')
    def _compute_warranty_status(self):
        today = fields.Date.context_today(self)
        for order in self:
            if not order.warranty_end:
                order.warranty_status = 'none'
            elif order.warranty_end >= today:
                order.warranty_status = 'active'
            else:
                order.warranty_status = 'expired'

    def _consume_parts(self):
        self.ensure_one()
        lines = self.line_ids.filtered('part_id')
        needed = {}
        for line in lines:
            needed[line.part_id] = needed.get(line.part_id, 0.0) + line.quantity
        short = ['%s: hay %g, se necesitan %g' % (p.display_name, p.stock, q)
                 for p, q in needed.items() if p.stock < q]
        if short:
            raise UserError('Stock insuficiente:\n' + '\n'.join(short))
        for line in lines:
            self.env['service.part.move'].create({
                'part_id': line.part_id.id,
                'move_type': 'out',
                'quantity': line.quantity,
                'order_id': self.id,
                'note': self.name,
            })
        self.stock_consumed = True

    def _return_parts(self):
        self.ensure_one()
        net = {}
        for move in self.env['service.part.move'].search([('order_id', '=', self.id)]):
            net[move.part_id] = net.get(move.part_id, 0.0) + move.signed_qty
        for part, qty in net.items():
            if qty < 0:
                self.env['service.part.move'].create({
                    'part_id': part.id,
                    'move_type': 'in',
                    'quantity': -qty,
                    'order_id': self.id,
                    'note': 'Devolución de %s' % self.name,
                })
        self.stock_consumed = False

    def write(self, vals):
        new_status = vals.get('status')
        if new_status in ('done', 'delivered'):
            for order in self.filtered(lambda o: not o.stock_consumed):
                order._consume_parts()
        elif new_status in ('draft', 'diagnosing', 'quote', 'repairing', 'cancel'):
            for order in self.filtered('stock_consumed'):
                order._return_parts()
        to_notify = self.env['service.order']
        if new_status == 'done':
            to_notify = self.filtered(
                lambda o: o.status != 'done' and o.notify_customer and o.partner_id.email)
        res = super().write(vals)
        if to_notify:
            template = self.env.ref('taller.mail_template_order_ready', raise_if_not_found=False)
            if template:
                for order in to_notify:
                    template.sudo().send_mail(order.id, force_send=False)
        if new_status == 'done':
            for order in self.filtered(lambda o: not o.date_ready):
                order.date_ready = fields.Date.today()
        if new_status == 'delivered':
            for order in self.filtered(lambda o: not o.date_finished):
                order.date_finished = fields.Date.today()
        return res

    @api.depends('promise_date', 'status')
    def _compute_is_late(self):
        today = fields.Date.context_today(self)
        for order in self:
            order.is_late = bool(
                order.promise_date and order.promise_date < today
                and order.status in ('draft', 'diagnosing', 'quote', 'repairing'))

    @api.model
    def _cron_unclaimed_orders(self):
        days = int(self.env['ir.config_parameter'].sudo().get_param('taller.unclaimed_days', 7))
        limit = fields.Date.today() - timedelta(days=days)
        managers = self.env.ref('taller.group_taller_manager').user_ids
        orders = self.search([('status', '=', 'done'), ('date_ready', '!=', False),
                              ('date_ready', '<=', limit)])
        for order in orders:
            pending = self.env['mail.activity'].search_count([
                ('res_model', '=', 'service.order'),
                ('res_id', '=', order.id),
                ('summary', '=', 'Equipo sin retirar'),
            ])
            if pending:
                continue
            note = 'La orden %s lleva más de %s días lista sin retirar.' % (order.name, days)
            for user in managers:
                order.activity_schedule('mail.mail_activity_data_todo',
                                        summary='Equipo sin retirar', note=note, user_id=user.id)

    def action_whatsapp(self):
        self.ensure_one()
        raw = self.partner_id.phone
        if not raw:
            raise UserError('El cliente no tiene celular ni teléfono cargado.')
        number = re.sub(r'\D', '', raw)
        if number.startswith('00'):
            number = number[2:]
        elif number.startswith('0'):
            number = '598' + number[1:]
        elif len(number) == 8 and number.startswith('9'):
            number = '598' + number
        name = self.partner_id.name or self.customer_name or ''
        device = ' '.join(filter(None, [self.device_brand, self.device_model])) or 'equipo'
        if self.status == 'done':
            text = 'Hola %s, su %s (orden %s) está listo para retirar. Total: %.2f' % (
                name, device, self.name, self.total)
        elif self.status == 'quote':
            self._ensure_token()
            text = ('Hola %s, el presupuesto de su %s (orden %s) es de %.2f. '
                    'Puede revisarlo y aprobarlo o rechazarlo desde este enlace: %s') % (
                name, device, self.name, self.total, self.public_url)
        elif self.status in ('diagnosing', 'repairing'):
            text = ('Hola %s, le escribimos por su %s (orden %s). Estamos trabajando en él '
                    'y le avisaremos cuando esté listo.') % (name, device, self.name)
        else:
            text = 'Hola %s, le escribimos por su orden %s.' % (name, self.name)
        return {
            'type': 'ir.actions.act_url',
            'url': 'https://wa.me/%s?text=%s' % (number, quote(text)),
            'target': 'new',
        }

    def action_start_diagnosis(self):
        self.write({'status': 'diagnosing'})

    def action_start_repair(self):
        self.write({'status': 'repairing'})

    def action_done(self):
        for order in self.filtered(lambda o: not o.stock_consumed):
            order._consume_parts()
        return self._action_done_status()

    def _action_done_status(self):
        self.write({'status': 'done'})

    def action_deliver(self):
        self.write({'status': 'delivered', 'date_finished': fields.Date.today()})

    def action_cancel(self):
        for order in self.filtered('stock_consumed'):
            order._return_parts()
        return self._action_cancel_status()

    def _action_cancel_status(self):
        self.write({'status': 'cancel'})

    def action_reset_draft(self):
        for order in self.filtered('stock_consumed'):
            order._return_parts()
        return self._action_reset_draft_status()

    def _action_reset_draft_status(self):
        self.write({'status': 'draft'})


class ServiceOrderLine(models.Model):
    _name = 'service.order.line'
    _description = 'Repuesto de Orden de Servicio'

    order_id = fields.Many2one('service.order', required=True, ondelete='cascade')
    part_id = fields.Many2one('service.part', string='Inventario', ondelete='restrict')
    name = fields.Char(string='Repuesto', required=True)
    quantity = fields.Float(string='Cantidad', default=1.0)
    currency_id = fields.Many2one(related='order_id.currency_id', store=True)
    unit_price = fields.Monetary(string='Precio unitario', currency_field='currency_id')
    subtotal = fields.Monetary(string='Subtotal', compute='_compute_subtotal',
                               store=True, currency_field='currency_id')

    @api.onchange('part_id')
    def _onchange_part_id(self):
        if self.part_id:
            self.name = self.part_id.name
            self.unit_price = self.part_id.price

    @api.depends('quantity', 'unit_price')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.unit_price
