from urllib.parse import quote

from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
from odoo.tools import html2plaintext

SALE_METHODS = [
    ('cash', 'Efectivo'),
    ('transfer', 'Transferencia'),
    ('card', 'Tarjeta'),
    ('other', 'Otro'),
]


class TallerSale(models.Model):
    _name = 'taller.sale'
    _description = 'Venta de mostrador'
    _order = 'date desc, id desc'

    name = fields.Char(string='Número', default='Nueva', copy=False, readonly=True)
    date = fields.Date(string='Fecha', default=fields.Date.today, required=True)
    customer = fields.Char(string='Cliente')
    method = fields.Selection(SALE_METHODS, string='Forma de pago', default='cash', required=True)
    state = fields.Selection([('done', 'Cobrada'), ('cancel', 'Anulada')], default='done', required=True)
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)
    line_ids = fields.One2many('taller.sale.line', 'sale_id', string='Detalle')
    total = fields.Monetary(string='Total', compute='_compute_total', store=True, currency_field='currency_id')

    @api.depends('line_ids.subtotal')
    def _compute_total(self):
        for sale in self:
            sale.total = sum(sale.line_ids.mapped('subtotal'))

    @api.model_create_multi
    def create(self, vals_list):
        sales = super().create(vals_list)
        for sale in sales:
            sale.name = 'V-%05d' % sale.id
        return sales


class TallerSaleLine(models.Model):
    _name = 'taller.sale.line'
    _description = 'Línea de venta de mostrador'

    sale_id = fields.Many2one('taller.sale', required=True, ondelete='cascade')
    part_id = fields.Many2one('service.part', string='Repuesto', ondelete='restrict')
    name = fields.Char(string='Descripción', required=True)
    quantity = fields.Float(string='Cantidad', default=1.0)
    currency_id = fields.Many2one(related='sale_id.currency_id', store=True)
    unit_price = fields.Monetary(string='Precio', currency_field='currency_id')
    unit_cost = fields.Monetary(string='Costo', currency_field='currency_id')
    subtotal = fields.Monetary(string='Subtotal', compute='_compute_subtotal', store=True,
                               currency_field='currency_id')

    @api.depends('quantity', 'unit_price')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.unit_price

    @api.constrains('quantity', 'unit_price')
    def _check_values(self):
        for line in self:
            if line.quantity <= 0 or line.unit_price < 0:
                raise ValidationError('Cantidad y precio deben ser válidos.')


