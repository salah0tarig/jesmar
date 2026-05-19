# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError

EXPENSE_APPROVAL_STATE = [
    ('submitted', 'Submitted'),
    ('budget_owner', 'Budget Owner'),
    ('approved', 'Approved'),
    ('refused', 'Refused'),
]

class HrExpense(models.Model):
    _inherit = "hr.expense"

    payment_mode = fields.Selection(
        selection=[
            ("own_account", _("Employee (to reimburse)")),
            ("company_account", _("Company")),
        ],
        string="Paid By",
        default="company_account",
        required=True,
        tracking=True,
    )

    state = fields.Selection(
        selection=[
            # Pre-Approval states
            ('draft', 'Draft'),
            # Approval states
            ('submitted', 'Submitted'),
            ('budget_owner', 'Budget Owner'),
            ('approved', 'Approved'),
            ('posted', 'Posted'),
            # Payment states
            ('in_payment', 'In Payment'),
            ('paid', 'Paid'),
            # refused state is always last
            ('refused', 'Refused'),
        ],
        string="Status",
    )
    approval_state = fields.Selection(selection=EXPENSE_APPROVAL_STATE, copy=False, readonly=True)

    mission_start_date = fields.Date(string="Mission From")
    mission_end_date = fields.Date(string="Mission To")
    mission_destination = fields.Char(string="Mission Destination")
    mission_purpose = fields.Text(string="Mission Purpose & Justification")
    budget_id = fields.Many2one(
        "budget.analytic",
        string="Budget",
        ondelete="restrict",
        help="Budget header used for this expense.",
    )
    budget_line_id = fields.Many2one(
        "budget.line",
        string="Budget Line",
        ondelete="restrict",
        domain="[('budget_analytic_id', '=', budget_id)]",
        help="Specific budget line to charge this expense to.",
    )
    budget_remaining_amount = fields.Monetary(
        string="Budget Remaining",
        currency_field="company_currency_id",
        compute="_compute_budget_check_fields",
        store=False,
    )
    budget_state = fields.Selection(
        [
            ("in_budget", "In Budget"),
            ("budget_exceed", "Budget Exceed"),
        ],
        string="Budget State",
        compute="_compute_budget_check_fields",
        store=False,
    )

    @api.onchange("budget_line_id")
    def _onchange_budget_line_id(self):
        if self.budget_line_id:
            self.budget_id = self.budget_line_id.budget_analytic_id
            acc = self.budget_line_id.task_id.activity_analytic_account_id
            if acc:
                self.analytic_distribution = {str(acc.id): 100}
        else:
            self.analytic_distribution = False

    @api.depends(
        "product_id",
        "account_id",
        "employee_id",
        "budget_line_id",
        "budget_line_id.task_id",
        "budget_line_id.task_id.activity_analytic_account_id",
    )
    def _compute_analytic_distribution(self):
        """Budget line activity analytic account at 100%; otherwise default distribution rules."""
        with_budget_analytic = self.filtered(
            lambda e: e.budget_line_id
            and e.budget_line_id.task_id
            and e.budget_line_id.task_id.activity_analytic_account_id
        )
        for expense in with_budget_analytic:
            acc = expense.budget_line_id.task_id.activity_analytic_account_id
            expense.analytic_distribution = {str(acc.id): 100}
        super(HrExpense, self - with_budget_analytic)._compute_analytic_distribution()

    def _expense_amount_in_company_currency(self):
        """Amount to compare against budget line (company currency)."""
        self.ensure_one()
        company_currency = self.company_currency_id or self.env.company.currency_id
        if self.currency_id and self.currency_id != company_currency:
            return self.currency_id._convert(
                self.total_amount_currency or 0.0,
                company_currency,
                self.company_id or self.env.company,
                self.date or fields.Date.context_today(self),
            )
        return self.total_amount or self.total_amount_currency or 0.0

    def _budget_line_remaining(self, budget_line):
        """Read budget line balance after refreshing achieved/committed (balance formula unchanged)."""
        budget_line.invalidate_recordset(
            ["committed_amount", "achieved_amount", "committed_percentage", "achieved_percentage", "balance"]
        )
        budget_line._compute_all()
        return budget_line.balance or 0.0

    @api.depends(
        "budget_line_id",
        "total_amount",
        "total_amount_currency",
        "currency_id",
        "company_currency_id",
        "date",
        "company_id",
    )
    def _compute_budget_check_fields(self):
        for rec in self:
            if rec.budget_line_id:
                remaining = rec._budget_line_remaining(rec.budget_line_id)
                required_amount = rec._expense_amount_in_company_currency()
                rec.budget_remaining_amount = remaining
                rec.budget_state = (
                    "budget_exceed" if required_amount > remaining else "in_budget"
                )
            else:
                rec.budget_remaining_amount = 0.0
                rec.budget_state = False

    @api.onchange(
        "budget_line_id",
        "total_amount",
        "total_amount_currency",
        "currency_id",
    )
    def _onchange_budget_check_fields(self):
        """Refresh budget remaining in the form when line or amount changes."""
        for rec in self:
            if rec.budget_line_id:
                remaining = rec._budget_line_remaining(rec.budget_line_id)
                required_amount = rec._expense_amount_in_company_currency()
                rec.budget_remaining_amount = remaining
                rec.budget_state = (
                    "budget_exceed" if required_amount > remaining else "in_budget"
                )
            else:
                rec.budget_remaining_amount = 0.0
                rec.budget_state = False

    def action_submit(self):
        """Route submitted expenses to Budget Owner first."""
        user = self.env.user
        for expense in self:
            if user.employee_id != expense.employee_id and not expense.can_approve:
                raise UserError(_("You do not have the required permission to submit this expense."))
            if not expense.product_id:
                raise UserError(_("You can not submit an expense without a category."))
            if not expense.manager_id:
                expense.sudo().manager_id = expense._get_default_responsible_for_approval()
        self.approval_state = "budget_owner"
        self.sudo().update_activities_and_mails()

    def action_budget_owner_approve(self):
        self.ensure_one()
        if not self.env.user.has_group("project_budget.group_budget_owner"):
            raise UserError(_("Only Budget Owner can approve this step."))
        if self.state != "budget_owner":
            return
        if self.budget_line_id and self.budget_state == "budget_exceed":
            raise UserError(
                _(
                    "Budget exceeded for line %(line)s.\n"
                    "Remaining: %(remaining).2f, Expense: %(amount).2f.\n"
                    "Budget Owner cannot approve until amount is within remaining budget.",
                    line=self.budget_line_id.display_name,
                    remaining=self.budget_remaining_amount,
                    amount=self._expense_amount_in_company_currency(),
                )
            )
        self.sudo()._validate_distribution(
            account=self.account_id.id,
            product=self.product_id.id,
            business_domain="expense",
            company_id=self.company_id.id,
        )
        # Base _do_approve only handles states draft/submitted; custom budget_owner
        # must be approved explicitly.
        self.sudo().write(
            {
                "approval_state": "approved",
                "manager_id": self.env.user.id,
                "approval_date": fields.Datetime.now(),
            }
        )
        self.sudo().update_activities_and_mails()

    def action_budget_owner_reject(self):
        self.ensure_one()
        if not self.env.user.has_group("project_budget.group_budget_owner"):
            raise UserError(_("Only Budget Owner can reject this step."))
        if self.state != "budget_owner":
            return
        self.sudo()._do_refuse(_("Rejected by Budget Owner"))