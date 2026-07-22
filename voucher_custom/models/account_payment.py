# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    amount_in_words = fields.Char(
        string='Amount in Words',
        compute='_compute_amount_in_words',
        store=True,
        readonly=True,
    )
    voucher_quick_notes = fields.Text(string='Voucher Quick Notes')
    voucher_entered_on = fields.Date(
        string='Voucher Entered On',
        default=fields.Date.context_today,
    )
    voucher_signature_ids = fields.One2many(
        'account.payment.signature',
        'payment_id',
        string='Voucher Signatures',
        copy=True,
    )
    voucher_project_display = fields.Char(
        string='Voucher Project(s)',
        compute='_compute_voucher_project_info',
    )
    voucher_project_aa_display = fields.Char(
        string='Voucher Project Account(s)',
        compute='_compute_voucher_project_info',
    )
    voucher_donor_display = fields.Char(
        string='Voucher Donor(s)',
        compute='_compute_voucher_project_info',
    )
    voucher_check_number = fields.Char(
        string='Cheque Number',
        compute='_compute_voucher_check_number',
    )

    @api.depends('amount', 'currency_id')
    def _compute_amount_in_words(self):
        for payment in self:
            if payment.currency_id and payment.amount:
                payment.amount_in_words = payment.currency_id.amount_to_text(payment.amount)
            else:
                payment.amount_in_words = ''

    @api.depends(
        'reconciled_bill_ids',
        'reconciled_bill_ids.invoice_line_ids.purchase_line_id.order_id.project_id.donor_id',
    )
    def _compute_voucher_project_info(self):
        for payment in self:
            projects = payment._get_voucher_projects()
            payment.voucher_project_display = ', '.join(projects.mapped('name'))
            payment.voucher_project_aa_display = ', '.join(
                aa for aa in projects.mapped('account_id.display_name') if aa
            )
            donor_names = [
                name for name in projects.mapped('donor_id.display_name') if name
            ]
            payment.voucher_donor_display = ', '.join(dict.fromkeys(donor_names))

    def _compute_voucher_check_number(self):
        for payment in self:
            payment.voucher_check_number = getattr(payment, 'check_number', False) or ''

    def _get_voucher_bills(self):
        self.ensure_one()
        bills = self.reconciled_bill_ids
        if not bills:
            bills = self.invoice_ids.filtered(lambda move: move.is_purchase_document(include_receipts=True))
        return bills

    def _get_voucher_projects(self):
        self.ensure_one()
        Project = self.env['project.project']
        projects = Project
        for bill in self._get_voucher_bills():
            po_lines = bill.invoice_line_ids.mapped('purchase_line_id')
            projects |= po_lines.order_id.project_id
        return projects

    def _voucher_line_dept(self, move_line):
        """Analytic account label used as department / budget dimension on the voucher."""
        self.ensure_one()
        distribution = move_line.analytic_distribution or {}
        if not distribution:
            return ''
        account_ids = []
        for key in distribution:
            account_ids.extend(int(part) for part in key.split(',') if part)
        accounts = self.env['account.analytic.account'].browse(account_ids).exists()
        return ', '.join(accounts.mapped('display_name'))

    def _get_voucher_journal_lines(self):
        self.ensure_one()
        rows = []
        total_debit = 0.0
        total_credit = 0.0
        move = self.move_id
        if not move:
            return rows, total_debit, total_credit

        for line in move.line_ids.sorted(key=lambda aml: (aml.sequence, aml.id)):
            if line.display_type in ('line_section', 'line_note', 'line_subsection'):
                continue
            if not line.debit and not line.credit:
                continue
            rows.append({
                'account_name': line.account_id.display_name or '',
                'dept': self._voucher_line_dept(line),
                'description': line.name or '',
                'debit': line.debit,
                'credit': line.credit,
            })
            total_debit += line.debit
            total_credit += line.credit
        return rows, total_debit, total_credit

    def _get_voucher_signatures_by_role(self):
        self.ensure_one()
        role_labels = dict(self.env['account.payment.signature']._fields['role'].selection)
        grouped = {key: [] for key in role_labels}
        for signature in self.voucher_signature_ids:
            grouped.setdefault(signature.role, []).append(signature)
        return grouped, role_labels

    def _get_payment_voucher_report_values(self):
        self.ensure_one()
        journal_lines, total_debit, total_credit = self._get_voucher_journal_lines()
        signatures_by_role, role_labels = self._get_voucher_signatures_by_role()
        projects = self._get_voucher_projects()
        return {
            'journal_lines': journal_lines,
            'total_debit': total_debit,
            'total_credit': total_credit,
            'project_names': ', '.join(projects.mapped('name')),
            'project_accounts': ', '.join(
                aa for aa in projects.mapped('account_id.display_name') if aa
            ),
            'donors': self.voucher_donor_display or '',
            'signatures_by_role': signatures_by_role,
            'role_labels': role_labels,
            'check_number': self.voucher_check_number or '',
            'doc_number': self.name or '',
            'source_label': _('GL Payment Voucher'),
            'branch_name': self.company_id.name or '',
        }
