from odoo import fields, models


class HrJob(models.Model):
    _inherit = 'hr.job'

    subsistence_allowance_type = fields.Selection(
        selection=[
            ('none', 'None'),
            ('fixed', 'Fixed Subsistence (Amount)'),
        ],
        string='Subsistence Allowance Type',
        default='none',
        help='Fixed subsistence for maintenance and administrative staff. Daily subsistence is set on the employee profile.',
    )
    fixed_subsistence_amount = fields.Monetary(
        string='Fixed Subsistence Amount',
        currency_field='currency_id',
        help='Monthly fixed subsistence amount for maintenance and administrative staff.',
    )
    currency_id = fields.Many2one(
        related='company_id.currency_id',
        depends=['company_id'],
    )
