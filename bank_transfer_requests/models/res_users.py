from odoo import fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    btr_finance_branch_ids = fields.Many2many(
        "res.company",
        "btr_user_finance_branch_rel",
        "user_id",
        "company_id",
        string="Bank Transfer Finance Branches",
    )