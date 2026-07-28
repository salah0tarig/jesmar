# -*- coding: utf-8 -*-

from odoo import fields, models, _
from odoo.tools import html2plaintext
from odoo.tools.misc import format_date


class AccountMove(models.Model):
    _inherit = 'account.move'

    voucher_quick_notes = fields.Text(string='Voucher Quick Notes')
    voucher_entered_on = fields.Date(
        string='Voucher Entered On',
        default=fields.Date.context_today,
    )

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

    def _get_journal_voucher_lines(self):
        self.ensure_one()
        rows = []
        total_debit = 0.0
        total_credit = 0.0
        for line in self.line_ids.sorted(key=lambda aml: (aml.sequence, aml.id)):
            if line.display_type in ('line_section', 'line_note', 'line_subsection'):
                continue
            if not line.debit and not line.credit:
                continue
            account = line.account_id
            rows.append({
                'gl_code': account.code or '',
                'account_name': account.display_name or '',
                'dept': self._voucher_line_dept(line),
                'description': line.name or '',
                'debit': line.debit,
                'credit': line.credit,
            })
            total_debit += line.debit
            total_credit += line.credit
        return rows, total_debit, total_credit

    def _get_voucher_partner_name(self):
        self.ensure_one()
        if self.partner_id:
            return self.partner_id.display_name
        partners = self.line_ids.partner_id
        if partners:
            return ', '.join(dict.fromkeys(partners.mapped('display_name')))
        return ''

    def _get_voucher_description(self):
        self.ensure_one()
        if self.ref:
            return self.ref
        line_names = [
            name.strip()
            for name in self.line_ids.mapped('name')
            if name and name.strip()
        ]
        if line_names:
            return line_names[0]
        if self.narration:
            return html2plaintext(self.narration).strip()
        return ''

    def _get_journal_voucher_report_values(self):
        self.ensure_one()
        lines, total_debit, total_credit = self._get_journal_voucher_lines()
        entered_on = self.voucher_entered_on or self.date
        return {
            'title': _('JOURNAL VOUCHER'),
            'doc_number': self.name or '',
            'source_label': _('GL Journal Voucher'),
            'branch_name': self.company_id.name or '',
            'journal_name': self.journal_id.display_name or '',
            'reference': self.ref or '',
            'description': self._get_voucher_description(),
            'partner_name': self._get_voucher_partner_name(),
            'prepared_by': self.create_uid.name or '',
            'entered_on': entered_on,
            'entered_on_display': format_date(self.env, entered_on) if entered_on else '',
            'quick_notes': self.voucher_quick_notes or '',
            'check_number': '',
            'lines': lines,
            'total_debit': total_debit,
            'total_credit': total_credit,
            'grand_total_label': _('Grand Total'),
            'subtotal_label': _('Subtotal for'),
        }
