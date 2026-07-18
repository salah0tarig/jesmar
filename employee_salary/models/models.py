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

    def _get_salary_wage(self):
        self.ensure_one()
        return (self.approval_amount or 0.0) + (self.social_insurance or 0.0)

    @api.constrains('approval_amount', 'social_insurance')
    def _check_amounts(self):
        for rec in self.filtered('employee_id'):
            if not (rec.approval_amount or rec.social_insurance):
                continue
            if not rec.approval_amount or rec.approval_amount <= 0:
                raise ValidationError(_('Approval amount must be greater than zero.'))
            if not rec.social_insurance or rec.social_insurance <= 0:
                raise ValidationError(_('Social insurance must be greater than zero.'))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.filtered('employee_id')._sync_wage_from_salary_components()
        return records

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get('skip_salary_wage_sync') and (
            {'approval_amount', 'social_insurance'} & set(vals)
        ):
            self.filtered('employee_id')._sync_wage_from_salary_components()
        return res

    def _sync_wage_from_salary_components(self):
        for rec in self:
            wage = rec._get_salary_wage()
            if rec.wage != wage:
                rec.with_context(skip_salary_wage_sync=True).write({'wage': wage})


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
