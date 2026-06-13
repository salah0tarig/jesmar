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

    def action_register_payment(self):
        if any(state == "paid" for state in self.mapped("state")):
            raise UserError(_("You can only register payments for unpaid documents."))
        if not self.struct_id.rule_ids.filtered(lambda r: r.code == "NET").account_credit.reconcile:
            raise UserError(_("The credit account on the NET salary rule is not reconciliable"))
        bank_accounts = self.employee_id.sudo().bank_account_ids
        if any(not bank.allow_out_payment for bank in bank_accounts):
            raise UserError(_("An employee bank account is untrusted"))
        if any(m.state != "posted" for m in self.move_id):
            raise UserError(_("You can only register payment for posted journal entries."))

        payment_lines = self.env["account.move.line"]
        for slip in self:
            payment_lines |= slip._get_salary_payment_move_lines()

        ctx = {
            "default_partner_id": self.employee_id.work_contact_id.id,
            "default_partner_bank_id": self.employee_id.primary_bank_account_id.id,
            "default_company_id": self.company_id.id,
        }
        return payment_lines.action_register_payment(ctx=ctx)
