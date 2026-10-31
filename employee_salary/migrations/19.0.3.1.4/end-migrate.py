# -*- coding: utf-8 -*-
"""Set PIT salary rules to skip computation in the last contract month."""


def migrate(cr, version):
    from odoo import api, SUPERUSER_ID
    from odoo.addons.employee_salary.models.hr_payslip import PIT_LAST_MONTH_CONDITION

    env = api.Environment(cr, SUPERUSER_ID, {})
    pit_rules = env["hr.salary.rule"].search([("code", "=", "PIT")])
    if not pit_rules:
        return
    pit_rules.write({
        "condition_select": "python",
        "condition_python": PIT_LAST_MONTH_CONDITION,
    })
