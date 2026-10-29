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

    def _get_net_salary_rule(self):
        """NET rule on the payslip structure (code match is case-insensitive)."""
        self.ensure_one()
        return self.struct_id.rule_ids.filtered(
            lambda r: (r.code or "").strip().upper() == "NET"
        )[:1]

    def _get_net_credit_account(self):
        """Credit account for NET (company-dependent).

        Tries the payslip company first, then parent companies. Setting the
        account only under JASMAR must still work for child companies like
        River Nile when the account itself is shared.
        """
        self.ensure_one()
        net_rule = self._get_net_salary_rule()
        if not net_rule:
            return self.env["account.account"]
        company = self.company_id
        while company:
            account = net_rule.with_company(company).account_credit
            if account:
                return account
            company = company.parent_id
        return self.env["account.account"]

    def _get_salary_payment_move_lines(self):
        """Payable lines for this employee's NET salary only (not the whole batch move).

        Prefer the posted journal entry (source of truth). The NET rule credit
        account is only used to narrow lines when it is set for this company.
        """
        self.ensure_one()
        if not self.move_id:
            raise UserError(_("No journal entry is linked to this payslip."))

        partner = self.employee_id.work_contact_id
        residual_payable = self.move_id.line_ids.filtered(
            lambda line: (
                line.account_type == "liability_payable"
                and not line.currency_id.is_zero(line.amount_residual_currency)
            )
        )
        lines = residual_payable
        if partner:
            partner_lines = residual_payable.filtered(lambda line, p=partner: line.partner_id == p)
            if partner_lines:
                lines = partner_lines
        net_account = self._get_net_credit_account()
        if net_account:
            matched = lines.filtered(lambda line, acc=net_account: line.account_id == acc)
            if matched:
                lines = matched
            else:
                # Fallback: rule account may differ by company; keep payable residuals.
                matched = residual_payable.filtered(
                    lambda line, acc=net_account: line.account_id == acc
                )
                if matched:
                    lines = matched
        if len(lines) > 1:
            named = lines.filtered(
                lambda line: (line.name or "").strip().upper().startswith("NET")
            )
            if named:
                lines = named
        if not lines:
            raise UserError(
                _(
                    "No NET salary payable line found for %(employee)s on journal entry %(move)s.",
                    employee=self.employee_id.name,
                    move=self.move_id.display_name,
                )
            )
        return lines

    def _payroll_payment_accounting_company(self, payment_lines):
        """Company of the journal items being paid (may differ from payslip company).

        Example: River Nile payslip posted on the JASMAR Salaries journal → pay
        must use a JASMAR bank journal, not a River Nile one.
        """
        self.ensure_one()
        if payment_lines:
            return min(payment_lines.company_id, key=lambda c: len(c.parent_ids))
        return self.company_id[:1]

    def _payroll_payment_company_ids(self, payment_company=None):
        """Accounting company and its parents, limited to companies this user may access.

        Walks parents only. Child-branch journals must not be offered when the
        payable lines belong to the parent company.
        """
        allowed = set(self.env.user.company_ids.ids)
        company_ids = []
        companies = payment_company or self.company_id
        while companies:
            for company in companies:
                if company.id in allowed and company.id not in company_ids:
                    company_ids.append(company.id)
            companies = companies.parent_id
        return company_ids

    def _prepare_register_payment_context(self, payment_lines):
        ctx = {
            "dont_redirect_to_payments": True,
            "hr_payroll_payment_register": True,
        }
        company = self[:1]._payroll_payment_accounting_company(payment_lines)
        if company:
            ctx["default_company_id"] = company.id
            company_ids = self._payroll_payment_company_ids(company)
            ctx["hr_payroll_payment_company_ids"] = company_ids
            Journal = self.env["account.journal"].with_context(**ctx)
            journals = Journal.search([
                ("company_id", "in", company_ids or [company.id]),
                ("type", "in", ("bank", "cash", "credit")),
            ])
            payable_journals = journals.filtered("outbound_payment_method_line_ids")
            if not company_ids:
                raise UserError(_(
                    "You cannot pay this payslip because you do not have access to company %(company)s. "
                    "Ask an administrator to add that company on your user, then switch to it if needed.",
                    company=company.display_name,
                ))
            if not journals:
                raise UserError(_(
                    "No Bank, Cash, or Credit Card journal exists for %(company)s. "
                    "Pay cannot use Miscellaneous journals such as Salaries. "
                    "Create a Bank or Cash journal in Accounting → Configuration → Journals "
                    "for the company of the journal entry (%(company)s).",
                    company=company.display_name,
                ))
            if not payable_journals:
                raise UserError(_(
                    "Bank/Cash journals exist for %(company)s, but none has an outbound "
                    "payment method. Open the journal and add one (for example Manual).",
                    company=company.display_name,
                ))
            # Prefer a journal of the exact accounting company over a parent.
            same_company = payable_journals.filtered(lambda j: j.company_id == company)
            ctx["default_journal_id"] = (same_company or payable_journals)[:1].id
        if payment_lines:
            residual = abs(sum(payment_lines.mapped("amount_residual_currency")))
            if payment_lines.currency_id[:1].is_zero(residual):
                residual = abs(sum(payment_lines.mapped("amount_residual")))
            ctx["default_amount"] = residual
        if len(self) == 1:
            slip = self
            ctx.update({
                "default_partner_id": slip.employee_id.work_contact_id.id,
                "default_partner_bank_id": slip.employee_id.primary_bank_account_id.id,
            })
        return ctx

    def action_register_payment(self):
        """Open payment wizard for one or many validated payslips (NET lines only)."""
        if not self:
            raise UserError(_("Please select at least one payslip."))

        if len(self.company_id) > 1:
            raise UserError(_("Please select payslips from the same company."))

        if self.filtered(lambda slip: slip.state == "paid"):
            raise UserError(_("You can only register payments for unpaid documents."))

        not_validated = self.filtered(lambda slip: slip.state != "validated")
        if not_validated:
            raise UserError(
                _("Only validated payslips can be paid: %s")
                % ", ".join(not_validated.mapped("display_name"))
            )

        without_move = self.filtered(lambda slip: not slip.move_id)
        if without_move:
            raise UserError(
                _("These payslips have no journal entry: %s")
                % ", ".join(without_move.mapped("display_name"))
            )

        not_posted = self.filtered(lambda slip: slip.move_id.state != "posted")
        if not_posted:
            raise UserError(_("You can only register payment for posted journal entries."))

        payment_lines = self.env["account.move.line"]
        for slip in self:
            bank_accounts = slip.employee_id.sudo().bank_account_ids
            if any(not bank.allow_out_payment for bank in bank_accounts):
                raise UserError(
                    _("An employee bank account is untrusted for %s.")
                    % slip.employee_id.display_name
                )
            lines = slip._get_salary_payment_move_lines()
            not_reconcile = lines.filtered(lambda line: not line.account_id.reconcile)
            if not_reconcile:
                raise UserError(
                    _(
                        "Payable account %(account)s on journal entry %(move)s is not "
                        "reconciliable (payslip %(payslip)s). Enable Allow Reconciliation.",
                        account=not_reconcile[:1].account_id.display_name,
                        move=slip.move_id.display_name,
                        payslip=slip.display_name,
                    )
                )
            payment_lines |= lines

        return payment_lines.action_register_payment(
            ctx=self._prepare_register_payment_context(payment_lines)
        )
