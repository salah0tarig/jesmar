from odoo import models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def button_validate(self):
        # Check permission before validation
        if not self.env.user.has_group("purchase_request.group_store_user"):
            raise UserError("Only Store users can validate receipts.")

        res = super().button_validate()

        for picking in self:
            po = picking.purchase_id
            if po and po.pr_id:
                po.pr_id.update_state_from_po()

        return res
    
    
    
