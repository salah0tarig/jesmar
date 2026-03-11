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
            return act.activity_analytic_account_id

        lines_with_activity = self.filtered(lambda l: l.activity_id and _get_analytic_account(l))
        for line in lines_with_activity:
            acc = _get_analytic_account(line)
            line.analytic_distribution = {str(acc.id): 100}

        # Other lines: use default (product/partner-based) computation
        lines_without = self - lines_with_activity
        if lines_without:
            super(PurchaseOrderLine, lines_without)._compute_analytic_distribution()

    @api.depends('analytic_distribution', 'activity_id', 'product_id', 'order_id.date_order', 'product_qty', 'qty_received')
    def _compute_budget_line_ids(self):
        """Override: when activity+product set, search budget lines directly; else use base logic and filter."""
        lines_direct = self.filtered(lambda l: l.activity_id and l.product_id and l.order_id and (l.product_qty or 0) - (l.qty_received or 0) > 0)
        lines_base = self - lines_direct
        # Direct search for lines with activity+product
        for line in lines_direct:
            acc = line.activity_id.activity_analytic_account_id or line.activity_id.output_id
            if not acc:
                line.budget_line_ids = self.env['budget.line']
                continue
            # Match: (task=our activity) OR (no task and account=our analytic)
            domain = [
                '|', ('task_id', '=', line.activity_id.id), '&', ('task_id', '=', False), ('account_id', '=', acc.id),
                ('budget_analytic_id.budget_type', '!=', 'revenue'),
                ('budget_analytic_id.state', 'in', ['confirmed', 'done']),
                ('date_from', '<=', line.order_id.date_order),
                ('date_to', '>=', line.order_id.date_order),
                '|', ('product_id', '=', False), ('product_id', '=', line.product_id.id),
            ]
            if line.company_id:
                domain.extend(['|', ('company_id', '=', False), ('company_id', '=', line.company_id.id)])
            line.budget_line_ids = self.sudo().env['budget.line'].search(domain)
        # Base logic for other lines
        if lines_base:
            super(PurchaseOrderLine, lines_base)._compute_budget_line_ids()
            for line in lines_base:
                if line.activity_id and line.product_id and line.budget_line_ids:
                    line.budget_line_ids = line.budget_line_ids.filtered(
                        lambda bl, al=line: (not bl.task_id or bl.task_id == al.activity_id)
                        and (not bl.product_id or bl.product_id == al.product_id)
                    )

    def write(self, vals):
        res = super().write(vals)
        if any(f in vals for f in ('activity_id', 'analytic_distribution', 'product_id', 'product_qty', 'price_unit', 'price_subtotal')):
            # Invalidate budget lines so committed_amount recomputes from POL query
            self.env['budget.line'].invalidate_model(['committed_amount', 'committed_percentage'])
        return res

    @api.constrains('activity_id', 'product_id', 'price_subtotal', 'product_qty', 'price_unit', 'order_id')
    def _check_budget_remaining(self):
        """Restrict when (balance + requested amount) would exceed budget. Balance = budget - achieved - committed."""
        for line in self:
            if not line.activity_id or not line.product_id or not line.order_id:
                continue
            if not line.budget_line_ids:
                continue
            # Invalidate so committed/achieved recompute on next read
            line.budget_line_ids.invalidate_recordset(['committed_amount', 'achieved_amount', 'committed_percentage', 'achieved_percentage', 'balance'])
            # Requested amount = this line's uninvoiced value that would add to committed
            requested = (
                line.price_unit * (line.product_qty - line.qty_invoiced)
                if line.order_id.state != 'purchase'
                else (line.price_subtotal or 0)
            )
            if requested <= 0:
                continue
            for budget in line.budget_line_ids:
                # Balance = remaining = budget - achieved - committed (what's left for new requests)
                balance = (budget.budget_amount or 0) - (budget.achieved_amount or 0) - (budget.committed_amount or 0)
                # Restrict when requested > balance (request exceeds what's available)
                if requested > balance:
                    currency = budget.budget_display_currency_id or line.currency_id
                    raise ValidationError(_(
                        "Budget exceeded for Activity '%(activity)s' and Product '%(product)s'. "
                        "Available balance: %(balance).2f %(currency)s. Requested amount: %(requested).2f %(currency)s."
                    ) % {
                        'activity': line.activity_id.name,
                        'product': line.product_id.name,
                        'balance': balance,
                        'requested': requested,
                        'currency': currency.name,
                    })
