# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.tools.misc import formatLang, format_date


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
            payment.voucher_project_aa_display = payment._get_voucher_project_account_display(projects)
            donor_names = [
                name for name in projects.mapped('donor_id.display_name') if name
            ]
            payment.voucher_donor_display = ', '.join(dict.fromkeys(donor_names))

    def _compute_voucher_check_number(self):
        for payment in self:
            payment.voucher_check_number = getattr(payment, 'check_number', False) or ''

    def _get_voucher_project_account_display(self, projects):
        """Analytic account display name(s) for the voucher."""
        labels = []
        for project in projects:
            account = project.account_id
            if not account:
                continue
            label = (account.display_name or '').strip()
            if label and label not in labels:
                labels.append(label)
        return ', '.join(labels)

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

    def _journal_lines_from_move(self, move):
        """Build voucher table rows from one posted journal entry."""
        self.ensure_one()
        rows = []
        total_debit = 0.0
        total_credit = 0.0
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

    def _get_voucher_journal_sections(self, is_receipt=False):
        """Payment/receipt journal entry only for the voucher table."""
        self.ensure_one()
        sections = []
        payment_lines, payment_debit, payment_credit = self._journal_lines_from_move(self.move_id)
        if payment_lines:
            title_tmpl = _('Receipt Journal Entry: %s') if is_receipt else _('Payment Journal Entry: %s')
            sections.append({
                'title': title_tmpl % (self.name or self.display_name),
                'lines': payment_lines,
                'total_debit': payment_debit,
                'total_credit': payment_credit,
            })
        return sections, payment_debit, payment_credit

    def _get_voucher_currency_rate_info(self):
        """Return exchange rate for voucher when payment currency != company currency."""
        self.ensure_one()
        company_currency = self.company_currency_id
        payment_currency = self.currency_id
        if not payment_currency or payment_currency == company_currency:
            return False

        rate_date = self.date or fields.Date.context_today(self)
        rate = None

        if self.move_id and self.move_id.state == 'posted':
            foreign_lines = self.move_id.line_ids.filtered(
                lambda line: line.currency_id == payment_currency
                and line.amount_currency
                and not line.display_type
            )
            if foreign_lines:
                line = foreign_lines[0]
                if line.amount_currency:
                    rate = abs(line.balance) / abs(line.amount_currency)

        if not rate:
            rate = payment_currency._convert(
                1.0,
                company_currency,
                self.company_id,
                rate_date,
            )

        rate_digits = max(company_currency.decimal_places or 2, 4)
        rate_formatted = formatLang(self.env, rate, digits=rate_digits)
        return {
            'date': rate_date,
            'date_display': format_date(self.env, rate_date),
            'rate': rate,
            'payment_currency': payment_currency.name,
            'company_currency': company_currency.name,
            'rate_display': _('1 %(from)s = %(rate)s %(to)s') % {
                'from': payment_currency.name,
                'rate': rate_formatted,
                'to': company_currency.name,
            },
        }

    def _get_payment_voucher_report_values(self, voucher_type=None):
        self.ensure_one()
        is_receipt = (voucher_type == 'receipt') or (
            voucher_type is None and self.payment_type == 'inbound'
        )
        journal_sections, total_debit, total_credit = self._get_voucher_journal_sections(
            is_receipt=is_receipt
        )
        projects = self._get_voucher_projects()
        project_names = ', '.join(projects.mapped('name'))
        project_accounts = self._get_voucher_project_account_display(projects)
        if is_receipt:
            labels = {
                'title': _('RECEIPT VOUCHER'),
                'partner_label': _('Received From'),
                'description_label': _('Description'),
                'amount_label': _('Receipt Amount'),
                'note': _('Being receipt against transactions listed below'),
                'grand_total_label': _('Grand Total (Receipt)'),
                'source_label': _('GL Receipt Voucher'),
            }
        else:
            labels = {
                'title': _('PAYMENT VOUCHER'),
                'partner_label': _('Pay To'),
                'description_label': _('Description'),
                'amount_label': _('Payment Amount'),
                'note': _('Being payment against transactions listed below'),
                'grand_total_label': _('Grand Total (Payment)'),
                'source_label': _('GL Payment Voucher'),
            }
        return {
            'is_receipt': is_receipt,
            'labels': labels,
            'journal_sections': journal_sections,
            'total_debit': total_debit,
            'total_credit': total_credit,
            'project_names': project_names,
            'project_accounts': project_accounts,
            'donors': self.voucher_donor_display or '',
            'check_number': self.voucher_check_number or '',
            'doc_number': self.name or '',
            'source_label': labels['source_label'],
            'branch_name': self.company_id.name or '',
            'currency_rate_info': self._get_voucher_currency_rate_info(),
        }
