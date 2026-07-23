# -*- coding: utf-8 -*-

import logging

from lxml import etree

_logger = logging.getLogger(__name__)


def _strip_signature_fields(arch):
    if not arch or 'voucher_signature_ids' not in arch:
        return arch
    wrapper = f'<data>{arch}</data>'
    root = etree.fromstring(wrapper.encode('utf-8'))
    for node in root.xpath(".//field[@name='voucher_signature_ids']"):
        parent = node.getparent()
        if parent is not None:
            parent.remove(node)
    for group in root.xpath(".//group[@string='Signatures']"):
        parent = group.getparent()
        if parent is not None:
            parent.remove(group)
    return ''.join(
        etree.tostring(child, encoding='unicode') for child in root
    )


def migrate(cr, version):
    """Drop stale signature field metadata and clean payment form views."""
    cr.execute(
        """
        DELETE FROM ir_model_fields
         WHERE model = 'account.payment'
           AND name = 'voucher_signature_ids'
        """
    )
    cr.execute(
        """
        DELETE FROM ir_model_data
         WHERE module = 'voucher_custom'
           AND (name LIKE '%payment_signature%' OR name LIKE '%voucher_signature%')
        """
    )
    cr.execute(
        """
        SELECT 1
          FROM information_schema.tables
         WHERE table_name = 'account_payment_signature'
        """
    )
    if cr.fetchone():
        _logger.info('voucher_custom: dropping account_payment_signature table')
        cr.execute('DROP TABLE account_payment_signature CASCADE')

    cr.execute(
        """
        DELETE FROM ir_model_fields
         WHERE model = 'account.payment.signature'
        """
    )
    cr.execute(
        """
        DELETE FROM ir_model
         WHERE model = 'account.payment.signature'
        """
    )

    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    views = env['ir.ui.view'].with_context(active_test=False).search([
        ('arch_db', 'ilike', 'voucher_signature_ids'),
    ])
    for view in views:
        arch = view.arch_db or ''
        cleaned = _strip_signature_fields(arch)
        if cleaned != arch:
            _logger.info(
                'voucher_custom: removing voucher_signature_ids from view %s (id=%s)',
                view.name,
                view.id,
            )
            view.with_context(no_save_prev=True).write({'arch_db': cleaned})

    cr.execute(
        """
        DELETE FROM ir_ui_view
         WHERE id IN (
            SELECT v.id
              FROM ir_ui_view v
              JOIN ir_model_data d ON d.res_id = v.id AND d.model = 'ir.ui.view'
             WHERE d.module = 'voucher_custom'
               AND d.name LIKE '%payment_signature%'
         )
        """
    )
