from datetime import date, timedelta

from odoo import models, fields, api

STATUS_ORDER = ['draft', 'diagnosing', 'quote', 'repairing', 'done', 'delivered']
OPEN_STATES = ['draft', 'diagnosing', 'quote', 'repairing']


class ServiceOrderDashboard(models.Model):
    _inherit = 'service.order'

    @api.model
    def _kpi(self, key, label, value, icon, tone, domain, model='service.order', **extra):
        kpi = {
            'key': key, 'label': label, 'value': value, 'icon': icon, 'tone': tone,
            'domain': domain, 'model': model,
            'alert': bool(value) and tone == 'red',
        }
        kpi.update(extra)
        return kpi

    @api.model
    def get_dashboard_data(self):
        today = fields.Date.today()
        month_start = today.replace(day=1)
        params = self.env['ir.config_parameter'].sudo()
        unclaimed_days = int(params.get_param('taller.unclaimed_days', 7))
        followup_days = int(params.get_param('taller.quote_followup_days', 3))
        is_manager = self.env.user.has_group('taller.group_taller_manager')
        symbol = self.env.company.currency_id.symbol or ''
        labels = dict(self._fields['status'].selection)
        to_str = fields.Date.to_string

        open_domain = [('status', 'in', OPEN_STATES)]
        late_domain = [('promise_date', '<', to_str(today)), ('status', 'in', OPEN_STATES)]
        quote_domain = [('status', '=', 'quote')]
        stale_domain = [('status', '=', 'quote'), ('quote_date', '!=', False),
                        ('quote_date', '<=', to_str(today - timedelta(days=followup_days)))]
        ready_domain = [('status', '=', 'done')]
        unclaimed_domain = [('status', '=', 'done'), ('date_ready', '!=', False),
                            ('date_ready', '<=', to_str(today - timedelta(days=unclaimed_days)))]
        low_domain = [('low_stock', '=', True)]
        delivered_domain = [('status', '=', 'delivered'),
                            ('date_finished', '>=', to_str(month_start))]

        kpis = [
            self._kpi('open', 'En proceso', self.search_count(open_domain),
                      'fa-wrench', 'teal', open_domain),
            self._kpi('late', 'Atrasadas', self.search_count(late_domain),
                      'fa-clock-o', 'red', late_domain),
            self._kpi('quote', 'Esperando aprobación', self.search_count(quote_domain),
                      'fa-hourglass-half', 'amber', quote_domain),
            self._kpi('stale', 'Presupuestos sin respuesta', self.search_count(stale_domain),
                      'fa-bell', 'amber', stale_domain),
            self._kpi('ready', 'Listas para retirar', self.search_count(ready_domain),
                      'fa-check-circle', 'green', ready_domain),
            self._kpi('unclaimed', 'Sin retirar', self.search_count(unclaimed_domain),
                      'fa-exclamation-triangle', 'red', unclaimed_domain),
            self._kpi('lowstock', 'Repuestos con stock bajo',
                      self.env['service.part'].search_count(low_domain),
                      'fa-cubes', 'red', low_domain, model='service.part'),
        ]

        if is_manager:
            delivered = self.search(delivered_domain)
            kpis.append(self._kpi(
                'income', 'Ingresos del mes', sum(delivered.mapped('total')),
                'fa-line-chart', 'blue', delivered_domain, money=True, symbol=symbol))
            balance_domain = [('status', 'in', ['done', 'delivered']), ('balance', '>', 0)]
            pending = self.search(balance_domain)
            kpis.append(self._kpi(
                'balance', 'Saldo por cobrar', sum(pending.mapped('balance')),
                'fa-money', 'amber', balance_domain, money=True, symbol=symbol))
            rated = self.search([('rating', '!=', False)])
            if rated:
                avg = sum(rated.mapped('rating_value')) / float(len(rated))
                kpis.append(self._kpi(
                    'rating', 'Satisfacción', avg, 'fa-star', 'purple',
                    [('rating', '!=', False)], decimals=1, suffix='/5'))

        counts = {s: self.search_count([('status', '=', s)]) for s in OPEN_STATES + ['done']}
        counts['delivered'] = self.search_count(delivered_domain)
        top = max(counts.values()) or 1
        stages = []
        for status in STATUS_ORDER:
            count = counts[status]
            stages.append({
                'key': status,
                'label': labels[status] + (' (mes)' if status == 'delivered' else ''),
                'count': count,
                'pct': max(4, round(count * 100.0 / top)) if count else 0,
                'domain': delivered_domain if status == 'delivered' else [('status', '=', status)],
            })

        device_labels = dict(self._fields['device_type'].selection)
        recent = []
        for order in self.search([], order='id desc', limit=6):
            device = ' '.join(filter(None, [order.device_brand, order.device_model]))
            recent.append({
                'id': order.id,
                'name': order.name,
                'customer': order.partner_id.name or order.customer_name or '',
                'device': device or device_labels.get(order.device_type, ''),
                'status': order.status,
                'status_label': labels.get(order.status, order.status),
                'date': order.date_received.strftime('%d/%m') if order.date_received else '',
            })

        # tendencia semanal: últimas 8 semanas
        week0 = today - timedelta(days=today.weekday())
        starts = [week0 - timedelta(weeks=i) for i in range(7, -1, -1)]
        first_week = starts[0]

        def bucket(dates):
            counts = [0] * len(starts)
            for d in dates:
                if d:
                    idx = (d - first_week).days // 7
                    if 0 <= idx < len(counts):
                        counts[idx] += 1
            return counts

        received = self.search([('date_received', '>=', to_str(first_week))]).mapped('date_received')
        finished = self.search([('status', '=', 'delivered'),
                                ('date_finished', '>=', to_str(first_week))]).mapped('date_finished')
        trend = {
            'labels': [s.strftime('%d/%m') for s in starts],
            'received': bucket(received),
            'delivered': bucket(finished),
        }

        # ingresos de los últimos 6 meses (solo administradores)
        income = None
        if is_manager:
            month_names = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun',
                           'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
            months = []
            for i in range(5, -1, -1):
                year, month = today.year, today.month - i
                while month <= 0:
                    month += 12
                    year -= 1
                months.append((year, month))
            totals = {key: 0.0 for key in months}
            since = date(months[0][0], months[0][1], 1)
            for order in self.search([('status', '=', 'delivered'),
                                      ('date_finished', '>=', to_str(since))]):
                if order.date_finished:
                    key = (order.date_finished.year, order.date_finished.month)
                    if key in totals:
                        totals[key] += order.total
            income = {
                'labels': [month_names[m - 1] for _y, m in months],
                'values': [totals[key] for key in months],
                'symbol': symbol,
            }

        return {
            'user': self.env.user.name,
            'today': today.strftime('%d/%m/%Y'),
            'is_manager': is_manager,
            'kpis': kpis,
            'stages': stages,
            'recent': recent,
            'trend': trend,
            'income': income,
        }