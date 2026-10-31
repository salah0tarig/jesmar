# -*- coding: utf-8 -*-

from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    contract_document = fields.Binary(
        string="Contract Document",
        attachment=True,
    )
    contract_filename = fields.Char(string="Contract Filename")
