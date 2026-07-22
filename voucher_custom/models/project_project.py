# -*- coding: utf-8 -*-

from odoo import fields, models


class ProjectProject(models.Model):
    _inherit = 'project.project'

    donor_id = fields.Many2one(
        'res.partner',
        string='Donor',
        help='Donor partner shown on payment vouchers linked to this project.',
    )
