from odoo import fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    payment_request_portal_access = fields.Boolean(
        string="Payment Request Portal",
        compute="_compute_payment_request_portal_access",
        inverse="_inverse_payment_request_portal_access",
    )

    def _compute_payment_request_portal_access(self):
        group = self.env.ref("payment_request.group_payment_request_portal", raise_if_not_found=False)
        for user in self:
            user.payment_request_portal_access = bool(group and group in user.groups_id)

    def _inverse_payment_request_portal_access(self):
        group = self.env.ref("payment_request.group_payment_request_portal", raise_if_not_found=False)
        if not group:
            return
        for user in self:
            if user.payment_request_portal_access:
                user.write({"groups_id": [(4, group.id)]})
            else:
                user.write({"groups_id": [(3, group.id)]})

