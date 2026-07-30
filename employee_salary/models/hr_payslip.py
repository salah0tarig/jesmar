# -*- coding: utf-8 -*-

from odoo import api, models


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    @api.depends("line_ids.total", "struct_id.rule_ids.appears_on_employee_cost_dashboard")
    def _compute_basic_net(self):
        super()._compute_basic_net()
        employer_rules = ("EMP_SI", "EMP_MI")
        slips_with_rules = self.filtered(
            lambda p: p.struct_id.rule_ids.filtered(lambda r: r.code in employer_rules)
        )
        if not slips_with_rules:
            return
        line_values = slips_with_rules._get_line_values(employer_rules)
        for payslip in slips_with_rules:
            slip_id = payslip._origin.id
            si = line_values.get("EMP_SI", {}).get(slip_id, {}).get("total", 0.0)
            mi = line_values.get("EMP_MI", {}).get(slip_id, {}).get("total", 0.0)
            payslip.employer_cost = payslip.gross_wage + si + mi
