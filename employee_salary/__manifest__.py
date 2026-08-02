{
    'name': "Employee Salary Management",

    'summary': "Manage employee salaries, allowances, and deductions",

    'description': """
Employee Salary Module
======================

This module helps in managing employee salary details in a simple and flexible way.

Main Features:
--------------
- Manage basic salary
- Employer SI/MI on payslip
- Salary budget allocation on employee record → payslip journal entry (budget achieved)

Use Case:
---------
Useful for small and medium companies that need a lightweight salary system
without full payroll complexity.
    """,

    'author': "My Company",
    'website': "https://www.yourcompany.com",

    'category': 'Human Resources',
    'version': '19.0.3.0.6',

    'depends': [
        'base',
        'hr',
        'hr_payroll',
        'hr_payroll_account',
        'project_budget',
    ],

    'data': [
        'security/ir.model.access.csv',
        'data/hr_salary_rules_data.xml',
        'views/employee_views_inherit.xml',
        'views/hr_salary_allocation_views.xml',
    ],

    'installable': True,
    'application': True,
    'auto_install': False,
}
