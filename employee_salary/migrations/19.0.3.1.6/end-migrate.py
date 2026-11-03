# -*- coding: utf-8 -*-
"""Skip Social Insurance rules when employee age > 60 (Regular Pay)."""


def migrate(cr, version):
    from odoo import api, SUPERUSER_ID
    from odoo.addons.employee_salary.models.hr_payslip import SI_SKIP_OVER_60_CONDITION

    env = api.Environment(cr, SUPERUSER_ID, {})
    # EMP_SI (employer 17%) + SOCIAL_INSURANCE (employee 8%)
    rules = env["hr.salary.rule"].search([
        ("code", "in", ["EMP_SI", "SOCIAL_INSURANCE"]),
    ])
    if not rules:
        return
    rules.write({
        "condition_select": "python",
        "condition_python": SI_SKIP_OVER_60_CONDITION,
    })
