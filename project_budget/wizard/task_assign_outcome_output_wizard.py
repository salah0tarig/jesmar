# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class TaskAssignOutcomeOutputWizard(models.TransientModel):
    _name = 'project.task.assign.outcome.output.wizard'
    _description = 'Assign Outcome, Output and Activity Analytic to Tasks'

    task_ids = fields.Many2many(
        'project.task',
        string='Tasks',
        help='Tasks to update (from selection)',
    )
    project_id = fields.Many2one(
        'project.project',
        string='Project',
        compute='_compute_project_id',
        store=True,
        readonly=True,
        help='Project of selected tasks (must be same for all)',
    )
    parent_account_id = fields.Many2one(
        'account.analytic.account',
        related='project_id.account_id',
        string='Project Account',
    )
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
        help='Output analytic account (parent must be outcome)',
    )
    activity_analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Activity Analytic Account',
        domain="[('parent_id', '=', output_id or False)]",
        help='Activity analytic account (parent must be output)',
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if self.env.context.get('active_model') == 'project.task' and self.env.context.get('active_ids'):
            res['task_ids'] = [(6, 0, self.env.context['active_ids'])]
        return res

    @api.depends('task_ids', 'task_ids.project_id')
    def _compute_project_id(self):
        for wiz in self:
            if wiz.task_ids:
                projects = wiz.task_ids.mapped('project_id')
                if len(projects) > 1:
                    wiz.project_id = False  # Mixed projects
                else:
                    wiz.project_id = projects[:1]
            else:
                wiz.project_id = False

    def action_apply(self):
        self.ensure_one()
        if not self.task_ids:
            raise UserError(_('No tasks selected.'))
        projects = self.task_ids.mapped('project_id')
        if len(projects) > 1:
            raise UserError(_('Selected tasks must be from the same project.'))
        if not self.project_id or not self.project_id.account_id:
            raise UserError(_('Tasks must belong to a project with an analytic account.'))
        vals = {}
        if self.outcome_id:
            vals['outcome_id'] = self.outcome_id.id
        if self.output_id:
            vals['output_id'] = self.output_id.id
        if self.activity_analytic_account_id:
            vals['activity_analytic_account_id'] = self.activity_analytic_account_id.id
        if not vals:
            raise UserError(_('Select at least one value to assign (Outcome, Output or Activity Analytic).'))
        self.task_ids.write(vals)
        return {'type': 'ir.actions.act_window_close'}
