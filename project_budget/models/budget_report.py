# -*- coding: utf-8 -*-

from odoo import fields, models
from odoo.tools import SQL


class BudgetReport(models.Model):
    _inherit = 'budget.report'

    def _get_pol_query(self, plan_fnames):
        """Same as Odoo default. Add: (1) activity match when bl has task, (2) product filter.
        Odoo matches via plan: bl.x = a.x from analytic_json. For project hierarchy we add
        pol.activity_id = bl.task_id when task set (purchase_order_line has activity_id)."""
        query = super()._get_pol_query(plan_fnames)
        # %(condition)s is expanded by SQL - use stable anchor "LEFT JOIN budget_analytic"
        # When POL has activity: only match budget lines WITH that task (avoid duplicate rows)
        # When POL has no activity: match by plan only (bl.task_id IS NULL satisfies)
        activity_cond = (
            " AND (bl.task_id IS NULL OR pol.activity_id = bl.task_id)"
            " AND (pol.activity_id IS NULL OR bl.task_id IS NOT NULL)"
        )
        product_cond = " AND (bl.product_id IS NULL OR pol.product_id = bl.product_id)"
        budget_analytic_join = "LEFT JOIN budget_analytic ba ON ba.id = bl.budget_analytic_id"
        new_code = query.code.replace(
            budget_analytic_join,
            activity_cond + "\n         " + budget_analytic_join,
        )
        new_code = new_code.replace(
            "AND ba.budget_type != 'revenue'",
            "AND ba.budget_type != 'revenue'\n               " + product_cond.strip(),
        )
        return SQL(new_code, *query.params)

    def _get_aal_query(self, plan_fnames):
        """Same as Odoo default, add product filter via aml: bl.product_id IS NULL OR aml.product_id = bl.product_id.
        Matching uses plan fields (bl.account_id = aal.account_id) - ensure budget line has account_id set."""
        query = super()._get_aal_query(plan_fnames)
        from_clause = (
            "FROM account_analytic_line aal\n         LEFT JOIN account_move_line aml ON aal.move_line_id = aml.id\n         "
            "LEFT JOIN budget_line bl"
        )
        orig_from = "FROM account_analytic_line aal\n         LEFT JOIN budget_line bl"
        new_code = query.code.replace(orig_from, from_clause)
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
