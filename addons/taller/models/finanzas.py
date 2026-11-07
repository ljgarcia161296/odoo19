import calendar
import csv
import io
import re
from datetime import date

from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError

EXPENSE_CATEGORIES = [
    ('rent', 'Alquiler'),
    ('utilities', 'Luz, agua, internet'),
    ('salary', 'Sueldos'),
    ('tax', 'Impuestos y aportes'),
    ('supplies', 'Insumos'),
    ('other', 'Otros'),
]


class TallerExpense(models.Model):
    _name = 'taller.expense'
    _description = 'Gasto del taller'
    _order = 'date desc, id desc'

    name = fields.Char(string='Concepto', required=True)
    date = fields.Date(string='Fecha', default=fields.Date.today, required=True)
    category = fields.Selection(EXPENSE_CATEGORIES, string='Categoría', default='other', required=True)
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)
    amount = fields.Monetary(string='Monto', required=True, currency_field='currency_id')
    recurring = fields.Boolean(string='Se repite todos los meses')
    end_date = fields.Date(string='Deja de repetirse el')

    @api.constrains('amount')
    def _check_amount(self):
        for expense in self:
            if expense.amount <= 0:
                raise ValidationError('El monto del gasto debe ser mayor que cero.')


class ResUsersCommission(models.Model):
    _inherit = 'res.users'

    taller_commission_pct = fields.Float(string='Comisión del taller (%)')


class ServiceOrderFinanzas(models.Model):
    _inherit = 'service.order'

    @api.model
    def _fin_check(self):
        if not self.env.user.has_group('taller.group_taller_manager'):
            raise UserError('Las finanzas son solo para responsables.')

    @api.model
    def fin_data(self, month=None):
        self._fin_check()
        today = fields.Date.context_today(self)
        if month:
            year, mon = [int(x) for x in month.split('-')]
        else:
            year, mon = today.year, today.month
        start = date(year, mon, 1)
        end = date(year, mon, calendar.monthrange(year, mon)[1])

        groups = self.env['service.payment']._read_group(
            [('date', '>=', start), ('date', '<=', end)], aggregates=['amount:sum'])
        income = (groups[0][0] if groups else 0) or 0
        sales = self.env['taller.sale'].search([('date', '>=', start), ('date', '<=', end),
                                                ('state', '=', 'done')])
        income += sum(sales.mapped('total'))

        orders = self.search([('status', '=', 'delivered'),
                              ('date_finished', '>=', start), ('date_finished', '<=', end)])
        parts_cost = sum(orders.mapped('line_ids.cost_subtotal'))
        parts_cost += sum(l.quantity * l.unit_cost for l in sales.mapped('line_ids'))
        parts_sales = sum(orders.mapped('parts_total'))

        sudo_users = self.env['res.users'].sudo()
        group_users = (self.env.ref('taller.group_taller_technician').sudo().user_ids
                       | self.env.ref('taller.group_taller_manager').sudo().user_ids)
        techs = {}
        for user in group_users:
            techs[user.id] = {'id': user.id, 'name': user.name, 'orders': 0, 'labor': 0.0,
                              'pct': user.taller_commission_pct, 'commission': 0.0}
        techs.setdefault(0, {'id': 0, 'name': 'Sin asignar', 'orders': 0, 'labor': 0.0,
                             'pct': 0.0, 'commission': 0.0})
        for order in orders.filtered(lambda o: not o.no_charge):
            tech = techs.setdefault(order.user_id.id or 0, {
                'id': order.user_id.id or 0, 'name': order.user_id.name or 'Sin asignar',
                'orders': 0, 'labor': 0.0, 'pct': order.user_id.taller_commission_pct, 'commission': 0.0})
            tech['orders'] += 1
            tech['labor'] += order.labor_cost
        for tech in techs.values():
            tech['commission'] = tech['labor'] * (tech['pct'] or 0) / 100.0
        tech_rows = [t for t in techs.values() if t['orders'] or t['id']]
        tech_rows.sort(key=lambda t: -t['labor'])
        commissions = sum(t['commission'] for t in tech_rows)

        labels = dict(EXPENSE_CATEGORIES)
        expenses = []
        for exp in self.env['taller.expense'].search([('date', '<=', end)]):
            if exp.recurring:
                if exp.end_date and exp.end_date < start:
                    continue
            elif exp.date < start:
                continue
            expenses.append({
                'id': exp.id, 'name': exp.name, 'category': labels[exp.category],
                'amount': exp.amount, 'recurring': exp.recurring,
            })
        expenses_total = sum(e['amount'] for e in expenses)

        return {
            'month': '%04d-%02d' % (year, mon),
            'symbol': self.env.company.currency_id.symbol or '',
            'income': income,
            'parts_cost': parts_cost,
            'parts_sales': parts_sales,
            'delivered': len(orders),
            'commissions': commissions,
            'expenses_total': expenses_total,
            'result': income - parts_cost - commissions - expenses_total,
            'techs': tech_rows,
            'expenses': expenses,
        }

    @api.model
    def fin_set_commission(self, user_id, pct):
        self._fin_check()
        pct = float(pct or 0)
        if pct < 0 or pct > 100:
            raise UserError('El porcentaje debe estar entre 0 y 100.')
        self.env['res.users'].sudo().browse(int(user_id)).write({'taller_commission_pct': pct})
        return True


