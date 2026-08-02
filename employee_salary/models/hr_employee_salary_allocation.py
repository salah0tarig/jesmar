# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class HrEmployeeSalaryAllocation(models.Model):
    _name = "hr.employee.salary.allocation"
    _description = "Employee salary budget allocation"
    _order = "id"

    version_id = fields.Many2one(
        "hr.version",
        string="Employee record",
        ondelete="cascade",
        index=True,
    )
    payslip_id = fields.Many2one(
        "hr.payslip",
        string="Payslip override",
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        compute="_compute_company_id",
        store=True,
        readonly=True,
    )
    budget_line_id = fields.Many2one(
        "budget.line",
        string="Budget line",
        required=True,
        ondelete="restrict",
        domain="[('budget_analytic_id.state', '=', 'confirmed'), ('budget_analytic_id.company_id', '=', company_id)]",
    )
    budget_id = fields.Many2one(
        "budget.analytic",
        related="budget_line_id.budget_analytic_id",
        string="Budget",
        store=True,
        readonly=True,
    )
    budget_project_id = fields.Many2one(
        "project.project",
        related="budget_line_id.budget_project_id",
        string="Project",
        store=True,
        readonly=True,
    )
    product_id = fields.Many2one(
        "product.product",
        related="budget_line_id.product_id",
        string="Product",
        store=True,
        readonly=True,
    )
    analytic_account_id = fields.Many2one(
        "account.analytic.account",
        string="Analytic account",
        compute="_compute_analytic_account_id",
        store=True,
        readonly=True,
    )
    percentage = fields.Float(
        string="Allocation %",
        required=True,
        default=100.0,
        help="Share of Total Employee Cost charged to this budget line (must total 100% per employee or payslip).",
    )
    total_employee_cost = fields.Monetary(
        string="Total Employee Cost",
        compute="_compute_allocated_amount",
        currency_field="currency_id",
        help="Approved staff cost used as the allocation base.",
    )
    allocated_amount = fields.Monetary(
        string="Allocated Amount",
        compute="_compute_allocated_amount",
        currency_field="currency_id",
        help="Total Employee Cost × allocation %.",
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        compute="_compute_currency_id",
        readonly=True,
    )

    @api.depends("company_id")
    def _compute_currency_id(self):
        for rec in self:
            rec.currency_id = rec.company_id.currency_id or self.env.company.currency_id

    @api.depends(
        "percentage",
        "version_id.total_staff_cost",
        "payslip_id.version_id.total_staff_cost",
        "payslip_id.line_ids.total",
        "payslip_id.line_ids.code",
    )
    def _compute_allocated_amount(self):
        for rec in self:
            staff_cost = rec._get_allocation_staff_cost_base()
            rec.total_employee_cost = staff_cost
            rec.allocated_amount = (
                staff_cost * rec.percentage / 100.0 if staff_cost and rec.percentage else 0.0
            )

    def _get_allocation_staff_cost_base(self):
        self.ensure_one()
        if self.payslip_id:
            return self.payslip_id._get_total_employee_cost_amount()
        if self.version_id:
            return self.version_id.total_staff_cost or 0.0
        return 0.0

    @api.depends("version_id.company_id", "payslip_id.company_id")
    def _compute_company_id(self):
        for rec in self:
            rec.company_id = (
                rec.payslip_id.company_id
                or rec.version_id.company_id
                or self.env.company
            )

    @api.depends(
        "budget_line_id",
        "budget_line_id.account_id",
        "budget_line_id.task_id",
        "budget_line_id.task_id.activity_analytic_account_id",
    )
    def _compute_analytic_account_id(self):
        for rec in self:
            line = rec.budget_line_id
            if not line:
                rec.analytic_account_id = False
                continue
            rec.analytic_account_id = line._get_budget_line_analytic_account()

    @api.constrains("version_id", "payslip_id")
    def _check_single_parent(self):
        for rec in self:
            if bool(rec.version_id) == bool(rec.payslip_id):
                raise ValidationError(
                    _("Each allocation must belong to exactly one employee record or one payslip.")
                )

    @api.constrains("percentage")
    def _check_percentage_positive(self):
        for rec in self:
            if rec.percentage <= 0:
                raise ValidationError(_("Allocation percentage must be greater than zero."))

    @api.constrains("budget_line_id", "analytic_account_id")
    def _check_budget_line_analytic(self):
        for rec in self:
            if rec.budget_line_id and not rec.analytic_account_id:
                raise ValidationError(
                    _(
                        "Budget line «%(line)s» has no activity analytic account. "
                        "Set Activity on the budget line or choose another line."
                    )
                    % {"line": rec.budget_line_id.display_name}
                )

    @api.model
    def _validate_allocation_set(self, allocations, label):
        allocations = allocations.filtered(lambda a: a.percentage > 0)
        if not allocations:
            return
        total = sum(allocations.mapped("percentage"))
        if abs(total - 100.0) > 0.01:
            raise ValidationError(
                _("%(label)s salary allocations must total 100%% (currently %(total).2f%%).")
                % {"label": label, "total": total}
            )
