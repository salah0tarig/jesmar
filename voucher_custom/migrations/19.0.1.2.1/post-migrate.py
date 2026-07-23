# -*- coding: utf-8 -*-

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Remove obsolete payment voucher signature model after manual sign-off change."""
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
        DELETE FROM ir_model_data
         WHERE module = 'voucher_custom'
           AND model = 'account.payment.signature'
        """
    )
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
