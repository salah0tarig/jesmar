from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class HrVersion(models.Model):
    _inherit = 'hr.version'

    social_insurance = fields.Monetary(
        string='Social Insurance',
        currency_field='currency_id',
        tracking=True,
    )
    approval_amount = fields.Monetary(
        string='Approval Amount',
        currency_field='currency_id',
        tracking=True,
    )

    wage = fields.Monetary(
        string='Wage',
        compute='_compute_wage',
        store=True,
        readonly=True,
        tracking=True,
        help="Employee's monthly gross wage.",
        aggregator='avg',
        groups='hr.group_hr_manager',
    )

    @api.depends('approval_amount', 'social_insurance')
    def _compute_wage(self):
        for rec in self:
            rec.wage = (rec.approval_amount or 0.0) + (rec.social_insurance or 0.0)

    @api.constrains('approval_amount', 'social_insurance')
    def _check_amounts(self):
        for rec in self.filtered('employee_id'):
            if not rec.approval_amount or rec.approval_amount <= 0:
                raise ValidationError(_('Approval amount must be greater than zero.'))
            if not rec.social_insurance or rec.social_insurance <= 0:
                raise ValidationError(_('Social insurance must be greater than zero.'))


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    social_insurance = fields.Monetary(
        related='version_id.social_insurance',
        readonly=False,
        inherited=True,
        groups='hr.group_hr_manager',
    )
    approval_amount = fields.Monetary(
        related='version_id.approval_amount',
        readonly=False,
        inherited=True,
        groups='hr.group_hr_manager',
    )
    wage = fields.Monetary(
        related='version_id.wage',
        inherited=True,
        groups='hr.group_hr_manager',
    )
    subsistence_allowance_type = fields.Selection(
        selection=[
            ('none', 'None'),
            ('fixed', 'Fixed Subsistence (Amount)'),
            ('daily', 'Daily Subsistence'),
        ],
        string='Subsistence Allowance Type',
        compute='_compute_subsistence_allowance',
        store=True,
        readonly=True,
    )
    fixed_subsistence_amount = fields.Monetary(
        string='Fixed Subsistence Amount',
        currency_field='currency_id',
        compute='_compute_subsistence_allowance',
        store=True,
        readonly=True,
    )
    daily_subsistence_rate = fields.Monetary(
        string='Daily Subsistence Rate',
        currency_field='currency_id',
        help='Daily subsistence allowance rate used on payslips (field work days x rate).',
    )
    subsistence_allowance_source = fields.Char(
        string='Subsistence Rule Source',
        compute='_compute_subsistence_allowance',
        store=True,
        readonly=True,
    )

    @api.depends(
        'job_id.subsistence_allowance_type',
        'job_id.fixed_subsistence_amount',
        'department_id.subsistence_allowance_type',
        'department_id.fixed_subsistence_amount',
        'daily_subsistence_rate',
    )
    def _compute_subsistence_allowance(self):
        for employee in self:
            source = employee._get_subsistence_allowance_source()
            if source.subsistence_allowance_type == 'fixed':
                employee.subsistence_allowance_type = 'fixed'
                employee.fixed_subsistence_amount = source.fixed_subsistence_amount or 0.0
                if source._name == 'hr.job':
                    employee.subsistence_allowance_source = _('Job: %s', source.display_name)
                else:
                    employee.subsistence_allowance_source = _('Department: %s', source.display_name)
            elif employee.daily_subsistence_rate:
                employee.subsistence_allowance_type = 'daily'
                employee.fixed_subsistence_amount = 0.0
                employee.subsistence_allowance_source = _('Employee profile')
            else:
                employee.subsistence_allowance_type = 'none'
                employee.fixed_subsistence_amount = 0.0
                employee.subsistence_allowance_source = False

    def _get_subsistence_allowance_source(self):
        self.ensure_one()
        if self.job_id and self.job_id.subsistence_allowance_type == 'fixed':
            return self.job_id
        if self.department_id and self.department_id.subsistence_allowance_type == 'fixed':
            return self.department_id
        return self.env['hr.job']

    @api.model
    def _employee_salary_run_migrations(self):
        from odoo.addons.employee_salary.hooks import _migrate_job_daily_subsistence_to_employee_profile
        _migrate_job_daily_subsistence_to_employee_profile(self.env)
