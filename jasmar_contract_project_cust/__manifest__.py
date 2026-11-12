# -*- coding: utf-8 -*-
{
    "name": "Jasmar Contract & Project Custom",
    "version": "19.0.1.1",
    "category": "Human Resources",
    "summary": "Contract attachment on employee profile and analytic menus on project",
    "author": "Eng.Huda Abdalla",
    "depends": [
        "hr",
        "project",
        "analytic",
        "account_budget",
        "project_budget",
    ],
    "data": [
        "views/hr_employee_views.xml",
        "views/project_analytic_menus.xml",
    ],

    "installable": True,
    "license": "LGPL-3",
}
