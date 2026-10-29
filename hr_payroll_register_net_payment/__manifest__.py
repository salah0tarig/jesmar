# -*- coding: utf-8 -*-
{
    "name": "Payroll: register NET salary payment only",
    "version": "19.0.1.5.1",
    "category": "Human Resources/Payroll",
    "summary": "Payslip Pay uses standard payment wizard on payable NET lines only",
    "depends": ["hr_payroll_account"],
    "data": [
        "security/ir.model.access.csv",
        "security/security.xml",
        "views/hr_payslip_views.xml",
    ],
    "installable": True,
    "license": "LGPL-3",
}
