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
- Configure subsistence allowance rules on job positions and departments
- Auto-fill fixed subsistence allowance on payslips from employee job/department
- Auto-calculate daily subsistence from project timesheets in the payslip period

Use Case:
---------
Useful for small and medium companies that need a lightweight salary system
without full payroll complexity.
    """,

    'author': "My Company",
    'website': "https://www.yourcompany.com",

    'category': 'Human Resources',
    'version': '19.0.1.2.3',

    'depends': ['base', 'hr', 'hr_hourly_cost', 'hr_payroll', 'hr_timesheet'],

    'data': [
        'views/employee_views_inherit.xml',
        'views/hr_job_department_views.xml',
        'views/hr_payslip_views.xml',
        'data/payroll_subsistence_data.xml',
    ],

    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',

    'installable': True,
    'application': True,
    'auto_install': False,
}
