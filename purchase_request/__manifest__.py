{
    'name': "Purchase Requisition",

    'description': """
    Pre request for purchase order
    """,
    'category': 'Purchase',
    'author': "Huda Abdalla",
    
    'category': 'Uncategorized',
    'version': '19.0.1.0.1',

    'depends': [
        'purchase',
        'stock',
        'account',
        'analytic',
        'hr',
        'mail',   
        'project_budget',
        'project',
    ],

    
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'views/purchase_requisition_views.xml',
        'views/purchase_order_views.xml',
        'views/menus.xml',
        'views/reject_wizard_views.xml',
        
        
    ],
    'application': True,
}

