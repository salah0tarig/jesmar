# -*- coding: utf-8 -*-

from odoo import api, fields, models


class BudgetLine(models.Model):
    _inherit = 'budget.line'

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
    budgetary_position = fields.Char(
        string='Budgetary Position',
        help='e.g. Materials, Labor, Equipment',
    )

    @api.onchange('task_id')
    def _onchange_task_id(self):
        """When Activity (Task) is selected, auto-fill Analytic Account from Task's Output."""
        if self.task_id:
            account = (
                self.task_id.output_id
                or self.task_id.outcome_id
                or (self.task_id.project_id.account_id if self.task_id.project_id else False)
            )
            if account:
                self.account_id = account

