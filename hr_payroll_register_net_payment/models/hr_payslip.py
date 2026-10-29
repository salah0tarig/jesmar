from odoo import _, models
from odoo.exceptions import UserError


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    def action_create_and_post_journal_entry(self):
        """Create the payroll journal entry when missing, then post it if still draft."""
        if not self:
            raise UserError(_("Please select at least one payslip."))

        invalid = self.filtered(lambda slip: slip.state in ("paid", "cancel"))
        if invalid:
            raise UserError(
                _(
                    "Cannot create or post journal entries for payslips that are paid or cancelled: %s"
                )
                % ", ".join(invalid.mapped("display_name"))
            )

        drafts = self.filtered(lambda slip: slip.state == "draft")
        if drafts:
            uncomputed = drafts.filtered(lambda slip: not slip.line_ids)
            if uncomputed:
                raise UserError(
                    _("Compute the payslip before creating journal entries: %s")
                    % ", ".join(uncomputed.mapped("display_name"))
                )
            drafts.action_payslip_done()

        without_move = self.filtered(lambda slip: slip.state == "validated" and not slip.move_id)
        if without_move:
            without_move.filtered("journal_id")._action_create_account_move()

        still_without_move = self.filtered(lambda slip: slip.state == "validated" and not slip.move_id)
        if still_without_move:
            raise UserError(
                _("No journal entry could be created for: %s")
                % ", ".join(still_without_move.mapped("display_name"))
            )

        cancelled_moves = self.filtered(lambda slip: slip.move_id.state == "cancel")
        if cancelled_moves:
            raise UserError(
                _("The journal entry is cancelled for: %s")
                % ", ".join(cancelled_moves.mapped("display_name"))
            )

        draft_moves = self.move_id.filtered(lambda move: move.state == "draft")
        if draft_moves:
            draft_moves.action_post()

        return True

    def action_register_payment(self):
        """Use standard Odoo payroll payment register (no custom journal/company logic)."""
        return super().action_register_payment()
