from odoo import Command, api, fields, models, _


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    project_id = fields.Many2one(
        'project.project',
        string='Project',
        domain="[('allow_timesheets', '=', True), '|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        help='Optional. Count field work days only on this project. Leave empty to count all project task timesheet lines.',
    )
    subsistence_allowance_type = fields.Selection(
        related='employee_id.subsistence_allowance_type',
        readonly=True,
    )
    fixed_subsistence_amount = fields.Monetary(
        related='employee_id.fixed_subsistence_amount',
        readonly=True,
    )
    daily_subsistence_rate = fields.Monetary(
        related='employee_id.daily_subsistence_rate',
        string='Daily Rate',
        readonly=True,
        help='Daily subsistence rate from the employee profile.',
    )
    field_work_days = fields.Integer(
        string='Field Work Days',
        compute='_compute_subsistence_from_timesheets',
        store=True,
        readonly=True,
        help='One day per project task timesheet line in the payslip period.',
    )
    daily_subsistence_amount = fields.Monetary(
        string='Daily Subsistence Amount',
        compute='_compute_subsistence_from_timesheets',
        store=True,
        readonly=True,
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(related='company_id.currency_id')

    @api.depends(
        'employee_id',
        'employee_id.daily_subsistence_rate',
        'employee_id.subsistence_allowance_type',
        'date_from',
        'date_to',
        'project_id',
    )
    def _compute_subsistence_from_timesheets(self):
        for slip in self:
            slip.field_work_days = slip._get_field_work_days_count()
            employee = slip.employee_id
            daily_rate = employee.daily_subsistence_rate if employee else 0.0
            if (
                employee
                and employee.subsistence_allowance_type == 'daily'
                and daily_rate
                and slip.field_work_days
            ):
                slip.daily_subsistence_amount = daily_rate * slip.field_work_days
            else:
                slip.daily_subsistence_amount = 0.0

    def _get_field_work_days_count(self):
        """Count project task timesheet lines (= field work days for daily subsistence)."""
        self.ensure_one()
        if not self.employee_id or not self.date_from or not self.date_to:
            return 0

        domain = [
            ('employee_id', '=', self.employee_id.id),
            ('project_id', '!=', False),
            ('task_id', '!=', False),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
        ]
        if self.project_id:
            domain.append(('project_id', '=', self.project_id.id))

        return self.env['account.analytic.line'].sudo().search_count(domain)

    @api.depends(
        'employee_id',
        'employee_id.subsistence_allowance_type',
        'employee_id.daily_subsistence_rate',
        'employee_id.fixed_subsistence_amount',
        'version_id',
        'struct_id',
        'date_from',
        'date_to',
        'project_id',
        'field_work_days',
        'daily_subsistence_amount',
    )
    def _compute_input_line_ids(self):
        super()._compute_input_line_ids()
        fixed_input_type = self.env.ref(
            'employee_salary.input_type_fixed_subsistence',
            raise_if_not_found=False,
        )
        daily_input_type = self.env.ref(
            'employee_salary.input_type_daily_subsistence',
            raise_if_not_found=False,
        )
        managed_input_types = (fixed_input_type | daily_input_type).exists()
        if not managed_input_types:
            return

        for slip in self:
            if not slip.employee_id or not slip.struct_id:
                continue

            commands = [
                Command.unlink(line.id)
                for line in slip.input_line_ids.filtered(
                    lambda line: line.input_type_id in managed_input_types
                )
            ]
            employee = slip.employee_id

            if (
                fixed_input_type
                and employee.subsistence_allowance_type == 'fixed'
                and employee.fixed_subsistence_amount
                and slip._is_subsistence_input_allowed(fixed_input_type)
            ):
                commands.append(Command.create({
                    'input_type_id': fixed_input_type.id,
                    'name': _('Fixed Subsistence'),
                    'amount': employee.fixed_subsistence_amount,
                }))

            if (
                daily_input_type
                and employee.subsistence_allowance_type == 'daily'
                and slip.daily_subsistence_amount
                and slip._is_subsistence_input_allowed(daily_input_type)
            ):
                commands.append(Command.create({
                    'input_type_id': daily_input_type.id,
                    'name': _(
                        'Daily Subsistence (%(days)s days x %(rate)s)',
                        days=slip.field_work_days,
                        rate=slip.daily_subsistence_rate,
                    ),
                    'amount': slip.daily_subsistence_amount,
                }))

            if commands:
                slip.update({'input_line_ids': commands})

    def _is_subsistence_input_allowed(self, input_type):
        self.ensure_one()
        return not input_type.struct_ids or self.struct_id in input_type.struct_ids

    def compute_sheet(self):
        """Recompute subsistence days/amount and salary inputs before payroll lines."""
        self.invalidate_recordset([
            'field_work_days',
            'daily_subsistence_amount',
            'input_line_ids',
        ])
        return super().compute_sheet()
