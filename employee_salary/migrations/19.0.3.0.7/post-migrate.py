# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Ensure STAFF_COST never distorts the standard payroll journal entry."""
    cr.execute(
        """
        SELECT id FROM ir_model_data
         WHERE module = 'employee_salary'
           AND name = 'salary_rule_total_employer_cost'
           AND model = 'hr.salary.rule'
        """
    )
    row = cr.fetchone()
    if not row:
        return
    rule_id = row[0]
    cr.execute(
        """
        UPDATE hr_salary_rule
           SET not_computed_in_net = FALSE,
               account_debit = NULL,
               account_credit = NULL
         WHERE id = %s
        """,
        (rule_id,),
    )
    _logger.info(
        "employee_salary: cleared STAFF_COST accounts and not_computed_in_net on rule %s",
        rule_id,
    )
