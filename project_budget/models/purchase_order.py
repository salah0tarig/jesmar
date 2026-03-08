# -*- coding: utf-8 -*-

from odoo import api, models


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    @api.onchange('project_id')
    def _onchange_project_id_clear_activity(self):
        """When project changes, clear activity on lines whose activity belongs to another project."""
        if not self.order_line:
            return
        for line in self.order_line:
            if line.activity_id:
                if not self.project_id or line.activity_id.project_id != self.project_id:
                    line.activity_id = False
