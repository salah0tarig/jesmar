# -*- coding: utf-8 -*-

from odoo import api, fields, models


class BudgetLine(models.Model):
    _inherit = 'budget.line'

    @api.depends('account_id', 'task_id', 'task_id.activity_analytic_account_id', 'product_id', 'date_from', 'date_to', 'company_id', 'budget_analytic_id', 'budget_analytic_id.budget_type')
    def _compute_all(self):
        """Same as account_budget_purchase: single read_group from budget.report.
        Fallback to direct compute when report returns 0 (project hierarchy plan matching can fail)."""
        grouped = {
            line: (committed, achieved)
            for line, committed, achieved in self.env['budget.report']._read_group(
                domain=[('budget_line_id', 'in', self.ids)],
                groupby=['budget_line_id'],
                aggregates=['committed:sum', 'achieved:sum'],
            )
        }
        for line in self:
            committed, achieved = grouped.get(line, (0.0, 0.0))
            # Fallback when report returns 0: direct compute (plan matching fails for activity hierarchy)
            if not committed and line.task_id and line.task_id.activity_analytic_account_id and line.date_from and line.date_to:
                committed = line._compute_committed_from_pol()
            elif not committed and line.account_id and line.date_from and line.date_to:
                committed = line._compute_committed_from_pol()
            if not achieved and line.task_id and line.task_id.activity_analytic_account_id and line.date_from and line.date_to:
                achieved = line._compute_achieved_from_analytic()
            elif not achieved and line.account_id and line.date_from and line.date_to:
                achieved = line._compute_achieved_from_analytic()
            line.committed_amount = committed
            line.achieved_amount = achieved
            line.committed_percentage = line.budget_amount and (committed / line.budget_amount)
            line.achieved_percentage = line.budget_amount and (achieved / line.budget_amount)
            line._compute_balance()

    def _compute_achieved_from_analytic(self):
        """Fallback: sum achieved from account.analytic.line. Uses activity_analytic_account_id or account_id (same as report)."""
        self.ensure_one()
        if not self.date_from or not self.date_to:
            return 0.0
        analytic_account = (
            (self.task_id.activity_analytic_account_id if self.task_id else False)
            or self.account_id
        )
        if not analytic_account:
            return 0.0
        domain = [
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('company_id', '=', self.company_id.id) if self.company_id else ('company_id', '=', False),
            ('account_id', '=', analytic_account.id),
        ]
        # Product: when set, match to avoid mixing same product across activities
        if self.product_id:
            domain.append('|')
            domain.append(('product_id', '=', self.product_id.id))
            domain.append(('move_line_id.product_id', '=', self.product_id.id))
        # Expense/income: filter by general account type
        budget_type = (self.budget_analytic_id or self.env['budget.analytic']).budget_type
        if budget_type == 'expense':
            domain.append(('general_account_id.internal_group', '=', 'expense'))
        elif budget_type == 'revenue':
            domain.append(('general_account_id.internal_group', '=', 'income'))
        aal_records = self.env['account.analytic.line'].search(domain)
        sign = -1 if budget_type == 'expense' else 1
        return sum(aal.amount * sign for aal in aal_records)

    def _compute_committed_from_pol(self):
        """Fallback: sum uninvoiced amounts from confirmed PO lines. Uses activity_id or account in analytic."""
        self.ensure_one()
        if not self.date_from or not self.date_to:
            return 0.0
        analytic_account = (
            (self.task_id.activity_analytic_account_id if self.task_id else False)
            or self.account_id
        )
        if not analytic_account:
            return 0.0
        budget_type = (self.budget_analytic_id or self.env['budget.analytic']).budget_type
        if budget_type == 'revenue':
            return 0.0
        sign = -1 if budget_type == 'both' else 1
        # Find POL: order in purchase, date in range, match activity when task set
        pol_domain = [
            ('order_id.state', '=', 'purchase'),
            ('order_id.date_order', '>=', self.date_from),
            ('order_id.date_order', '<=', self.date_to),
        ]
        if self.company_id:
            pol_domain.append(('company_id', '=', self.company_id.id))
        if self.product_id:
            pol_domain.append(('product_id', '=', self.product_id.id))
        if self.task_id:
            pol_domain.append(('activity_id', '=', self.task_id.id))
        pols = self.env['purchase.order.line'].search(pol_domain)
        if not self.task_id:
            # No task: filter by analytic_distribution containing our account_id
            pols = pols.filtered(
                lambda p: p.analytic_distribution and str(analytic_account.id) in (p.analytic_distribution or {})
            )
        total = 0.0
        for pol in pols:
            uninvoiced_qty = pol.product_qty - pol.qty_invoiced
            if uninvoiced_qty <= 0:
                continue
            # Match by activity_analytic_account_id (same as achieved) - analytic must contain it
            dist = pol.analytic_distribution or {}
            if str(analytic_account.id) not in dist:
                continue
            line_total = pol.price_subtotal or pol.price_unit * pol.product_qty
            price_per_unit = line_total / (pol.product_qty or 1)
            amount_currency = price_per_unit * uninvoiced_qty
            company_currency = self.company_id.currency_id if self.company_id else self.env.company.currency_id
            if pol.currency_id != company_currency:
                amount_currency = pol.currency_id._convert(
                    amount_currency, company_currency,
                    pol.order_id.company_id or self.env.company,
                    pol.order_id.date_order or fields.Date.today(),
                )
            total += amount_currency * sign
        return total

    budget_currency_id = fields.Many2one(
        'res.currency',
        related='budget_analytic_id.budget_currency_id',
        string='Currency',
        readonly=True,
        help='Currency from the budget; when set, achieved amount is converted from company currency.',
    )
    budget_display_currency_id = fields.Many2one(
        'res.currency',
        compute='_compute_budget_display_currency_id',
        store=True,
        string='Display Currency',
    )
    outcome_id = fields.Many2one(
        'account.analytic.account',
        string='Outcome',
        ondelete='set null',
        domain="[('parent_id', '=', project_account_id or account_id or False)]",
        help='Outcome analytic account (parent must be project account)',
    )
    output_id = fields.Many2one(
        'account.analytic.account',
        string='Output',
        ondelete='set null',
        domain="[('parent_id', '=', outcome_id or False)]",
        help='Output analytic account (parent must be selected outcome)',
    )
    task_id = fields.Many2one(
        'project.task',
        string='Activity',
        ondelete='set null',
        domain="[('project_id', '=', budget_project_id), ('output_id', '=', output_id)]",
        help='Task/Activity - restricted to tasks linked to the selected Output',
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        ondelete='set null',
        help='When set, only PO lines with this product will consume this budget line.',
    )
    budget_project_id = fields.Many2one(
        'project.project',
        related='budget_analytic_id.project_id',
        string='Budget Project',
    )
    project_account_id = fields.Many2one(
        'account.analytic.account',
        related='budget_project_id.account_id',
        string='Project Account',
    )
    budgetary_position = fields.Char(
        string='Budgetary Position',
        help='e.g. Materials, Labor, Equipment',
    )
    # --- Other-currency amounts: pure conversion of base fields, no base logic changes ---
    budget_amount_other = fields.Monetary(
        string='Budgeted (Other)',
        compute='_compute_amounts_other_currency',
        store=True,
        currency_field='budget_display_currency_id',
        help='Budgeted amount converted to the budget currency.',
    )
    committed_amount_other = fields.Monetary(
        string='Committed (Other)',
        compute='_compute_amounts_other_currency',
        store=False,
        currency_field='budget_display_currency_id',
        help='Committed amount converted to the budget currency. Always fresh from purchase/invoice data.',
    )
    achieved_in_currency = fields.Monetary(
        string='Achieved (Other)',
        compute='_compute_amounts_other_currency',
        store=False,
        currency_field='budget_display_currency_id',
        help='Achieved amount converted to the budget currency. Always fresh from purchase/invoice data.',
    )
    theoritical_amount_other = fields.Monetary(
        string='Theoretical (Other)',
        compute='_compute_amounts_other_currency',
        store=True,
        currency_field='budget_display_currency_id',
        help='Theoretical amount converted to the budget currency.',
    )
    balance_other = fields.Monetary(
        string='Balance (Other)',
        compute='_compute_amounts_other_currency',
        store=False,
        currency_field='budget_display_currency_id',
        help='Balance (Budgeted - Achieved) converted to the budget currency. Always fresh.',
    )
    balance = fields.Monetary(
        string='Balance',
        compute='_compute_balance',
        store=True,
        currency_field='company_currency_id',
        help='Budgeted - Achieved',
    )
    company_currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
        string='Company Currency',
    )

    @api.depends('budget_currency_id', 'company_id')
    def _compute_budget_display_currency_id(self):
        for line in self:
            line.budget_display_currency_id = (
                line.budget_currency_id
                or (line.company_id or self.env.company).currency_id
            )

    def _convert_to_other_currency(self, line, amount):
        """Convert amount from company currency to budget currency. Returns amount as-is when no conversion needed."""
        if not amount:
            return 0.0
        company_currency = (line.company_id or self.env.company).currency_id
        if not line.budget_currency_id or line.budget_currency_id == company_currency:
            return amount
        conv_date = line.date_to or fields.Date.context_today(self)
        return company_currency._convert(
            from_amount=amount,
            to_currency=line.budget_currency_id,
            company=line.company_id or self.env.company,
            date=conv_date,
        )

    @api.depends(
        'budget_amount', 'achieved_amount', 'theoritical_amount', 'committed_amount', 'balance',
        'budget_currency_id', 'company_id', 'date_to', 'budget_analytic_state'
    )
    def _compute_amounts_other_currency(self):
        """Convert base amounts to other currency. Uses our achieved_amount and committed_amount (from our direct POL compute)."""
        if not self:
            return
        for line in self:
            committed = line.committed_amount  # From our _compute_all (direct POL when task+activity)
            achieved = line.achieved_amount  # From our _compute_achieved_from_analytic
            line.budget_amount_other = line._convert_to_other_currency(line, line.budget_amount)
            line.achieved_in_currency = line._convert_to_other_currency(line, achieved)
            line.theoritical_amount_other = line._convert_to_other_currency(line, line.theoritical_amount)
            line.committed_amount_other = line._convert_to_other_currency(line, committed)
            line.balance_other = line._convert_to_other_currency(line, (line.budget_amount or 0.0) - achieved)

    @api.depends('budget_amount', 'achieved_amount')
    def _compute_balance(self):
        for line in self:
            line.balance = (line.budget_amount or 0.0) - (line.achieved_amount or 0.0)

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        budget_analytic_id = self.env.context.get('default_budget_analytic_id') or defaults.get('budget_analytic_id')
        if budget_analytic_id and (not fields_list or 'account_id' in fields_list):
            budget_analytic = self.env['budget.analytic'].browse(budget_analytic_id)
            if budget_analytic.project_id and budget_analytic.project_id.account_id:
                defaults['account_id'] = budget_analytic.project_id.account_id.id
        return defaults

    def _get_account_id_for_budget_line(self, task_id=None, output_id=None, outcome_id=None, project_account_id=None):
        """Return the analytic account to use for budget matching.
        Must match PO line analytic_distribution (activity_analytic_account_id) for committed/achieved to work."""
        if task_id:
            task = self.env['project.task'].browse(task_id)
            if task.exists():
                acc = task.activity_analytic_account_id or False
                return acc.id if acc else None
        if output_id:
            return output_id
        if outcome_id:
            return outcome_id
        if project_account_id:
            return project_account_id
        return None

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'account_id' not in vals:
                proj_acc = None
                if vals.get('budget_analytic_id'):
                    ba = self.env['budget.analytic'].browse(vals['budget_analytic_id'])
                    if ba.project_id and ba.project_id.account_id:
                        proj_acc = ba.project_id.account_id.id
                acc = self._get_account_id_for_budget_line(
                    task_id=vals.get('task_id'),
                    output_id=vals.get('output_id'),
                    outcome_id=vals.get('outcome_id'),
                    project_account_id=proj_acc,
                )
                if acc:
                    vals['account_id'] = acc
        return super().create(vals_list)

    def write(self, vals):
        if 'account_id' not in vals and any(k in vals for k in ('task_id', 'output_id', 'outcome_id')):
            line = self[0]
            task_id = vals.get('task_id', line.task_id.id if line.task_id else None)
            output_id = vals.get('output_id', line.output_id.id if line.output_id else None)
            outcome_id = vals.get('outcome_id', line.outcome_id.id if line.outcome_id else None)
            proj_acc = None
            if line.budget_analytic_id and (line.budget_analytic_id.project_id or line.budget_project_id):
                proj = line.budget_project_id or line.budget_analytic_id.project_id
                if proj and proj.account_id:
                    proj_acc = proj.account_id.id
            acc = line._get_account_id_for_budget_line(
                task_id=task_id,
                output_id=output_id,
                outcome_id=outcome_id,
                project_account_id=proj_acc,
            )
            if acc:
                vals['account_id'] = acc
        return super().write(vals)

    @api.onchange('budget_analytic_id', 'budget_project_id')
    def _onchange_project_clear_outcome_output(self):
        """When budget/project changes, clear outcome and output; set account_id from project."""
        if self.project_account_id:
            self.account_id = self.project_account_id

    def action_sync_account_from_activity(self):
        """Recompute account_id from task/output/outcome for selected lines. Use after data fixes or imports."""
        for line in self:
            acc = line._get_account_id_for_budget_line(
                task_id=line.task_id.id if line.task_id else None,
                output_id=line.output_id.id if line.output_id else None,
                outcome_id=line.outcome_id.id if line.outcome_id else None,
                project_account_id=(
                    (line.budget_project_id or line.budget_analytic_id.project_id).account_id.id
                    if (line.budget_analytic_id and (line.budget_analytic_id.project_id or line.budget_project_id))
                    else None
                ),
            )
            if acc and line.account_id.id != acc:
                line.account_id = acc

    @api.onchange('task_id')
    def _onchange_task_id_set_account(self):
        """When Activity is selected, set Outcome, Output and account_id from task.
        account_id must = activity_analytic_account_id so PO lines with this activity match for committed/achieved."""
        if self.task_id:
            self.outcome_id = self.task_id.outcome_id
            self.output_id = self.task_id.output_id
            acc = self.task_id.activity_analytic_account_id or self.task_id.output_id
            self.account_id = acc if acc else False

    @api.onchange('output_id')
    def _onchange_output_clear_task_set_account(self):
        """When Output changes: clear task if it no longer matches; set account_id if no task."""
        if self.output_id:
            if self.task_id and self.task_id.output_id != self.output_id:
                self.task_id = False
          

          

    

