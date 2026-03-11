# -*- coding: utf-8 -*-

from odoo import fields, models
from odoo.tools import SQL


class BudgetReport(models.Model):
    _inherit = 'budget.report'

    def _get_pol_query(self, plan_fnames):
        """Filter by product: match when budget line has product_id, only count PO lines with same product.
        Activity is matched via analytic account (bl.account_id = activity_analytic_account_id from pol.analytic_json)."""
        query = super()._get_pol_query(plan_fnames)
        return SQL(
            query.code + " AND (bl.product_id IS NULL OR pol.product_id = bl.product_id)",
            *query.params
        )

    def _get_aal_query(self, plan_fnames):
        """Achieved from account.analytic.line (when bill posted).
        Match by activity_analytic_account_id (AAL analytic account = bl.account_id) and product (aml.product_id = bl.product_id).
        No PO dependency - works for manual bills too."""
        query = super()._get_aal_query(plan_fnames)
        # Add aml JOIN to get product from move line
        from_clause = "FROM account_analytic_line aal\n         LEFT JOIN account_move_line aml ON aal.move_line_id = aml.id\n         LEFT JOIN budget_line bl"
        orig_from = "FROM account_analytic_line aal\n         LEFT JOIN budget_line bl"
        new_code = query.code.replace(orig_from, from_clause)
        # Filter by product: bl.account_id already matches activity_analytic_account_id via plan condition
        product_cond = " AND (bl.product_id IS NULL OR aml.product_id = bl.product_id)"
        new_code = new_code.replace(
            "LEFT JOIN account_account aa ON aa.id = aal.general_account_id",
            product_cond + "\n         LEFT JOIN account_account aa ON aa.id = aal.general_account_id"
        )
        return SQL(new_code, *query.params)

    outcome_id = fields.Many2one(
        'account.analytic.account',
        related='budget_line_id.outcome_id',
        string='Outcome',
        readonly=True,
    )
    output_id = fields.Many2one(
        'account.analytic.account',
        related='budget_line_id.output_id',
        string='Output',
        readonly=True,
    )
    task_id = fields.Many2one(
        'project.task',
        related='budget_line_id.task_id',
        string='Activity',
        readonly=True,
    )
    budget_currency_id = fields.Many2one(
        'res.currency',
        related='budget_line_id.budget_currency_id',
        string='Currency',
        readonly=True,
    )
    budget_display_currency_id = fields.Many2one(
        'res.currency',
        related='budget_line_id.budget_display_currency_id',
        string='Display Currency',
    )
    budget_amount_other = fields.Monetary(
        related='budget_line_id.budget_amount_other',
        string='Budgeted (Other)',
        readonly=True,
        currency_field='budget_display_currency_id',
    )
    committed_amount_other = fields.Monetary(
        related='budget_line_id.committed_amount_other',
        string='Committed (Other)',
        readonly=True,
        currency_field='budget_display_currency_id',
    )
    achieved_in_currency = fields.Monetary(
        related='budget_line_id.achieved_in_currency',
        string='Achieved (Other)',
        readonly=True,
        currency_field='budget_display_currency_id',
    )
    theoritical_amount_other = fields.Monetary(
        related='budget_line_id.theoritical_amount_other',
        string='Theoretical (Other)',
        readonly=True,
        currency_field='budget_display_currency_id',
    )
    balance_other = fields.Monetary(
        related='budget_line_id.balance_other',
        string='Balance (Other)',
        readonly=True,
        currency_field='budget_display_currency_id',
    )
    balance = fields.Monetary(
        related='budget_line_id.balance',
        string='Balance',
        readonly=True,
        currency_field='company_currency_id',
    )
    company_currency_id = fields.Many2one(
        related='company_id.currency_id',
        string='Company Currency',
    )
