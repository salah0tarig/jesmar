from odoo import fields, models


class HrDepartment(models.Model):
    _inherit = 'hr.department'

    subsistence_allowance_type = fields.Selection(
        selection=[
            ('none', 'None'),
            ('fixed', 'Fixed Subsistence (Amount)'),
        ],
        string='Subsistence Allowance Type',
        default='none',
        help='Default fixed subsistence for this department. Daily subsistence is set on the employee profile.',
    )
    fixed_subsistence_amount = fields.Monetary(
        string='Fixed Subsistence Amount',
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        related='company_id.currency_id',
        depends=['company_id'],
    )
