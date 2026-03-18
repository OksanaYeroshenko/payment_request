from odoo import models, fields, _


class AccountMove(models.Model):
    _inherit = 'account.move'

    payment_request_id = fields.Many2one('payment.request', copy=False)

    def action_open_payment_request(self):
        self.ensure_one()
        if not self.payment_request_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': _('Payment Request'),
            'res_model': 'payment.request',
            'view_mode': 'form',
            'res_id': self.payment_request_id.id,
            'target': 'current',
        }
