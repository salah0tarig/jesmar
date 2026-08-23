# -*- coding: utf-8 -*-

from odoo import models


class BudgetLine(models.Model):
    _inherit = "budget.line"

    def _get_budget_line_analytic_account(self):
        return super()._get_budget_line_analytic_account()
