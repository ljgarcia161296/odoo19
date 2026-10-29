from odoo import models, fields, api
from odoo.exceptions import UserError


class AccountMoveTaller(models.Model):
    _inherit = 'account.move'

    service_order_id = fields.Many2one('service.order', string='Orden de servicio',
                                       copy=False, readonly=True, ondelete='set null')
    dgi_serie = fields.Char(string='Serie del CFE (DGI)', copy=False)
    dgi_number = fields.Char(string='Número del CFE (DGI)', copy=False)
    dgi_summary = fields.Text(string='Datos para el portal de la DGI',
                              compute='_compute_dgi_summary')

    @api.depends('partner_id', 'invoice_line_ids', 'amount_total')
    def _compute_dgi_summary(self):
        for move in self:
            lines = ['Cliente: %s' % (move.partner_id.name or '')]
            if move.partner_id.vat:
                lines.append('Documento: %s' % move.partner_id.vat)
            lines.append('')
            for line in move.invoice_line_ids.filtered(lambda l: not l.display_type):
                lines.append('%s | cant. %g | precio %.2f' % (
                    line.name, line.quantity, line.price_unit))
            lines.append('')
            lines.append('Subtotal: %.2f' % move.amount_untaxed)
            lines.append('IVA: %.2f' % move.amount_tax)
            lines.append('Total: %.2f' % move.amount_total)
            move.dgi_summary = '\n'.join(lines)

    def action_post(self):
        for move in self:
            if move.service_order_id and not move.dgi_number:
                raise UserError('Emita el comprobante en el portal de la DGI y cargue aquí '
                                'su serie y número antes de confirmar la factura.')
        return super().action_post()


class ServiceOrderInvoicing(models.Model):
    _inherit = 'service.order'

    invoice_id = fields.Many2one('account.move', string='Factura', copy=False,
                                 readonly=True, ondelete='set null')

    def action_view_invoice(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.invoice_id.id,
            'view_mode': 'form',
        }

    def action_create_invoice(self):
        self.ensure_one()
        if self.invoice_id and self.invoice_id.state != 'cancel':
            return self.action_view_invoice()
        if not self.partner_id:
            raise UserError('Seleccione un cliente en la orden antes de facturar.')
        if self.no_charge or not self.total:
            raise UserError('Esta orden no tiene un importe para facturar.')

        company = self.env.company
        journal = self.env['account.journal'].search(
            [('type', '=', 'sale'), ('company_id', '=', company.id)], limit=1)
        account = journal.default_account_id
        if not account:
            raise UserError('Falta configurar la contabilidad: no hay un diario de ventas '
                            'con cuenta de ingresos.')

        taxes = company.account_sale_tax_id
        param = self.env['ir.config_parameter'].sudo().get_param('taller.prices_include_tax', '0')
        include = param in ('1', 'True', 'true')
        rate = 0.0
        if include:
            rate = sum(t.amount for t in taxes if t.amount_type == 'percent') / 100.0

        def net(price):
            return price / (1.0 + rate) if rate else price

        def make_line(name, qty, price):
            return (0, 0, {
                'name': name,
                'quantity': qty,
                'price_unit': net(price),
                'account_id': account.id,
                'tax_ids': [(6, 0, taxes.ids)],
            })

        lines = [make_line(line.name, line.quantity, line.unit_price) for line in self.line_ids]
        if self.labor_cost:
            lines.append(make_line('Mano de obra - %s' % self.name, 1.0, self.labor_cost))

        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'journal_id': journal.id,
            'partner_id': self.partner_id.id,
            'invoice_origin': self.name,
            'ref': self.name,
            'currency_id': self.currency_id.id,
            'service_order_id': self.id,
            'invoice_line_ids': lines,
        })
        self.invoice_id = move
        self.message_post(body='Factura interna creada: %s' % move.display_name)
        return self.action_view_invoice()