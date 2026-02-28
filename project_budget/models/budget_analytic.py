# -*- coding: utf-8 -*-

from odoo import api, fields, models


class BudgetAnalytic(models.Model):
    _inherit = 'budget.analytic'

    project_id = fields.Many2one(
        'project.project',
        string='Project',
        ondelete='set null',
        help='Optional: scope budget to a project (Outcome/Output hierarchy)',
    )
