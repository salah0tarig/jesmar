# -*- coding: utf-8 -*-

from odoo import api, fields, models


class BudgetLine(models.Model):
    _inherit = 'budget.line'

    budget_currency_id = fields.Many2one(
        'res.currency',
        related='budget_analytic_id.budget_currency_id',
        string='Currency',
        readonly=True,
        help='Currency from the budget; when set, achieved amount is converted from company currency.',
    )
    budget_display_currency_id = fields.Many2one(
        'res.currency',
        compute='_compute_budget_display_currency_id',
        store=True,
        string='Display Currency',
    )
    outcome_id = fields.Many2one(
        'account.analytic.account',
        string='Outcome',
        ondelete='set null',
        domain="[('parent_id', '=', project_account_id or account_id or False)]",
        help='Outcome analytic account (parent must be project account)',
    )
    output_id = fields.Many2one(
        'account.analytic.account',
        string='Output',
        ondelete='set null',
        domain="[('parent_id', '=', outcome_id or False)]",
        help='Output analytic account (parent must be selected outcome)',
    )
    task_id = fields.Many2one(
        'project.task',
        string='Activity',
        ondelete='set null',
        domain="[('project_id', '=', budget_project_id), ('output_id', '=', output_id)]",
        help='Task/Activity - restricted to tasks linked to the selected Output',
    )  
    budget_project_id = fields.Many2one(
        'project.project',
        related='budget_analytic_id.project_id',
        string='Budget Project',
    )
    project_account_id = fields.Many2one(
        'account.analytic.account',
        related='budget_project_id.account_id',
        string='Project Account',
    )
    budgetary_position = fields.Char(
        string='Budgetary Position',
        help='e.g. Materials, Labor, Equipment',
    )
    # --- Other-currency amounts: pure conversion of base fields, no base logic changes ---
    budget_amount_other = fields.Monetary(
        string='Budgeted (Other)',
        compute='_compute_amounts_other_currency',
        store=True,
        currency_field='budget_display_currency_id',
        help='Budgeted amount converted to the budget currency.',
    )
    committed_amount_other = fields.Monetary(
        string='Committed (Other)',
        compute='_compute_amounts_other_currency',
        store=False,
        currency_field='budget_display_currency_id',
        help='Committed amount converted to the budget currency. Always fresh from purchase/invoice data.',
    )
    achieved_in_currency = fields.Monetary(
        string='Achieved (Other)',
        compute='_compute_amounts_other_currency',
        store=False,
        currency_field='budget_display_currency_id',
        help='Achieved amount converted to the budget currency. Always fresh from purchase/invoice data.',
    )
    theoritical_amount_other = fields.Monetary(
        string='Theoretical (Other)',
        compute='_compute_amounts_other_currency',
        store=True,
        currency_field='budget_display_currency_id',
        help='Theoretical amount converted to the budget currency.',
    )
    balance_other = fields.Monetary(
        string='Balance (Other)',
        compute='_compute_amounts_other_currency',
        store=False,
        currency_field='budget_display_currency_id',
        help='Balance (Budgeted - Achieved) converted to the budget currency. Always fresh.',
    )
    balance = fields.Monetary(
        string='Balance',
        compute='_compute_balance',
        store=True,
        currency_field='company_currency_id',
        help='Budgeted - Achieved',
    )
    company_currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
        string='Company Currency',
    )

    @api.depends('budget_currency_id', 'company_id')
    def _compute_budget_display_currency_id(self):
        for line in self:
            line.budget_display_currency_id = (
                line.budget_currency_id
                or (line.company_id or self.env.company).currency_id
            )

    def _convert_to_other_currency(self, line, amount):
        """Convert amount from company currency to budget currency. Returns amount as-is when no conversion needed."""
        if not amount:
            return 0.0
        company_currency = (line.company_id or self.env.company).currency_id
        if not line.budget_currency_id or line.budget_currency_id == company_currency:
            return amount
        conv_date = line.date_to or fields.Date.context_today(self)
        return company_currency._convert(
            from_amount=amount,
            to_currency=line.budget_currency_id,
            company=line.company_id or self.env.company,
            date=conv_date,
        )

    @api.depends(
        'budget_amount', 'achieved_amount', 'theoritical_amount', 'committed_amount', 'balance',
        'budget_currency_id', 'company_id', 'date_to', 'budget_analytic_state'
    )
    def _compute_amounts_other_currency(self):
        """Convert base amounts to other currency. Uses base fields only, no logic override."""
        if not self:
            return
        # Read committed/achieved directly from budget.report so we get fresh purchase data
        # (committed_amount is non-stored; reading here ensures we react to PO changes)
        grouped = {
            line: (committed, achieved)
            for line, committed, achieved in self.env['budget.report']._read_group(
                domain=[('budget_line_id', 'in', self.ids)],
                groupby=['budget_line_id'],
                aggregates=['committed:sum', 'achieved:sum'],
            )
        }
        for line in self:
            committed, achieved = grouped.get(line, (0.0, 0.0))
            line.budget_amount_other = line._convert_to_other_currency(line, line.budget_amount)
            line.achieved_in_currency = line._convert_to_other_currency(line, achieved)
            line.theoritical_amount_other = line._convert_to_other_currency(line, line.theoritical_amount)
            line.committed_amount_other = line._convert_to_other_currency(line, committed)
            line.balance_other = line._convert_to_other_currency(line, (line.budget_amount or 0.0) - achieved)

    @api.depends('budget_amount', 'achieved_amount')
    def _compute_balance(self):
        for line in self:
            line.balance = (line.budget_amount or 0.0) - (line.achieved_amount or 0.0)

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        budget_analytic_id = self.env.context.get('default_budget_analytic_id') or defaults.get('budget_analytic_id')
        if budget_analytic_id and (not fields_list or 'account_id' in fields_list):
            budget_analytic = self.env['budget.analytic'].browse(budget_analytic_id)
            if budget_analytic.project_id and budget_analytic.project_id.account_id:
                defaults['account_id'] = budget_analytic.project_id.account_id.id
        return defaults

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            output_id = vals.get('output_id')
            if output_id and 'account_id' not in vals:
                vals['account_id'] = output_id
        return super().create(vals_list)

    def write(self, vals):
        if 'output_id' in vals and vals.get('output_id') and 'account_id' not in vals:
            vals['account_id'] = vals['output_id']
        return super().write(vals)

    @api.onchange('budget_analytic_id', 'budget_project_id')
    def _onchange_project_clear_outcome_output(self):
        """When budget/project changes, clear outcome and output; set account_id from project."""
        if self.budget_project_id or self.budget_analytic_id:
            self.outcome_id = False
            self.output_id = False
            if self.project_account_id:
                self.account_id = self.project_account_id

    @api.onchange('outcome_id')
    def _onchange_outcome_clear_output(self):
        """When outcome changes, clear output."""
        if self.outcome_id:
            self.output_id = False

    @api.onchange('outcome_id', 'output_id', 'budget_project_id')
    def _onchange_outcome_output_set_account(self):
        """Set account_id (analytic plan) for budget matching.
        Must use output_id when set, so PO/bill lines with activity_id match this budget line.
        Committed = uninvoiced PO amount; Achieved = invoiced/billed amount."""
        if self.output_id:
            self.account_id = self.output_id
        elif self.outcome_id:
            self.account_id = self.outcome_id
        elif self.project_account_id:
            self.account_id = self.project_account_id

    @api.onchange('output_id')
    def _onchange_output_clear_task(self):
        """When output changes, clear task if it no longer matches the new output."""
        if self.output_id and self.task_id and self.task_id.output_id != self.output_id:
            self.task_id = False

    @api.onchange('task_id')
    def _onchange_task_id(self):
        """When Activity (Task) is selected, auto-fill Outcome, Output and Analytic Account.
        account_id must = output_id so PO/bill lines (with activity's output in analytic_distribution)
        match this budget line for committed/achieved amounts."""
        if self.task_id:
            self.outcome_id = self.task_id.outcome_id
            self.output_id = self.task_id.output_id
            if self.output_id:
                self.account_id = self.output_id
            elif self.project_account_id:
                self.account_id = self.project_account_id

