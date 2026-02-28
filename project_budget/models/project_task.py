# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ProjectTask(models.Model):
    _inherit = 'project.task'

    outcome_id = fields.Many2one(
        'account.analytic.account',
        string='Outcome',
        domain="[('parent_id', '=', parent_account_id or False)]",
        help='Outcome analytic account (parent must be project)',
    )
    output_id = fields.Many2one(
        'account.analytic.account',
        string='Output',
        domain="[('parent_id', '=', outcome_id or False)]",
        help='Output analytic account used for expense allocation (parent must be outcome)',
    )
    parent_account_id = fields.Many2one(
        'account.analytic.account',
        string='Parent Account',
        compute='_compute_parent_account_id',
        store=True,
        readonly=False,
    )

    @api.depends('project_id', 'project_id.account_id')
    def _compute_parent_account_id(self):
        for task in self:
            task.parent_account_id = task.project_id.account_id if task.project_id and task.project_id.account_id else False

    @api.constrains('outcome_id', 'project_id')
    def _check_outcome_parent(self):
        for task in self:
            if task.outcome_id and task.project_id and task.project_id.account_id:
                if task.outcome_id.parent_id != task.project_id.account_id:
                    raise ValidationError(_(
                        'Outcome must have Project analytic account as parent.'
                    ))

    @api.constrains('output_id', 'outcome_id')
    def _check_output_parent(self):
        for task in self:
            if task.output_id and task.outcome_id:
                if task.output_id.parent_id != task.outcome_id:
                    raise ValidationError(_(
                        'Output must have selected Outcome as parent.'
                    ))

    @api.onchange('project_id')
    def _onchange_project_clear_outcome_output(self):
        if self.project_id:
            self.outcome_id = False
            self.output_id = False

    @api.onchange('outcome_id')
    def _onchange_outcome_clear_output(self):
        if self.outcome_id:
            self.output_id = False
