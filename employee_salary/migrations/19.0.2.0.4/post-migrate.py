import logging

_logger = logging.getLogger(__name__)

# Gross = Total Staff Cost / (1 + 0.17 + 0.06)
EMPLOYER_CONTRIBUTION_RATE = 0.23
EMPLOYER_SI_RATE = 0.17
EMPLOYER_MI_RATE = 0.06


def migrate(cr, version):
    """Recompute wage, SI, and MI from Total Staff Cost using the employer formula."""
    cr.execute(
        """
        SELECT column_name
          FROM information_schema.columns
         WHERE table_name = 'hr_version'
           AND column_name IN (
               'total_staff_cost', 'wage', 'social_insurance', 'medical_insurance'
           )
        """
    )
    columns = {row[0] for row in cr.fetchall()}
    if 'total_staff_cost' not in columns or 'wage' not in columns:
        _logger.info("employee_salary: required columns missing, skip wage recompute")
        return

    if 'medical_insurance' not in columns:
        cr.execute(
            "ALTER TABLE hr_version ADD COLUMN IF NOT EXISTS medical_insurance numeric"
        )

    cr.execute(
        """
        UPDATE hr_version
           SET wage = COALESCE(total_staff_cost, 0) / %s,
               social_insurance = (COALESCE(total_staff_cost, 0) / %s) * %s,
               medical_insurance = (COALESCE(total_staff_cost, 0) / %s) * %s
         WHERE total_staff_cost IS NOT NULL
           AND total_staff_cost > 0
        """,
        (
            1.0 + EMPLOYER_CONTRIBUTION_RATE,
            1.0 + EMPLOYER_CONTRIBUTION_RATE,
            EMPLOYER_SI_RATE,
            1.0 + EMPLOYER_CONTRIBUTION_RATE,
            EMPLOYER_MI_RATE,
        ),
    )
    _logger.info(
        "employee_salary: recomputed wage/SI/MI for %s hr.version rows",
        cr.rowcount,
    )
