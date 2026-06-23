from odoo import _


def _register_subsistence_salary_rule(env, xmlid, code, name, input_type):
    rule_model = env['hr.salary.rule']
    allowance_category = env.ref('hr_payroll.ALW', raise_if_not_found=False)
    if not input_type or not allowance_category:
        return

    for struct in env['hr.payroll.structure'].search([]):
        if rule_model.search_count([
            ('struct_id', '=', struct.id),
            ('code', '=', code),
        ]):
            continue
        rule_model.create({
            'name': name,
            'code': code,
            'struct_id': struct.id,
            'category_id': allowance_category.id,
            'sequence': 15,
            'condition_select': 'input',
            'condition_other_input_id': input_type.id,
            'amount_select': 'input',
            'amount_other_input_id': input_type.id,
            'appears_on_payslip': True,
        })


def _register_subsistence_salary_rules(env):
    fixed_input_type = env.ref('employee_salary.input_type_fixed_subsistence', raise_if_not_found=False)
    daily_input_type = env.ref('employee_salary.input_type_daily_subsistence', raise_if_not_found=False)
    _register_subsistence_salary_rule(
        env,
        'employee_salary.input_type_fixed_subsistence',
        'FIXED_SUBS',
        _('Fixed Subsistence'),
        fixed_input_type,
    )
    _register_subsistence_salary_rule(
        env,
        'employee_salary.input_type_daily_subsistence',
        'DAILY_SUBS',
        _('Daily Subsistence'),
        daily_input_type,
    )


def _migrate_job_daily_subsistence_to_employee_profile(env):
    """Daily subsistence is employee-profile only; clear legacy job/department daily rules."""
    for model_name in ('hr.job', 'hr.department'):
        records = env[model_name].sudo().search([('subsistence_allowance_type', '=', 'daily')])
        if records:
            records.write({'subsistence_allowance_type': 'none'})
    if 'daily_subsistence_rate' in env['hr.job']._fields:
        env['hr.job'].sudo().search([('daily_subsistence_rate', '!=', 0)]).write({
            'daily_subsistence_rate': 0,
        })
    if 'daily_subsistence_rate' in env['hr.department']._fields:
        env['hr.department'].sudo().search([('daily_subsistence_rate', '!=', 0)]).write({
            'daily_subsistence_rate': 0,
        })


def post_init_hook(env):
    _migrate_job_daily_subsistence_to_employee_profile(env)
    _register_subsistence_salary_rules(env)


def uninstall_hook(env):
    env['hr.salary.rule'].search([
        ('code', 'in', ['FIXED_SUBS', 'DAILY_SUBS']),
    ]).unlink()
