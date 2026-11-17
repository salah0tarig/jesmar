
from odoo import models, fields, _
from odoo.exceptions import UserError


class BtrSendWizard(models.TransientModel):
    _name = "btr.send.wizard"
    _description = "Verify Bank Transfer Sent"

    request_id = fields.Many2one(
        "fund.transfer.request",
        required=True,
        readonly=True,
    )
    bank_reference = fields.Char(required=True)

    def action_confirm(self):
        self.ensure_one()

        if not (self.bank_reference or "").strip():
            raise UserError(_("Bank reference is required."))

        self.request_id._post_sending_bank_entry(
            self.bank_reference.strip()
        )

        return {"type": "ir.actions.act_window_close"}


class BtrReceiptWizard(models.TransientModel):
    _name = "btr.receipt.wizard"
    _description = "Confirm Bank Transfer Receipt"

    request_id = fields.Many2one(
        "fund.transfer.request",
        required=True,
        readonly=True,
    )
    receipt_reference = fields.Char(required=True)

    def action_confirm(self):
        self.ensure_one()

        if not (self.receipt_reference or "").strip():
            raise UserError(_("Receipt reference is required."))

        # This method validates Receiving Branch Finance,
        # posts the receiving bank entry, links the move,
        # and marks the transfer Completed.
        self.request_id._post_receiving_bank_entry(
            self.receipt_reference.strip()
        )

        return {"type": "ir.actions.act_window_close"}
