# -*- coding: utf-8 -*-
{
    'name': 'Voucher Custom',
    'version': '19.0.1.2.3',
    'category': 'Accounting/Accounting',
    'summary': 'Custom Payment Voucher printout for vendor payments',
    'description': """
Payment Voucher printout
========================

Adds a Jesmar-style payment voucher PDF on account.payment with project/donor
resolution from reconciled vendor bills and purchase orders, amount in words,
and journal entry lines with manual signature blocks on the printout.
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
        'reports/payment_voucher_report.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
