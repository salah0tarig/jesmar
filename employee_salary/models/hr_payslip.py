# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare, float_is_zero, float_round

STAFF_COST_RULE_CODE = "STAFF_COST"


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    salary_allocation_ids = fields.One2many(
        "hr.employee.salary.allocation",
        "payslip_id",
        string="Salary budget allocations",
        help="Optional override for this payslip only. Leave empty to use the employee record defaults.",
        copy=True,
    )

    @api.depends("line_ids.total", "struct_id.rule_ids.appears_on_employee_cost_dashboard")
    def _compute_basic_net(self):
        super()._compute_basic_net()
        employer_rules = ("EMP_SI", "EMP_MI")
        slips_with_rules = self.filtered(
            lambda p: p.struct_id.rule_ids.filtered(lambda r: r.code in employer_rules)
        )
        if not slips_with_rules:
            return
        line_values = slips_with_rules._get_line_values(employer_rules)
        for payslip in slips_with_rules:
            slip_id = payslip._origin.id
            si = line_values.get("EMP_SI", {}).get(slip_id, {}).get("total", 0.0)
            mi = line_values.get("EMP_MI", {}).get(slip_id, {}).get("total", 0.0)
            staff_cost = payslip._get_total_employee_cost_amount()
            if staff_cost:
                payslip.employer_cost = staff_cost
            else:
                payslip.employer_cost = payslip.gross_wage + si + mi

    def _get_total_employee_cost_amount(self):
        """Total Employee Cost (= contract total_staff_cost)."""
        self.ensure_one()
        slip_id = self._origin.id or self.id
        if slip_id:
            line_values = self._get_line_values([STAFF_COST_RULE_CODE])
            staff_line = line_values.get(STAFF_COST_RULE_CODE, {}).get(slip_id, {})
            staff_total = staff_line.get("total", 0.0)
            if staff_total:
                return staff_total
        if self.version_id.total_staff_cost:
            return self.version_id.total_staff_cost
        line_values = self._get_line_values(["GROSS", "EMP_SI", "EMP_MI"])
        gross = line_values.get("GROSS", {}).get(slip_id, {}).get("total", 0.0)
        si = line_values.get("EMP_SI", {}).get(slip_id, {}).get("total", 0.0)
        mi = line_values.get("EMP_MI", {}).get(slip_id, {}).get("total", 0.0)
        return gross + si + mi

    def _get_effective_salary_allocations(self):
        self.ensure_one()
        if self.salary_allocation_ids:
            return self.salary_allocation_ids.filtered(lambda a: a.percentage > 0)
        if self.version_id:
            return self.version_id.salary_allocation_ids.filtered(lambda a: a.percentage > 0)
        return self.env["hr.employee.salary.allocation"]

    def _validate_effective_salary_allocations(self):
        for slip in self:
            allocations = slip._get_effective_salary_allocations()
            if not allocations:
                continue
            label = slip.display_name or _("Payslip")
            self.env["hr.employee.salary.allocation"]._validate_allocation_set(
                allocations, label
            )

    def action_payslip_done(self):
        self._validate_effective_salary_allocations()
        return super().action_payslip_done()

    def action_copy_salary_allocations_from_contract(self):
        Allocation = self.env["hr.employee.salary.allocation"]
        for slip in self:
            if slip.state != "draft":
                raise UserError(_("Copy allocations is only allowed on draft payslips."))
            if not slip.version_id.salary_allocation_ids:
                raise UserError(_("No salary allocations on the employee record."))
            slip.salary_allocation_ids.unlink()
            for line in slip.version_id.salary_allocation_ids:
                Allocation.create({
                    "payslip_id": slip.id,
                    "budget_line_id": line.budget_line_id.id,
                    "percentage": line.percentage,
                })
        return True

    def _is_expense_account(self, account):
        if not account:
            return False
        if account.internal_group == "expense":
            return True
        return account.account_type in (
            "expense",
            "expense_direct_cost",
            "expense_depreciation",
        )

    def _get_staff_cost_expense_account(self):
        """Expense account for Total Employee Cost (rule debit, else Salaries journal default)."""
        self.ensure_one()
        staff_line = self.line_ids.filtered(lambda l: l.code == STAFF_COST_RULE_CODE)[:1]
        if staff_line and staff_line.salary_rule_id.account_debit:
            return staff_line.salary_rule_id.account_debit
        return self.struct_id.journal_id.default_account_id

    def _split_expense_line_by_allocations(self, line_vals_list, allocations):
        """Split an expense debit by allocation % (totals preserved)."""
        precision = self.env["decimal.precision"].precision_get("Payroll")
        allocs = allocations.sorted("id")
        total_pct = sum(allocs.mapped("percentage")) or 100.0
        result = []
        for line_vals in line_vals_list:
            base_debit = line_vals.get("debit") or 0.0
            if base_debit <= 0:
                result.append(line_vals)
                continue
            running_debit = 0.0
            for idx, alloc in enumerate(allocs):
                is_last = idx == len(allocs) - 1
                if is_last:
                    split_debit = float_round(
                        base_debit - running_debit, precision_digits=precision
                    )
                else:
                    split_debit = float_round(
                        base_debit * alloc.percentage / total_pct,
                        precision_digits=precision,
                    )
                    running_debit += split_debit
                if float_compare(split_debit, 0.0, precision_digits=precision) <= 0:
                    continue
                split_vals = dict(line_vals)
                split_vals["debit"] = split_debit
                if alloc.analytic_account_id:
                    split_vals["analytic_distribution"] = {
                        str(alloc.analytic_account_id.id): 100.0
                    }
                if alloc.product_id:
                    split_vals["product_id"] = alloc.product_id.id
                result.append(split_vals)
        return result or line_vals_list

    def _prepare_staff_cost_expense_vals(self, date, amount, account):
        """Build move line values for the Total Employee Cost expense debit."""
        self.ensure_one()
        staff_line = self.line_ids.filtered(lambda l: l.code == STAFF_COST_RULE_CODE)[:1]
        rule = staff_line.salary_rule_id if staff_line else self.env["hr.salary.rule"]
        batch_lines = self.company_id.batch_payroll_move_lines
        if not batch_lines and rule and rule.employee_move_line:
            partner = self.employee_id.work_contact_id
        else:
            partner = staff_line.partner_id if staff_line else self.env["res.partner"]
        name = (
            staff_line.name
            if staff_line and rule.split_move_lines
            else (rule.name if rule else _("Total Employee Cost"))
        )
        return {
            "name": name,
            "partner_id": partner.id if partner else False,
            "account_id": account.id,
            "journal_id": self.struct_id.journal_id.id,
            "date": date,
            "debit": amount,
            "credit": 0.0,
            "analytic_distribution": (
                rule.analytic_distribution
                or self.version_id.analytic_distribution
                if rule
                else self.version_id.analytic_distribution
            ),
            "tax_tag_ids": staff_line.debit_tag_ids.ids if staff_line else [],
            "tax_ids": [(4, tax_id) for tax_id in account.tax_ids.ids],
        }

    def _ensure_total_employee_cost_expense(self, new_lines, date):
        """Post Total Employee Cost as the expense debit instead of Adjustment Entry.

        Only when the missing debit equals Total Employee Cost (typical setup: payable
        credits only, no salary expense rules). Otherwise leave the move unchanged.
        """
        self.ensure_one()
        precision = self.env["decimal.precision"].precision_get("Payroll")
        staff_line = self.line_ids.filtered(
            lambda l: l.code == STAFF_COST_RULE_CODE and not float_is_zero(l.total, precision_digits=precision)
        )[:1]
        if not staff_line:
            return

        # Already posted by standard payroll (rule has debit account).
        if staff_line.salary_rule_id.account_debit:
            return

        debit_sum = sum(line.get("debit") or 0.0 for line in new_lines)
        credit_sum = sum(line.get("credit") or 0.0 for line in new_lines)
        gap = credit_sum - debit_sum
        staff_cost = self._get_total_employee_cost_amount()
        if float_is_zero(staff_cost, precision_digits=precision):
            return
        if float_compare(gap, staff_cost, precision_digits=precision) != 0:
            return

        account = self._get_staff_cost_expense_account()
        if not account:
            raise UserError(
                _(
                    'Set a Debit Account on the «Total Employee Cost» salary rule, '
                    'or a default account on the Expense Journal "%s", '
                    "so payroll can post Total Employee Cost instead of an Adjustment Entry."
                )
                % self.struct_id.journal_id.name
            )

        line_vals_list = [self._prepare_staff_cost_expense_vals(date, staff_cost, account)]
        allocations = self._get_effective_salary_allocations()
        if allocations:
            line_vals_list = self._split_expense_line_by_allocations(line_vals_list, allocations)
        new_lines.extend(line_vals_list)

    def _prepare_slip_lines(self, date, line_ids):
        new_lines = super()._prepare_slip_lines(date, line_ids)
        self._ensure_total_employee_cost_expense(new_lines, date)
        return new_lines

    def _prepare_line_values(self, line, account, date, debit, credit):
        """When allocations exist, split only the Total Employee Cost expense debit."""
        line_vals_list = super()._prepare_line_values(line, account, date, debit, credit)
        allocations = self._get_effective_salary_allocations()
        if not allocations:
            return line_vals_list
        if line.code != STAFF_COST_RULE_CODE or debit <= 0:
            return line_vals_list
        if not self._is_expense_account(account):
            return line_vals_list
        return self._split_expense_line_by_allocations(line_vals_list, allocations)
