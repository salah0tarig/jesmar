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

    def _get_payroll_payment_lines(self):
        """Payable residual lines only (outbound). Whole move mixes debit+credit and fails Pay."""
        partners = self.employee_id.work_contact_id
        lines = self.move_id.line_ids.filtered(
            lambda line: (
                line.account_type == "liability_payable"
                and not line.currency_id.is_zero(line.amount_residual_currency)
            )
        )
        if partners:
            matched = lines.filtered(lambda line: line.partner_id in partners)
            if matched:
                return matched
        return lines

    def action_register_payment(self):
        """Same as standard payroll Pay, but only on payable NET lines.

        Default Odoo passes every journal item. Payroll entries have expense
        (inbound residual) and payable (outbound residual) together, which
        raises: cannot register inbound and outbound at the same time.
        """
        if any(state == "paid" for state in self.mapped("state")):
            raise UserError(_("You can only register payments for unpaid documents."))
        if any(m.state != "posted" for m in self.move_id):
            raise UserError(_("You can only register payment for posted journal entries."))

        bank_accounts = self.employee_id.sudo().bank_account_ids
        if any(not bank.allow_out_payment for bank in bank_accounts):
            raise UserError(_("An employee bank account is untrusted"))

        # Standard NET reconcile check (code case-insensitive; account per move company).
        for slip in self:
            net_rule = slip.struct_id.rule_ids.filtered(
                lambda rule: (rule.code or "").strip().upper() == "NET"
            )[:1]
            company = slip.move_id.company_id or slip.company_id
            credit = self.env["account.account"]
            while company and not credit:
                credit = net_rule.with_company(company).account_credit
                company = company.parent_id
            if not credit or not credit.reconcile:
                raise UserError(
                    _("The credit account on the NET salary rule is not reconciliable")
                )

        payment_lines = self._get_payroll_payment_lines()
        if not payment_lines:
            raise UserError(
                _("No payable salary line with residual amount found on the journal entry.")
            )

        pay_company = payment_lines.company_id[:1]
        journals = self.env["account.journal"].search([
            ("company_id", "parent_of", pay_company.id),
            ("type", "in", ("bank", "cash", "credit")),
        ])
        if not journals:
            archived = self.env["account.journal"].with_context(active_test=False).search([
                ("company_id", "parent_of", pay_company.id),
                ("type", "in", ("bank", "cash", "credit")),
                ("active", "=", False),
            ])
            if archived:
                raise UserError(
                    _(
                        "No active Bank/Cash journal for %(company)s. "
                        "These journals exist but are archived: %(journals)s. "
                        "Open Accounting → Configuration → Journals and activate one, then Pay again.",
                        company=pay_company.display_name,
                        journals=", ".join(archived.mapped("display_name")),
                    )
                )
            raise UserError(
                _(
                    "No Bank/Cash journal for %(company)s (company of the salary journal entry). "
                    "Branch banks from another company cannot pay this entry. "
                    "Create or activate a Bank journal on %(company)s.",
                    company=pay_company.display_name,
                )
            )

        residual = abs(sum(payment_lines.mapped("amount_residual_currency")))
        if payment_lines.currency_id[:1].is_zero(residual):
            residual = abs(sum(payment_lines.mapped("amount_residual")))

        ctx = {
            "default_company_id": pay_company.id,
            "default_journal_id": journals[:1].id,
            "default_amount": residual,
        }
        if len(self) == 1:
            ctx.update({
                "default_partner_id": self.employee_id.work_contact_id.id,
                "default_partner_bank_id": self.employee_id.primary_bank_account_id.id,
            })
        return payment_lines.action_register_payment(ctx=ctx)
