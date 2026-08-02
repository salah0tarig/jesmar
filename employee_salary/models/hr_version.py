# -*- coding: utf-8 -*-

from odoo import fields, models


class HrVersion(models.Model):
    _inherit = "hr.version"

    salary_allocation_ids = fields.One2many(
        "hr.employee.salary.allocation",
        "version_id",
        string="Salary budget allocations",
        copy=True,
        help="Default split of payroll expense across project budget lines.",
    )
