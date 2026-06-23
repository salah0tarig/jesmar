from odoo import api, models


class HrPayrollStructure(models.Model):
    _inherit = 'hr.payroll.structure'

    @api.model
    def _employee_salary_register_subsistence_rules(self):
        from odoo.addons.employee_salary.hooks import _register_subsistence_salary_rules
        _register_subsistence_salary_rules(self.env)
