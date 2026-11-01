# -*- coding: utf-8 -*-

from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    age = fields.Integer(
        string="Age",
        compute="_compute_age",
        groups="hr.group_hr_user",
        help="Age in full years based on Birthday (today).",
    )

    @api.depends("birthday")
    def _compute_age(self):
        for employee in self:
            employee.age = employee._get_age() if employee.birthday else 0
