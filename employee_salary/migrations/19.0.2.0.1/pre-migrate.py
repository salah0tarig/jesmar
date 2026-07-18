import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Keep legacy subsistence payroll records when upgrading to the slim module.

    Odoo deletes module XML records that are no longer in data files (_process_end).
    hr.payslip.input.type rows from the old subsistence feature must not be deleted
    while draft/done payslips still reference them through hr.payslip.input.
    """
    cr.execute(
        """
        UPDATE ir_model_data
           SET noupdate = true
         WHERE module = 'employee_salary'
           AND model IN ('hr.payslip.input.type', 'hr.salary.rule')
        """
    )
    _logger.info(
        "employee_salary: marked %s legacy payroll xmlids as noupdate to avoid FK errors on upgrade",
        cr.rowcount,
    )
