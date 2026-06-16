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

Use Case:
---------
Useful for small and medium companies that need a lightweight salary system
without full payroll complexity.

Future Improvements:
--------------------

- Integration with HR and Accounting modules
    """,

    'author': "My Company",
    'website': "https://www.yourcompany.com",

    'category': 'Human Resources',
    'version': '19.0.0',

    # dependencies
    'depends': ['base', 'hr'],

    # data files
    'data': [
        'views/employee_views_inherit.xml',
    ],

    # demo data
    'demo': [
    ],

    'installable': True,
    'application': True,
    'auto_install': False,
}
