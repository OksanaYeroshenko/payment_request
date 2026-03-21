from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PaymentRequestCreateBillWizard(models.TransientModel):
    _name = "payment.request.create.bill.wizard"
    _description = "Create Vendor Bill from Payment Request"

    payment_request_id = fields.Many2one("payment.request", required=True, readonly=True)
    company_id = fields.Many2one("res.company", string="Company")
    journal_id = fields.Many2one(
        "account.journal",
        string="Purchase Journal",
        domain="[('type', '=', 'purchase'), ('company_id', '=', company_id)]",
        required=True,
    )
    account_id = fields.Many2one(
        "account.account",
        string="Expense Account",
        domain="[('deprecated', '=', False), ('company_ids', 'in', company_id), ('account_type', 'in', ['expense', 'expense_depreciation', 'expense_direct_cost'])]",
        required=True,
    )
    to_check = fields.Boolean(string="To Check")

    @api.onchange("company_id")
    def _onchange_company_id(self):
        self.journal_id = False
        self.account_id = False
        if self.company_id:
            journal = self.env["account.journal"].search(
                [("type", "=", "purchase"), ("company_id", "=", self.company_id.id)],
                order="sequence, id", limit=1,)
            self.journal_id = journal

    @api.onchange("journal_id")
    def _onchange_journal_id(self):
        self.account_id = self.journal_id.default_account_id if self.journal_id and self.journal_id.default_account_id else False
        if self.journal_id and not self.company_id:
            self.company_id = self.journal_id.company_id

    def _get_request_attachments_to_copy(self, request_rec):
        attachments = self.env["ir.attachment"].search([
            ("res_model", "=", request_rec._name),
            ("res_id", "=", request_rec.id),
            ("type", "=", "binary"),
        ])
        if request_rec.invoice:
            attachments |= request_rec.invoice.filtered(lambda a: a.type == "binary")
        if request_rec.message_main_attachment_id and request_rec.message_main_attachment_id.type == "binary":
            attachments |= request_rec.message_main_attachment_id
        return attachments

    def _copy_request_attachments_to_bill(self, request_rec, bill):
        copied_by_source_id = {}
        source_attachments = self._get_request_attachments_to_copy(request_rec)
        for attachment in source_attachments:
            copied = attachment.copy({
                "res_model": bill._name,
                "res_id": bill.id,
            })
            copied_by_source_id[attachment.id] = copied

        source_main = request_rec.message_main_attachment_id
        copied_main = source_main and copied_by_source_id.get(source_main.id)
        if copied_main:
            bill.message_main_attachment_id = copied_main.id
        elif copied_by_source_id:
            bill.message_main_attachment_id = next(iter(copied_by_source_id.values())).id

        return copied_by_source_id

    def action_create_vendor_bill(self):
        self.ensure_one()
        request_rec = self.payment_request_id
        if not self.company_id:
            raise UserError(_("Please set Company."))
        if not self.journal_id:
            raise UserError(_("Please set Purchase Journal."))
        if not self.account_id:
            raise UserError(_("Please set Expense Account."))
        if self.journal_id.company_id != self.company_id:
            raise UserError(_("Selected journal does not belong to selected company."))

        analytic_account_id = request_rec.project
        move_vals = {
            "move_type": "in_invoice",
            "company_id": self.company_id.id,
            "journal_id": self.journal_id.id,
            "partner_id": request_rec.partner_id.id,
            "invoice_date": fields.Date.context_today(self),
            "invoice_date_due": request_rec.due_date or False,
            "currency_id": request_rec.currency_id.id,
            "payment_request_id": request_rec.id,
            "ref": request_rec.sequence,
            "invoice_line_ids": [
                (0, 0, {
                    "name": request_rec.description or request_rec.sequence,
                    "account_id": self.account_id.id,
                    "quantity": 1.0,
                    "price_unit": request_rec.amount,
                    **({"analytic_distribution": {analytic_account_id.id: 100}} if analytic_account_id else {}),
                })
            ],
        }
        bill = self.env["account.move"].create(move_vals)
        self._copy_request_attachments_to_bill(request_rec, bill)
        bill.action_post()
        bill.checked = not self.to_check
        return {
            "type": "ir.actions.act_window",
            "name": _("Vendor Bill"),
            "res_model": "account.move",
            "view_mode": "form",
            "res_id": bill.id,
            "target": "current",
        }
