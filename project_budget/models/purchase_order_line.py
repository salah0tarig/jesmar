# -*- coding: utf-8 -*-

from odoo import api, fields, models


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    activity_id = fields.Many2one(
        'project.task',
        string='Activity',
        help='When set, the Output analytic account from this activity is applied to analytic distribution at 100%. '
             'Removing the activity clears the analytic distribution.',
    )

    @api.depends('product_id', 'order_id.partner_id', 'activity_id', 'activity_id.output_id')
    def _compute_analytic_distribution(self):
        # Lines with activity that has output: use output's analytic account at 100%
        lines_with_activity = self.filtered(lambda l: l.activity_id and l.activity_id.output_id)
        for line in lines_with_activity:
            line.analytic_distribution = {str(line.activity_id.output_id.id): 100}

        # Other lines: use default (product/partner-based) computation
        lines_without = self - lines_with_activity
        if lines_without:
            super(PurchaseOrderLine, lines_without)._compute_analytic_distribution()
