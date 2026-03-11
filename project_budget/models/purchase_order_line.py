# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    activity_id = fields.Many2one(
        'project.task',
        string='Activity',
        help='When set, the Activity Analytic Account from this activity is applied to analytic distribution at 100%. '
             'Removing the activity clears the analytic distribution.',
    )

    @api.depends('product_id', 'order_id.partner_id', 'activity_id', 'activity_id.activity_analytic_account_id', 'activity_id.output_id')
    def _compute_analytic_distribution(self):
        # Lines with activity: use activity analytic account (or output as fallback) at 100%
        def _get_analytic_account(line):
            act = line.activity_id
            return act.activity_analytic_account_id or act.output_id

        lines_with_activity = self.filtered(lambda l: l.activity_id and _get_analytic_account(l))
        for line in lines_with_activity:
            acc = _get_analytic_account(line)
            line.analytic_distribution = {str(acc.id): 100}

        # Other lines: use default (product/partner-based) computation
        lines_without = self - lines_with_activity
        if lines_without:
            super(PurchaseOrderLine, lines_without)._compute_analytic_distribution()

    @api.depends('analytic_distribution', 'activity_id', 'product_id')
    def _compute_budget_line_ids(self):
        """Override to filter budget lines by activity and product when both are set."""
        super()._compute_budget_line_ids()
        for line in self:
            if line.activity_id and line.product_id and line.budget_line_ids:
                # Filter to budget lines matching activity and (no product or same product)
                line.budget_line_ids = line.budget_line_ids.filtered(
                    lambda bl: (not bl.task_id or bl.task_id == line.activity_id)
                    and (not bl.product_id or bl.product_id == line.product_id)
                )

    def write(self, vals):
        res = super().write(vals)
        if any(f in vals for f in ('activity_id', 'analytic_distribution', 'product_id', 'product_qty', 'price_unit', 'price_subtotal')):
            # Invalidate budget lines so committed_amount recomputes from POL query
            self.env['budget.line'].invalidate_model(['committed_amount', 'committed_percentage'])
        return res

    @api.constrains('activity_id', 'product_id', 'price_subtotal', 'product_qty', 'price_unit', 'order_id')
    def _check_budget_remaining(self):
        """Block PO line if subtotal exceeds remaining budget for activity+product."""
        for line in self:
            if not line.activity_id or not line.product_id or not line.budget_line_ids:
                continue
            # Recompute to get fresh budget amounts
            line.budget_line_ids.invalidate_recordset(['committed_amount', 'achieved_amount', 'balance'])
            uncommitted = line.price_unit * (line.product_qty - line.qty_invoiced) if line.order_id.state != 'purchase' else line.price_subtotal
            if uncommitted <= 0:
                continue
            for budget in line.budget_line_ids:
                # Remaining = budgeted - achieved - committed
                remaining = (budget.budget_amount or 0) - budget.achieved_amount - (budget.committed_amount or 0)
                if uncommitted > remaining:
                    currency = budget.budget_display_currency_id or line.currency_id
                    raise ValidationError(_(
                        "Budget exceeded for Activity '%(activity)s' and Product '%(product)s'. "
                        "Remaining budget: %(remaining).2f %(currency)s. Line amount: %(amount).2f %(currency)s."
                    ) % {
                        'activity': line.activity_id.name,
                        'product': line.product_id.name,
                        'remaining': remaining,
                        'amount': uncommitted,
                        'currency': currency.name,
                    })
