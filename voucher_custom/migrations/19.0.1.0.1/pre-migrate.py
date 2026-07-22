# -*- coding: utf-8 -*-

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Drop legacy Char donor column when upgrading to donor_id Many2one."""
    cr.execute(
        """
        SELECT column_name
          FROM information_schema.columns
         WHERE table_name = 'project_project'
           AND column_name = 'donor'
        """
    )
    if cr.fetchone():
        _logger.info("voucher_custom: dropping legacy project_project.donor column")
        cr.execute("ALTER TABLE project_project DROP COLUMN donor")
