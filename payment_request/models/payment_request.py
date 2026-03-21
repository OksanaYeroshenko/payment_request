from markupsafe import Markup
from odoo import models, fields, api, _


class PaymentRequest(models.Model):
    _name = "payment.request"
    _description = "Payment Request"
    _inherit = ["mail.thread.main.attachment", "mail.activity.mixin", "portal.mixin"]
    _order = "create_date desc"
    _rec_name = "sequence"
    _mail_post_access = "read"

    description = fields.Char(tracking=True)
    long_description = fields.Text(tracking=True, copy=False)
    sequence = fields.Char(string="Reference", readonly=True, copy=False, default="New")
    due_date = fields.Date()
    project = fields.Many2one("account.analytic.account", string="Project")
    partner_id = fields.Many2one("res.partner", required=True, tracking=True)
    requester_id = fields.Many2one(
        "res.users", string="Requester", default=lambda self: self.env.user, readonly=True)
    payment_basis = fields.Selection(
        [("invoice", "Invoice"), ("no_invoice", "No Invoice")],
        default="invoice",
        tracking=True,
        required=True,
    )
    invoice = fields.Many2many("ir.attachment", string="Upload File", copy=False)
    no_invoice_option = fields.Selection(
        [
            ("bank_card", "Bank Card"),
            ("int_bank_account", "International Bank Account"),
            ("paypal", "PayPal"),
            ("payoneer_wise", "Payoneer, Wise"),
            ("crypto", "Crypto"),
        ],
        default="payoneer_wise",
        required=True,
    )
    bank_card_name = fields.Char(string="Cardholder Name")
    bank_card_number = fields.Char(string="Card Number")
    bank_card_ussuing_bank = fields.Char(string="Issuing Bank")
    int_bank_acc_name = fields.Char(string="Account Holder Name")
    int_bank_acc_iban = fields.Char(string="IBAN")
    int_bank_acc_bic = fields.Char(string="SWIFT/BIC")
    int_bank_acc_bank = fields.Char(string="Bank Name")
    int_bank_acc_bank_address = fields.Char(string="Bank Address")
    paypal_name = fields.Char(string="Account Name")
    paypal_email = fields.Char(string="Email")
    payoneer_wise_name = fields.Char(string="Account Name")
    payoneer_wise_acc_number = fields.Char(string="Account Number")
    payoneer_wise_aba = fields.Char(string="Routing (ABA) Number")
    crypto_wallet_address = fields.Char(string="Wallet Address")
    crypto_network = fields.Char(string="Network/Protocol (only TRC-20 supported)")
    currency_id = fields.Many2one(
        "res.currency", default=lambda self: self.env.company.currency_id.id, required=True)
    amount = fields.Monetary(required=True, currency_field="currency_id", tracking=True)
    state = fields.Selection(
        [
            ("new", "New"),
            ("processing", "Processing"),
            ("stuck", "Stuck"),
            ("in_payment", "In Payment"),
            ("paid", "Paid"),
            ("cancelled", "Cancelled"),
        ], default="new", tracking=True, compute='_compute_state', store=True)
    vendor_bill_ids = fields.One2many(
        "account.move", "payment_request_id", string="Vendor Bill", copy=False)
    vendor_bill_ids_count = fields.Integer(compute="_compute_vendor_bill_count")
    readonly = fields.Boolean(compute='_compute_readonly')

    @api.depends('vendor_bill_ids', 'vendor_bill_ids.amount_residual')
    def _compute_state(self):
        for record in self:
            if not record.state:
                record.state = 'new'
            if record.vendor_bill_ids:
                if not sum(record.vendor_bill_ids.mapped('amount_residual')):
                    record.state = 'paid'
                else:
                    record.state = 'in_payment'
            else:
                record.state = 'processing'

    @api.depends('state')
    def _compute_readonly(self):
        for record in self:
            record.readonly = record.state in ['paid', 'in_payment', 'cancelled']

    @api.depends('vendor_bill_ids')
    def _compute_vendor_bill_count(self):
        for record in self:
            record.vendor_bill_ids_count = len(record.vendor_bill_ids)

    def _post_invoice_attachment(self):
        """Ensure invoice attachments appear in chatter and set main attachment."""
        for record in self:
            if record.invoice:
                latest = record.invoice.sorted(lambda a: a.id)[-1]
                # make sure attachments point to this record
                record.invoice.write({
                    "res_model": record._name,
                    "res_id": record.id,
                })
                record.message_main_attachment_id = latest.id
                record.with_context(from_invoice_upload=True).message_post(
                    body=_("Invoice uploaded"),
                    attachment_ids=[latest.id],
                    subtype_xmlid="mail.mt_comment",
                    message_type="comment",
                )

    def message_post(self, **kwargs):
        # Expose payment request notes/tracking in portal chatter by using comment subtype.
        note_subtype = self.env.ref("mail.mt_note", raise_if_not_found=False)
        comment_subtype = self.env.ref("mail.mt_comment", raise_if_not_found=False)
        if comment_subtype:
            if kwargs.get("subtype_xmlid") == "mail.mt_note":
                kwargs["subtype_xmlid"] = "mail.mt_comment"
            elif kwargs.get("subtype_id") and note_subtype and kwargs.get("subtype_id") == note_subtype.id:
                kwargs["subtype_id"] = comment_subtype.id

        # Keep main attachment unchanged for regular chatter uploads.
        self.ensure_one()
        previous_main = self.message_main_attachment_id
        message = super().message_post(**kwargs)
        if not self.env.context.get("from_invoice_upload") and previous_main and previous_main != self.message_main_attachment_id:
            self.message_main_attachment_id = previous_main.id
        return message

    def _subscribe_operation_managers(self):
        group = self.env.ref('payment_request.group_payment_request_operation_manager', raise_if_not_found=False)
        if not group:
            return
        partners = group.sudo().users.mapped('partner_id').filtered(lambda p: p)
        if partners:
            for rec in self:
                rec.message_subscribe(partner_ids=partners.ids)

    def _notify_followers_on_create(self):
        for rec in self:
            basis_label = dict(rec._fields["payment_basis"].selection).get(rec.payment_basis, rec.payment_basis or "-")
            no_invoice_label = dict(rec._fields["no_invoice_option"].selection).get(
                rec.no_invoice_option, rec.no_invoice_option or "-"
            )
            amount_label = "%s %s" % (rec.amount or 0.0, rec.currency_id.name or "")
            subject = _("New Payment Request %s") % (rec.sequence or rec.display_name)
            body = Markup(
                """
                <p>A new payment request has been created.</p>
                <ul>
                    <li><b>Reference:</b> %(reference)s</li>
                    <li><b>Partner:</b> %(partner)s</li>
                    <li><b>Amount:</b> %(amount)s</li>
                    <li><b>Due Date:</b> %(due_date)s</li>
                    <li><b>Payment Basis:</b> %(basis)s</li>
                    <li><b>No Invoice Option:</b> %(no_invoice)s</li>
                    <li><b>Requester:</b> %(requester)s</li>
                    <li><b>Description:</b> %(description)s</li>
                </ul>
                """
            ) % {
                "reference": rec.sequence or rec.display_name or "-",
                "partner": rec.partner_id.display_name or "-",
                "amount": amount_label.strip() or "-",
                "due_date": rec.due_date or "-",
                "basis": basis_label or "-",
                "no_invoice": no_invoice_label if rec.payment_basis == "no_invoice" else "-",
                "requester": rec.requester_id.display_name or "-",
                "description": rec.description or "-",
            }
            rec.message_post(
                subject=subject,
                body=body,
                subtype_xmlid="mail.mt_comment",
                message_type="comment",
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("partner_id") and self.env.user.partner_id:
                vals["partner_id"] = self.env.user.partner_id.id
            if not vals.get("requester_id"):
                vals["requester_id"] = self.env.uid
            if not vals.get("sequence") or vals.get("sequence") == "New":
                vals["sequence"] = self.env["ir.sequence"].next_by_code("payment.request.sequence") or "New"
        res = super().create(vals_list)
        for rec, vals in zip(res, vals_list):
            if vals.get("invoice"):
                rec._post_invoice_attachment()
        res._subscribe_operation_managers()
        res._notify_followers_on_create()
        return res

    def _post_state_change_message(self, previous_states):
        state_labels = dict(self._fields["state"].selection)
        for rec in self:
            old_state = previous_states.get(rec.id)
            new_state = rec.state
            if not old_state or old_state == new_state:
                continue
            body = Markup("Status changed: <b>%s</b> -> <b>%s</b>") % (
                state_labels.get(old_state, old_state),
                state_labels.get(new_state, new_state),
            )
            rec.message_post(
                body=body,
                subtype_xmlid="mail.mt_comment",
                message_type="comment",
            )

    def write(self, vals):
        previous_states = {rec.id: rec.state for rec in self} if "state" in vals else {}
        res = super(PaymentRequest, self).write(vals)
        if vals.get("invoice"):
            self._post_invoice_attachment()
        if "state" in vals:
            self._post_state_change_message(previous_states)
        return res

    def action_set_processing(self):
        self.write({"state": "processing"})

    def action_set_stuck(self):
        self.write({"state": "stuck"})

    def action_mark_as_paid(self):
        self.ensure_one()
        wizard_model = self.env["payment.request.create.bill.wizard"]._name
        return {
            "name": _("Create Vendor Bill"),
            "type": "ir.actions.act_window",
            "res_model": wizard_model,
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_payment_request_id": self.id,
            },
        }

    def action_cancel(self):
        self.state = "cancelled"

    def action_view_vendor_bill(self):
        self.ensure_one()
        if self.vendor_bill_ids_count == 1:
            return {
                "name": _("Vendor Bill"),
                "type": "ir.actions.act_window",
                "res_model": "account.move",
                "view_mode": "form",
                "res_id": self.vendor_bill_ids.id,
            }
        return {
            "name": _("Vendor Bills"),
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "view_mode": "list,form",
            "domain": [('id', 'in', self.vendor_bill_ids.ids)],
        }
