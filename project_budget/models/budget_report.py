# -*- coding: utf-8 -*-

from odoo import fields, models


class BudgetReport(models.Model):
    _inherit = 'budget.report'

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