# ---------------------------------------------------------------------- importar clientes
class TallerImportWizard(models.TransientModel):
    _name = 'taller.import.wizard'
    _description = 'Importar clientes desde CSV'

    file = fields.Binary(string='Archivo CSV', required=True)
    filename = fields.Char()
    result = fields.Text(string='Resultado', readonly=True)

    ALIASES = {
        'name': ('nombre', 'name', 'cliente', 'razon social', 'nombre y apellido'),
        'phone': ('telefono', 'celular', 'phone', 'movil', 'tel', 'whatsapp'),
        'email': ('email', 'correo', 'mail', 'e-mail'),
        'street': ('direccion', 'domicilio', 'address', 'calle'),
        'vat': ('documento', 'ci', 'rut', 'cedula', 'vat'),
    }

    @staticmethod
    def _norm(text):
        text = (text or '').strip().lower()
        for a, b in (('á', 'a'), ('é', 'e'), ('í', 'i'), ('ó', 'o'), ('ú', 'u'), ('ñ', 'n')):
            text = text.replace(a, b)
        return text

    def action_import(self):
        self.ensure_one()
        import base64
        raw = base64.b64decode(self.file or b'')
        try:
            text = raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            text = raw.decode('latin-1')
        sample = text[:2000]
        delimiter = max([',', ';', '\t'], key=sample.count)
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        if not reader.fieldnames:
            raise UserError('El archivo está vacío.')
        columns = {}
        for header in reader.fieldnames:
            key = self._norm(header)
            for field, names in self.ALIASES.items():
                if key in names and field not in columns:
                    columns[field] = header
        if 'name' not in columns:
            raise UserError('No encuentro la columna "nombre". Use la plantilla.')

        Partner = self.env['res.partner']

        def digits(value):
            return re.sub(r'\D', '', value or '')

        known_phones = {digits(p.phone): p for p in Partner.search([('phone', '!=', False)]) if digits(p.phone)}
        created = skipped = failed = 0
        notes = []
        for line_no, row in enumerate(reader, start=2):
            name = (row.get(columns['name']) or '').strip()
            if not name:
                continue
            vals = {'name': name}
            for field in ('phone', 'email', 'street', 'vat'):
                if field in columns and (row.get(columns[field]) or '').strip():
                    vals[field] = row[columns[field]].strip()
            number = digits(vals.get('phone'))
            if number and number in known_phones:
                skipped += 1
                if len(notes) < 200:
                    notes.append('Fila %s: "%s" ya existe (mismo teléfono).' % (line_no, name))
                continue
            try:
                with self.env.cr.savepoint():
                    partner = Partner.create(vals)
                created += 1
                if number:
                    known_phones[number] = partner
            except Exception as error:  # noqa: BLE001 - se informa fila por fila
                failed += 1
                if len(notes) < 200:
                    notes.append('Fila %s: "%s" no se pudo crear (%s).' % (line_no, name, str(error)[:80]))
        self.result = 'Creados: %s\nOmitidos por duplicado: %s\nCon errores: %s\n\n%s' % (
            created, skipped, failed, '\n'.join(notes))
        return {
            'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': self.id,
            'view_mode': 'form', 'target': 'new',
        }
