from odoo import models

class AccountMove(models.Model):
    _inherit = 'account.move'

    def write(self, vals):
        res = super().write(vals)

        if 'payment_state' in vals:
            for move in self:
                if move.move_type != 'in_invoice':
                    continue
                if move.payment_state == 'paid':
                    if not self.env.user.has_group('purchase_request.group_finance_payment'):
                        raise UserError("Only Finance can register payment")
                    pos = move.invoice_line_ids.mapped('purchase_line_id.order_id')
                if move.move_type == 'in_invoice':
                    pos = move.invoice_line_ids.mapped('purchase_line_id.order_id')
                    for po in pos:
                        if po.pr_id:
                            po.pr_id.update_state_from_po()

        return res
