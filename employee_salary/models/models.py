from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

# Employer contribution rates (SI + MI)
EMPLOYER_SI_RATE = 0.17
EMPLOYER_MI_RATE = 0.06
EMPLOYER_CONTRIBUTION_RATE = EMPLOYER_SI_RATE + EMPLOYER_MI_RATE  # 0.23


class HrVersion(models.Model):
    _inherit = 'hr.version'

    total_staff_cost = fields.Monetary(
        string='Total Staff Cost',
        currency_field='currency_id',
        tracking=True,
        help='Gross Salary + Social Insurance + Medical Insurance.',
    )
    social_insurance = fields.Monetary(
        string='Social Insurance',
        currency_field='currency_id',
        compute='_compute_insurance_amounts',
        store=True,
        tracking=True,
        help='Gross Salary × 17%.',
    )
    medical_insurance = fields.Monetary(
        string='Medical Insurance',
        currency_field='currency_id',
        compute='_compute_insurance_amounts',
        store=True,
        tracking=True,
        help='Gross Salary × 6%.',
    )

    def _get_salary_wage(self):
        """Gross Salary = Total Staff Cost / (1 + SI% + MI%)."""
        self.ensure_one()
        if not self.total_staff_cost:
            return 0.0
        return self.total_staff_cost / (1.0 + EMPLOYER_CONTRIBUTION_RATE)

    @api.depends('total_staff_cost')
    def _compute_insurance_amounts(self):
        for rec in self:
            wage = rec._get_salary_wage()
            rec.social_insurance = wage * EMPLOYER_SI_RATE
            rec.medical_insurance = wage * EMPLOYER_MI_RATE

    @api.constrains('total_staff_cost')
    def _check_amounts(self):
        for rec in self.filtered('employee_id'):
            if rec.total_staff_cost and rec.total_staff_cost <= 0:
                raise ValidationError(_('Total Staff Cost must be greater than zero.'))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.filtered('employee_id')._sync_wage_from_salary_components()
        return records

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get('skip_salary_wage_sync') and 'total_staff_cost' in vals:
            self.filtered('employee_id')._sync_wage_from_salary_components()
        return res

    def _sync_wage_from_salary_components(self):
        for rec in self:
            wage = rec._get_salary_wage()
            if rec.wage != wage:
                rec.with_context(skip_salary_wage_sync=True).write({'wage': wage})


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    total_staff_cost = fields.Monetary(
        related='version_id.total_staff_cost',
        readonly=False,
        inherited=True,
        groups='hr.group_hr_manager',
    )
    social_insurance = fields.Monetary(
        related='version_id.social_insurance',
        inherited=True,
        groups='hr.group_hr_manager',
    )
    medical_insurance = fields.Monetary(
        related='version_id.medical_insurance',
        inherited=True,
        groups='hr.group_hr_manager',
    )
    wage = fields.Monetary(
        related='version_id.wage',
        inherited=True,
        groups='hr.group_hr_manager',
    )
