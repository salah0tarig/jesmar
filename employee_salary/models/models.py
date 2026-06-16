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