class ServiceOrderMostrador(models.Model):
    _inherit = 'service.order'

    # ------------------------------------------------------------------ venta de mostrador
    @api.model
    def venta_parts(self, query=''):
        query = (query or '').strip()
        domain = ['|', ('name', 'ilike', query), ('code', 'ilike', query)] if query else []
        parts = self.env['service.part'].search(domain, limit=15, order='name')
        return [{'id': p.id, 'name': p.display_name, 'price': p.price, 'stock': p.stock} for p in parts]

    @api.model
    def venta_create(self, items, method, customer=''):
        methods = dict(SALE_METHODS)
        if method not in methods:
            raise UserError('Elija la forma de pago.')
        if not items:
            raise UserError('Agregue al menos un artículo.')
        Part = self.env['service.part']
        lines = []
        wanted = {}
        for item in items:
            qty = float(item.get('qty') or 0)
            price = float(item.get('price') or 0)
            name = (item.get('name') or '').strip()
            if qty <= 0 or price < 0 or not name:
                raise UserError('Revise cantidad, precio y descripción de cada artículo.')
            part = Part.browse(int(item['part_id'])).exists() if item.get('part_id') else Part
            if part:
                wanted[part.id] = wanted.get(part.id, 0) + qty
            lines.append((0, 0, {
                'part_id': part.id or False, 'name': name[:120], 'quantity': qty,
                'unit_price': price, 'unit_cost': part.cost if part else 0.0,
            }))
        for part_id, qty in wanted.items():
            part = Part.browse(part_id)
            if part.stock < qty:
                raise UserError('Stock insuficiente de %s: hay %g y se piden %g.' % (
                    part.display_name, part.stock, qty))
        sale = self.env['taller.sale'].create({
            'method': method, 'customer': (customer or '')[:80], 'line_ids': lines,
        })
        for line in sale.line_ids.filtered('part_id'):
            self.env['service.part.move'].sudo().create({
                'part_id': line.part_id.id, 'move_type': 'out', 'quantity': line.quantity,
                'note': 'Venta %s' % sale.name,
            })
        return {'id': sale.id, 'name': sale.name, 'total': sale.total}

    @api.model
    def venta_today(self):
        today = fields.Date.context_today(self)
        sales = self.env['taller.sale'].search([('date', '=', today)], order='id desc')
        labels = dict(SALE_METHODS)
        return {
            'symbol': self.env.company.currency_id.symbol or '',
            'is_manager': self.env.user.has_group('taller.group_taller_manager'),
            'sales': [{
                'id': s.id, 'name': s.name, 'customer': s.customer or '', 'state': s.state,
                'method': labels[s.method], 'total': s.total,
                'detail': ', '.join('%g x %s' % (l.quantity, l.name) for l in s.line_ids),
            } for s in sales],
            'total': sum(s.total for s in sales if s.state == 'done'),
        }

    @api.model
    def venta_cancel(self, sale_id):
        if not self.env.user.has_group('taller.group_taller_manager'):
            raise UserError('Solo un responsable puede anular ventas.')
        sale = self.env['taller.sale'].browse(int(sale_id)).exists()
        if not sale or sale.state == 'cancel':
            raise UserError('La venta ya fue anulada.')
        for line in sale.line_ids.filtered('part_id'):
            self.env['service.part.move'].sudo().create({
                'part_id': line.part_id.id, 'move_type': 'in', 'quantity': line.quantity,
                'note': 'Anulación %s' % sale.name,
            })
        sale.state = 'cancel'
        return True

    # ------------------------------------------------------------------ inventario ágil
    @api.model
    def inv_data(self, search='', only_low=False):
        Part = self.env['service.part']
        is_manager = self.env.user.has_group('taller.group_taller_manager')
        domain = []
        search = (search or '').strip()
        if search:
            domain += ['|', ('name', 'ilike', search), ('code', 'ilike', search)]
        if only_low:
            domain.append(('low_stock', '=', True))
        parts = Part.search(domain, limit=200, order='low_stock desc, name')
        incoming = {}
        for line in self.env['service.purchase.line'].search([('purchase_id.state', '=', 'ordered'),
                                                              ('part_id', 'in', parts.ids)]):
            incoming[line.part_id.id] = incoming.get(line.part_id.id, 0) + line.quantity
        all_parts = Part.search([])
        return {
            'symbol': self.env.company.currency_id.symbol or '',
            'is_manager': is_manager,
            'count': len(all_parts),
            'low': len(all_parts.filtered('low_stock')),
            'value': sum(p.stock * p.cost for p in all_parts) if is_manager else 0,
            'parts': [{
                'id': p.id, 'name': p.name, 'code': p.code or '', 'stock': p.stock,
                'min': p.min_stock, 'low': p.low_stock, 'cost': p.cost if is_manager else 0,
                'price': p.price, 'incoming': incoming.get(p.id, 0),
            } for p in parts],
        }

    @api.model
    def inv_adjust(self, part_id, delta, note=''):
        part = self.env['service.part'].browse(int(part_id)).exists()
        delta = float(delta or 0)
        if not part or not delta:
            raise UserError('Indique cuánto sumar o restar.')
        if part.stock + delta < 0:
            raise UserError('El stock no puede quedar negativo.')
        self.env['service.part.move'].create({
            'part_id': part.id, 'move_type': 'adjust', 'quantity': delta,
            'note': (note or 'Ajuste rápido')[:120],
        })
        return True

    @api.model
    def inv_write(self, part_id, vals):
        if not self.env.user.has_group('taller.group_taller_manager'):
            raise UserError('Solo un responsable puede editar precios y mínimos.')
        part = self.env['service.part'].browse(int(part_id)).exists()
        clean = {k: float(v or 0) for k, v in (vals or {}).items() if k in ('min_stock', 'price', 'cost')}
        if part and clean:
            part.write(clean)
        return True

    @api.model
    def inv_create_part(self, name, code, cost, price, min_stock, stock):
        if not self.env.user.has_group('taller.group_taller_manager'):
            raise UserError('Solo un responsable puede crear repuestos.')
        name = (name or '').strip()
        if not name:
            raise UserError('Escriba el nombre del repuesto.')
        vals = {'name': name, 'cost': float(cost or 0), 'price': float(price or 0),
                'min_stock': float(min_stock or 0)}
        if (code or '').strip():
            vals['code'] = code.strip()
        part = self.env['service.part'].create(vals)
        if float(stock or 0) > 0:
            self.env['service.part.move'].create({
                'part_id': part.id, 'move_type': 'in', 'quantity': float(stock), 'note': 'Stock inicial',
            })
        return part.id

    @api.model
    def inv_make_purchase(self, part_ids):
        if not self.env.user.has_group('taller.group_taller_manager'):
            raise UserError('Solo un responsable puede crear pedidos.')
        parts = self.env['service.part'].browse([int(i) for i in part_ids]).exists()
        if not parts:
            parts = self.env['service.part'].search([('low_stock', '=', True)])
        if not parts:
            raise UserError('No hay repuestos con stock bajo.')
        return parts.action_create_purchase()

    # ------------------------------------------------------------------ clientes
    @api.model
    def clientes_list(self, search=''):
        Partner = self.env['res.partner']
        search = (search or '').strip()
        if search:
            partners = Partner.search(['|', '|', ('name', 'ilike', search), ('phone', 'ilike', search),
                                       ('email', 'ilike', search)], limit=60)
        else:
            top = self.search([('partner_id', '!=', False)], order='id desc', limit=300).mapped('partner_id')
            partners = top[:60]
        orders = self.search([('partner_id', 'in', partners.ids)])
        stats = {}
        for order in orders:
            st = stats.setdefault(order.partner_id.id, {'n': 0, 'balance': 0.0, 'last': False})
            st['n'] += 1
            st['balance'] += order.balance if order.status in ('done', 'delivered') else 0
            if order.date_received and (not st['last'] or order.date_received > st['last']):
                st['last'] = order.date_received
        rows = [{
            'id': p.id, 'name': p.name, 'phone': p.phone or '',
            'orders': stats.get(p.id, {}).get('n', 0),
            'balance': stats.get(p.id, {}).get('balance', 0.0),
            'last': stats[p.id]['last'].strftime('%d/%m/%Y') if p.id in stats and stats[p.id]['last'] else '',
        } for p in partners]
        return {'symbol': self.env.company.currency_id.symbol or '', 'rows': rows}

    @api.model
    def cliente_get(self, partner_id):
        partner = self.env['res.partner'].browse(int(partner_id)).exists()
        if not partner:
            raise UserError('El cliente ya no existe.')
        labels = dict(self._fields['status'].selection)
        orders = self.search([('partner_id', '=', partner.id)], order='id desc', limit=100)
        devices = {}
        for order in orders:
            key = ' '.join(filter(None, [order.device_brand, order.device_model])) or 'Equipo'
            dev = devices.setdefault(key, {'name': key, 'count': 0, 'serial': order.serial_number or ''})
            dev['count'] += 1
        number = self._whatsapp_number(partner.phone) if partner.phone else ''
        text = 'Hola %s, le escribimos del taller.' % partner.name
        return {
            'id': partner.id,
            'name': partner.name,
            'phone': partner.phone or '',
            'email': partner.email or '',
            'street': partner.street or '',
            'city': partner.city or '',
            'vat': partner.vat or '',
            'comment': html2plaintext(partner.comment or '').strip(),
            'symbol': self.env.company.currency_id.symbol or '',
            'count': len(orders),
            'billed': sum(orders.filtered(lambda o: o.status != 'cancel').mapped('total')),
            'balance': sum(o.balance for o in orders if o.status in ('done', 'delivered')),
            'wa_url': ('https://wa.me/%s?text=%s' % (number, quote(text))) if number else '',
            'tel': ('tel:+%s' % number) if number else '',
            'devices': sorted(devices.values(), key=lambda d: -d['count']),
            'orders': [{
                'id': o.id, 'name': o.name, 'status': o.status, 'status_label': labels.get(o.status, ''),
                'device': ' '.join(filter(None, [o.device_brand, o.device_model])) or 'Equipo',
                'date': o.date_received.strftime('%d/%m/%Y') if o.date_received else '',
                'total': o.total, 'balance': o.balance if o.status in ('done', 'delivered') else 0,
            } for o in orders],
        }

    @api.model
    def cliente_save(self, partner_id, vals):
        allowed = ('name', 'phone', 'email', 'street', 'city', 'vat', 'comment')
        clean = {k: (v or '').strip() for k, v in (vals or {}).items() if k in allowed}
        if not partner_id and not clean.get('name'):
            raise UserError('Escriba el nombre del cliente.')
        if 'name' in clean and not clean['name']:
            raise UserError('El nombre no puede quedar vacío.')
        for key in ('phone', 'email', 'street', 'city', 'vat'):
            if key in clean and not clean[key]:
                clean[key] = False
        if clean.get('email') and '@' not in clean['email']:
            raise UserError('El email no parece válido.')
        if 'comment' in clean:
            clean['comment'] = clean['comment'] or False
        if partner_id:
            partner = self.env['res.partner'].browse(int(partner_id)).exists()
            if not partner:
                raise UserError('El cliente ya no existe.')
            partner.write(clean)
        else:
            partner = self.env['res.partner'].create(clean)
        return partner.id
