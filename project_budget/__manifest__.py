# -*- coding: utf-8 -*-
{
    'name': 'Project Budget (Outcome & Output)',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Project-centric budget with Outcome/Output hierarchy and Activity-driven budget lines',
    'description': """
Project Budget with Outcome & Output
====================================

Implements a hierarchical budget structure aligned with project management:

**Hierarchy (Analytic Accounts):**
- **Project** (top): Project's analytic account
- **Outcome** (child): Analytic account with parent = Project AA
- **Output** (child): Analytic account with parent = Outcome

**Task/Activity Enhancement:**
- Add Outcome and Output fields on Tasks
- Output links to the analytic account used for expense allocation
- Domain filters enforce: Output parent = Outcome, Outcome parent = Project

**Budget Lines:**
- Activity (Task) field on budget line
- When Activity selected → Analytic Account auto-fills from Task's Output
- Budgetary Position and Planned Amount
- Real expenses (vendor bills, timesheets) use Output analytic account → totals roll up automatically

**Reporting:**
- Project total, Outcome total, Output total, Activity detail
- Uses Odoo analytic hierarchy for automatic roll-up
    """,
    'author': 'Anas Osman',
    'website': 'https://www.yourcompany.com',
    'depends': [
        'base',
        'account',
        'analytic',
        'project',
        'account_budget',
        'project_account_budget',
    ],
    'data': [
        # 'security/ir.model.access.csv',
        'views/account_analytic_account_views.xml',
        'views/project_task_views.xml',
        'views/budget_analytic_views.xml',
        'views/budget_line_views.xml',
        'views/project_project_views.xml',
    ],
    'demo': [
        'data/project_budget_demo.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
