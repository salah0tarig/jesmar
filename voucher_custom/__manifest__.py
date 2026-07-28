# -*- coding: utf-8 -*-
{
    'name': 'Voucher Custom',
    'version': '19.0.1.2.6',
    'category': 'Accounting/Accounting',
    'summary': 'Custom Payment Voucher printout for vendor payments',
    'description': """
Payment Voucher printout
========================

Adds Jesmar-style payment, receipt, and journal voucher PDFs with journal
entry lines, analytic department columns, and manual signature blocks.
    """,
    'author': 'Anas Osman',
    'depends': [
        'account',
        'purchase',
        'project',
        'project_purchase',
        'project_budget',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/project_project_views.xml',
        'views/account_payment_views.xml',
        'views/account_move_views.xml',
        'reports/voucher_paperformat.xml',
        'reports/payment_voucher_report.xml',
        'reports/journal_voucher_report.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
