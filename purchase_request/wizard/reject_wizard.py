from odoo import models, fields

class RejectWizard(models.TransientModel):
    _name = 'procurement.reject.wizard'
    _description = 'Reject Reason'

    reason = fields.Text(required=True)

    def action_confirm(self):
        req = self.env['procurement.requisition'].browse(self.env.context.get('active_id'))

        req.write({
            'state': 'rejected',
            'reject_reason': self.reason,
            'rejected_by': self.env.user.id,
            'rejected_date': fields.Datetime.now()
        })