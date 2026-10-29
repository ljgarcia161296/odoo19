from odoo import http, fields
from odoo.http import request

STEPS = [
    ('draft', 'Recibido'),
    ('diagnosing', 'En diagnóstico'),
    ('quote', 'Presupuesto'),
    ('repairing', 'En reparación'),
    ('done', 'Listo para retirar'),
    ('delivered', 'Entregado'),
]


class TallerPublic(http.Controller):

    def _order(self, token):
        if not token or len(token) < 16:
            return request.env['service.order']
        return request.env['service.order'].sudo().search(
            [('access_token', '=', token)], limit=1)

    @http.route('/taller/estado/<string:token>', type='http', auth='public', methods=['GET'])
    def estado(self, token, gracias=None, **kw):
        order = self._order(token)
        if not order:
            return request.render('taller.status_not_found', {}, status=404)
        keys = [k for k, _label in STEPS]
        current = keys.index(order.status) if order.status in keys else -1
        labels = dict(order._fields['status'].selection)
        in_process = order.status in ('draft', 'diagnosing', 'quote', 'repairing')
        show_amount = order.status in ('quote', 'done')
        symbol = order.currency_id.symbol or ''
        values = {
            'order': order,
            'token': token,
            'steps': STEPS,
            'current': current,
            'thanks': bool(gracias),
            'status_label': labels.get(order.status, order.status),
            'device': ' '.join(filter(None, [order.device_brand, order.device_model])) or 'Equipo',
            'customer': order.partner_id.name or order.customer_name or '',
            'promise': order.promise_date.strftime('%d/%m/%Y') if (order.promise_date and in_process) else '',
            'ready': order.date_ready.strftime('%d/%m/%Y') if (order.date_ready and order.status == 'done') else '',
            'amount': '%s %.2f' % (symbol, order.total) if show_amount else '',
            'balance': '%s %.2f' % (symbol, order.balance) if (show_amount and order.paid_total) else '',
        }
        return request.render('taller.status_page', values)

    @http.route('/taller/encuesta/<string:token>', type='http', auth='public',
                methods=['POST'], csrf=True)
    def encuesta(self, token, rating=None, comment='', **kw):
        order = self._order(token)
        if not order or order.status != 'delivered' or order.rating:
            return request.redirect('/taller/estado/%s' % token)
        if rating in ('1', '2', '3', '4', '5'):
            order.with_context(tracking_disable=True).write({
                'rating': rating,
                'rating_comment': (comment or '')[:1000],
                'rating_date': fields.Date.today(),
            })
        return request.redirect('/taller/estado/%s?gracias=1' % token)