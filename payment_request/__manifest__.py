{
    'name': "Payment Request",
    'summary': "Payment request workflow with portal submission, comments, status tracking, and vendor bill creation",
    'description':
    """
    Payment Request

Structured workflow for collecting, reviewing, and processing payment requests in Odoo 18.
Includes portal submission, supporting documents, status tracking, and direct vendor bill creation.
    """,
    'author': "Oksana Yeroshenko",
    'website': "https://odoo-pro.com.ua/",
    'category': 'Accounting',
    'version': '18.0.0.1.0',
    'depends': ['account', 'portal', 'hr'],
    'data': [
        'data/ir_sequence.xml',
        'security/groups.xml',
        'security/ir.model.access.csv',
        'security/ir_rule.xml',
        'views/payment_request_views.xml',
        'wizard/payment_request_create_bill_wizard_views.xml',
        'views/res_users_views.xml',
        'views/portal_templates.xml',
        'views/account_vendor_bills_to_check_menu.xml',
        'views/account_move_views.xml',
    ],
    'images': ['static/description/banner.png'],
    'application': True,
    'installable': True,
    'license': 'LGPL-3',
}
