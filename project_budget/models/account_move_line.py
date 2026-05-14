# -*- coding: utf-8 -*-
# Propagate expense product to journal + analytic lines so budget achieved
# (matched by product on budget.line) includes posted expenses.

from odoo import api, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("expense_id") and not vals.get("product_id"):
                expense = self.env["hr.expense"].browse(vals["expense_id"])
                if expense.exists() and expense.product_id:
                    vals["product_id"] = expense.product_id.id
        return super().create(vals_list)

    def write(self, vals):
        vals = dict(vals)
        if vals.get("expense_id") and not vals.get("product_id"):
            expense = self.env["hr.expense"].browse(vals["expense_id"])
            if expense.exists() and expense.product_id:
                vals["product_id"] = expense.product_id.id
        return super().write(vals)

    def _prepare_analytic_distribution_line(self, distribution, account_ids, distribution_on_each_plan):
        """Ensure product is set on generated analytic lines (and rely on aml.product_id for budget SQL)."""
        vals = super()._prepare_analytic_distribution_line(
            distribution, account_ids, distribution_on_each_plan
        )
        if not vals.get("product_id"):
            product = self.product_id
            if not product and self.expense_id:
                product = self.expense_id.product_id
            if product:
                vals["product_id"] = product.id
        return vals
