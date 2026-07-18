from odoo import _, models
from odoo.exceptions import UserError


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    def _get_salary_payment_move_lines(self):
        """Payable lines for this employee's NET salary only (not the whole batch move)."""
        self.ensure_one()
        if not self.move_id:
            raise UserError(_("No journal entry is linked to this payslip."))

        net_rule = self.struct_id.rule_ids.filtered(lambda r: r.code == "NET")[:1]
        if not net_rule or not net_rule.account_credit:
            raise UserError(_("Configure a credit account on the NET salary rule."))

        partner = self.employee_id.work_contact_id
        lines = self.move_id.line_ids.filtered(
            lambda line, acc=net_rule.account_credit, partner=partner: (
                line.account_id == acc
                and line.partner_id == partner
                and line.account_type == "liability_payable"
            )
        )
        if not lines:
            raise UserError(
                _(
                    "No NET salary payable line found for %(employee)s on journal entry %(move)s.",
                    employee=self.employee_id.name,
                    move=self.move_id.display_name,
                )
            )
        return lines

    def _prepare_register_payment_context(self):
        ctx = {
            "dont_redirect_to_payments": True,
            "hr_payroll_payment_register": True,
        }
        if len(self.company_id) == 1:
            ctx["default_company_id"] = self.company_id.id
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

        for slip in self:
            net_rule = slip.struct_id.rule_ids.filtered(lambda r: r.code == "NET")[:1]
            if not net_rule or not net_rule.account_credit.reconcile:
                raise UserError(
                    _("The credit account on the NET salary rule is not reconciliable for %s.")
                    % slip.display_name
                )
            bank_accounts = slip.employee_id.sudo().bank_account_ids
            if any(not bank.allow_out_payment for bank in bank_accounts):
                raise UserError(
                    _("An employee bank account is untrusted for %s.")
                    % slip.employee_id.display_name
                )

        payment_lines = self.env["account.move.line"]
        for slip in self:
            payment_lines |= slip._get_salary_payment_move_lines()

        return payment_lines.action_register_payment(ctx=self._prepare_register_payment_context())
