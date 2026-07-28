import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Rename approval_amount column to total_staff_cost on hr_version."""
    cr.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_name = 'hr_version'
           AND column_name = 'approval_amount'
        """
    )
    if not cr.fetchone():
        _logger.info("employee_salary: approval_amount column not found, skip rename")
        return

    cr.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_name = 'hr_version'
           AND column_name = 'total_staff_cost'
        """
    )
    if cr.fetchone():
        _logger.info("employee_salary: total_staff_cost already exists, drop legacy approval_amount")
        cr.execute("ALTER TABLE hr_version DROP COLUMN IF EXISTS approval_amount")
        return

    cr.execute("ALTER TABLE hr_version RENAME COLUMN approval_amount TO total_staff_cost")
    _logger.info("employee_salary: renamed hr_version.approval_amount -> total_staff_cost")
