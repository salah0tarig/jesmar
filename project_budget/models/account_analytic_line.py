# -*- coding: utf-8 -*-

from odoo import models


class AccountAnalyticLine(models.Model):
    _inherit = 'account.analytic.line'

    def create(self, vals_list):
        res = super().create(vals_list)
        self.env['budget.line'].invalidate_model(['achieved_amount', 'achieved_percentage', 'committed_amount', 'committed_percentage'])
        return res

    def write(self, vals):
        if any(f in vals for f in ('amount', 'account_id', 'date', 'company_id', 'product_id', 'move_line_id')):
            res = super().write(vals)
            self.env['budget.line'].invalidate_model(['achieved_amount', 'achieved_percentage', 'committed_amount', 'committed_percentage'])
            return res
        return super().write(vals)
