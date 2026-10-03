# -*- coding: utf-8 -*-
{
    "name": "Payroll: register NET salary payment only",
    "version": "19.0.1.4.0",
    "category": "Human Resources/Payroll",
    "summary": "Payslip Pay button opens payment wizard on NET payable lines only",
    "depends": ["hr_payroll_account"],
    "data": [
        "security/ir.model.access.csv",
        "security/security.xml",
        "views/hr_payslip_views.xml",
        "views/account_payment_register_views.xml",
    ],
    "installable": True,
    "license": "LGPL-3",
}
