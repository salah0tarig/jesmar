from odoo import fields, models, _
from odoo.exceptions import UserError

class BTRRejectWizard(models.TransientModel):
    _name = "btr.reject.wizard"
    _description = "Bank Transfer Rejection"

    request_id = fields.Many2one("fund.transfer.request", required=True, readonly=True)
    reason = fields.Text(required=True, string="Rejection Reason")

    def action_confirm_reject(self):
        self.ensure_one()
        request = self.request_id
        if request.state != "pending":
            raise UserError(_("Only pending requests can be rejected."))
        request._check_approver()
        reason = (self.reason or "").strip()
        if not reason:
            raise UserError(_("Please provide a rejection reason."))
        request.write({"state": "rejected", "reject_reason": reason})
        request.message_post(body=_("Bank transfer rejected. Reason: %s") % reason)
        return {"type": "ir.actions.act_window_close"}
