# -*- coding: utf-8 -*-

from odoo import api, fields, models


class AccountPaymentSignature(models.Model):
    _name = 'account.payment.signature'
    _description = 'Payment Voucher Signature'
    _order = 'sequence, id'

    payment_id = fields.Many2one(
        'account.payment',
        string='Payment',
        required=True,
        ondelete='cascade',
        index=True,
    )
    sequence = fields.Integer(default=10)
    role = fields.Selection(
        selection=[
            ('prepared', 'Prepared By'),
            ('reviewed', 'Reviewed By'),
            ('approved', 'Approved By'),
            ('checked', 'Checked By'),
            ('accounts_officer', 'Accounts Officer'),
        ],
        string='Role',
        required=True,
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        check_company=True,
    )
    signer_name = fields.Char(string='Name', readonly=True)
    signer_position = fields.Char(string='Position', readonly=True)
    signature = fields.Binary(string='Signature', attachment=True)

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        self._apply_employee_signer_values()

    @api.model
    def _employee_signer_values(self, employee):
        if not employee:
            return {}
        position = employee.job_title or (employee.job_id.name if employee.job_id else '')
        return {
            'signer_name': employee.name,
            'signer_position': position,
        }

    def _apply_employee_signer_values(self):
        for signature in self:
            if signature.employee_id:
                signature.update(signature._employee_signer_values(signature.employee_id))

    @api.model_create_multi
    def create(self, vals_list):
        Employee = self.env['hr.employee']
        for vals in vals_list:
            employee_id = vals.get('employee_id')
            if employee_id and 'signer_name' not in vals:
                vals.update(self._employee_signer_values(Employee.browse(employee_id)))
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('employee_id'):
            vals.update(self._employee_signer_values(self.env['hr.employee'].browse(vals['employee_id'])))
        return super().write(vals)
