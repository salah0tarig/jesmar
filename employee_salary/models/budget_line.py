# -*- coding: utf-8 -*-

from odoo import models


class BudgetLine(models.Model):
    _inherit = "budget.line"

    def _get_budget_line_analytic_account(self):
        """Analytic account used for payroll / expense achieved matching."""
        self.ensure_one()
        if self.task_id and self.task_id.activity_analytic_account_id:
            return self.task_id.activity_analytic_account_id
        return self.account_id
