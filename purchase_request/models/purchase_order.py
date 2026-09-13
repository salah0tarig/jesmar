from odoo import models, fields, api
from odoo.exceptions import UserError


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    # pr_id = fields.Many2one('procurement.requisition' )
    pr_id = fields.Many2one('procurement.requisition',ondelete='set null')
    delivery_location_id = fields.Many2one('stock.location')
    project_id = fields.Many2one('project.project',string="Project")
    
    state = fields.Selection(selection_add=[
        ('to_approve_mgmt', 'Waiting Management Approval')
    ])
    @api.model
    def create(self, vals):
        po = super().create(vals)

        if po.pr_id:
            po.pr_id.update_state_from_po()

        return po
    def button_confirm(self):
        res = super().button_confirm()

        for po in self:
            if not self.env.user.has_group('purchase_request.group_po_manager'):
                raise UserError("Only PO Manager can approve PO")
            if po.pr_id:
                po.pr_id.update_state_from_po()

        return res
    
    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)

        req_id = self.env.context.get('default_pr_id')
        if not req_id:
            return res

        req = self.env['procurement.requisition'].browse(req_id)

        lines = []

        for line in req.line_ids:
            if not line.product_id:
                continue

            product = line.product_id
            lines.append((0, 0, {
                'product_id': line.product_id.id,
                'product_qty': line.quantity,
                'price_unit': line.price,
                'name': line.product_id.display_name,
                'activity_id': line.task_id.id,
                'product_uom_id': product.uom_id.id,  
                'date_planned': fields.Datetime.now(),
            }))

        res.update({
            'pr_id': req.id,
            'order_line': lines,
            'delivery_location_id': req.delivery_location_id.id,
            'project_id': req.project_id.id,
            
        })

        return res

    def action_submit_mgmt(self):
        for po in self:

            po.state = 'to_approve_mgmt'

            if po.pr_id:
                po.pr_id.state = 'to_approve_mgmt'
                # po.pr_id.approver_id = matrix.approver_id.id

    def action_mgmt_approve(self):
    

        for po in self:
            if po.pr_id:
                po.pr_id.state = 'po_approved'
        self._update_pr_state()
        return res

    def action_mgmt_reject(self):
        self.button_cancel()

        for po in self:
            req = po.pr_id
            if not req:
                continue

            all_cancelled = all(
                p.state == 'cancel'
                for p in self.search([('pr_id', '=', req.id)])
            )

            if all_cancelled:
                req.action_reject()
                
    def _update_pr_state(self):
        for po in self:
            if po.pr_id:
                po.pr_id.update_state_from_po()