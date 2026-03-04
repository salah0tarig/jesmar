# -*- coding: utf-8 -*-

from odoo import api, fields, models


class BudgetLine(models.Model):
    _inherit = 'budget.line'

    budget_currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        help='Optional: when set, achieved amount is converted from company currency to this currency using Odoo exchange rates.',
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
        domain="[('project_id', '=', budget_project_id)]",
        help='Task/Activity - Analytic Account auto-fills from Output when selected',
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
    achieved_in_currency = fields.Monetary(
        string='Achieved In Currency',
        compute='_compute_achieved_in_currency',
        store=True,
        currency_field='budget_display_currency_id',
        help='Achieved amount. When Currency is set, converted from company currency using Odoo exchange rate.',
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

    @api.depends('budget_currency_id', 'company_id', 'date_to', 'budget_analytic_state')
    def _compute_achieved_in_currency(self):
        """When budget_currency_id is set, convert achieved amount from company currency."""
        if not self:
            return
        # Read achieved directly from budget.report to avoid stale achieved_amount when state changes
        grouped = dict(self.env['budget.report']._read_group(
            domain=[('budget_line_id', 'in', self.ids)],
            groupby=['budget_line_id'],
            aggregates=['achieved:sum'],
        ))
        for line in self:
            achieved = grouped.get(line, 0.0)
            company_currency = (line.company_id or self.env.company).currency_id
            if line.budget_currency_id and line.budget_currency_id != company_currency:
                conv_date = line.date_to or fields.Date.context_today(self)
                line.achieved_in_currency = company_currency._convert(
                    from_amount=achieved,
                    to_currency=line.budget_currency_id,
                    company=line.company_id or self.env.company,
                    date=conv_date,
                )
            else:
                line.achieved_in_currency = achieved

    @api.depends('budget_amount', 'achieved_amount')
    def _compute_balance(self):
        for line in self:
            line.balance = (line.budget_amount or 0.0) - (line.achieved_amount or 0.0)

    @api.onchange('budget_analytic_id', 'budget_project_id')
    def _onchange_project_clear_outcome_output(self):
        """When budget/project changes, clear outcome and output (different hierarchy)."""
        if self.budget_project_id or self.budget_analytic_id:
            self.outcome_id = False
            self.output_id = False

    @api.onchange('outcome_id')
    def _onchange_outcome_clear_output(self):
        """When outcome changes, clear output."""
        if self.outcome_id:
            self.output_id = False

    @api.onchange('outcome_id', 'output_id')
    def _onchange_outcome_output_set_account(self):
        """When outcome or output is set, update account_id for allocation."""
        if self.output_id:
            self.account_id = self.output_id
        elif self.outcome_id:
            self.account_id = self.outcome_id

    @api.onchange('task_id')
    def _onchange_task_id(self):
        """When Activity (Task) is selected, auto-fill Outcome, Output and Analytic Account."""
        if self.task_id:
            self.outcome_id = self.task_id.outcome_id
            self.output_id = self.task_id.output_id
            account = (
                self.task_id.output_id
                or self.task_id.outcome_id
                or (self.task_id.project_id.account_id if self.task_id.project_id else False)
            )
            if account:
                self.account_id = account

