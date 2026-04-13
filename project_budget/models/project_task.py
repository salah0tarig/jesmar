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
    
    activity_analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Activity Analytic Account',
        domain="[('parent_id', '=', output_id or False)]",
        help='Analytic account for this activity; options are children of the selected Output',
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
            self.activity_analytic_account_id = False

    @api.onchange('outcome_id')
    def _onchange_outcome_clear_output(self):
        if self.outcome_id:
            self.output_id = False
            self.activity_analytic_account_id = False

    @api.onchange('output_id')
    def _onchange_output_clear_activity_analytic(self):
        """When Output changes, clear Activity Analytic Account (domain/options change)."""
        if self.output_id:
            self.activity_analytic_account_id = False

    @api.onchange('activity_analytic_account_id')
    def _onchange_activity_analytic_sync_output(self):
        """When Activity Analytic Account is set, ensure Output (and Outcome) are its ancestors."""
        if self.activity_analytic_account_id and self.activity_analytic_account_id.parent_id:
            self.output_id = self.activity_analytic_account_id.parent_id
            if self.output_id.parent_id:
                self.outcome_id = self.output_id.parent_id

    def _prepare_activity_analytic_account_vals(self):
        """Build values for the auto-created activity analytic account."""
        self.ensure_one()
        output = self.output_id
        plan = self._get_activity_analytic_plan(output)
        if not plan:
            raise ValidationError(_(
                'No Analytic Plan found to create the Activity Analytic Account. '
                'Please configure an Analytic Plan first.'
            ))
        return {
            'name': self.name or _('Activity'),
            'parent_id': output.id,
            'plan_id': plan.id,
            'company_id': output.company_id.id,
        }

    def _get_activity_analytic_plan(self, output):
        """Resolve a valid analytic plan for auto-created activity accounts."""
        self.ensure_one()
        plan = (
            output.plan_id
            or output.parent_id.plan_id
            or self.parent_account_id.plan_id
            or self.project_id.account_id.plan_id
        )
        if plan:
            return plan
        company = output.company_id or self.company_id or self.env.company
        plan = self.env['account.analytic.plan'].search(
            [('company_id', 'in', [company.id, False])],
            limit=1,
        )
        if not plan:
            plan = self.env['account.analytic.plan'].search([], limit=1)
        return plan

    @api.model_create_multi
    def create(self, vals_list):
        tasks = super().create(vals_list)
        for task, vals in zip(tasks, vals_list):
            # Auto-create activity analytic account only when task is created with an output
            # and no explicit activity analytic account was provided.
            if vals.get('activity_analytic_account_id'):
                continue
            analytic_account = self.env['account.analytic.account'].create(
                task._prepare_activity_analytic_account_vals()
            )
            task.activity_analytic_account_id = analytic_account
        return tasks
