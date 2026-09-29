# -*- coding: utf-8 -*-

from odoo import api, fields, models


class AccountPaymentRegister(models.TransientModel):
    _inherit = "account.payment.register"

    payroll_journal_ids = fields.Many2many(
        "account.journal",
        compute="_compute_payroll_journal_ids",
        string="Payroll payment journals",
    )

    @api.depends("available_journal_ids", "company_id", "payment_type", "line_ids")
    def _compute_payroll_journal_ids(self):
        """Bank/Cash journals for this payslip, ignoring extra journal ACLs.

        Other modules (and the company switcher) can replace the journal
        domain with an empty list even when Bank/Cash journals exist.
        """
        for wizard in self:
            journals = wizard.available_journal_ids
            if self.env.context.get("hr_payroll_payment_register"):
                company_ids = list(self.env.context.get("hr_payroll_payment_company_ids") or [])
                if wizard.company_id:
                    company_ids.append(wizard.company_id.id)
                company_ids = list(dict.fromkeys(company_ids))
                extra = self.env["account.journal"].search([
                    ("company_id", "in", company_ids),
                    ("type", "in", ("bank", "cash", "credit")),
                ])
                if wizard.payment_type == "inbound":
                    with_methods = extra.filtered("inbound_payment_method_line_ids")
                else:
                    with_methods = extra.filtered("outbound_payment_method_line_ids")
                journals |= with_methods or extra
            wizard.payroll_journal_ids = journals

    @api.depends("available_journal_ids", "payroll_journal_ids")
    def _compute_journal_id(self):
        super()._compute_journal_id()
        if not self.env.context.get("hr_payroll_payment_register"):
            return
        for wizard in self:
            journals = wizard.payroll_journal_ids
            if journals and wizard.journal_id not in journals:
                wizard.journal_id = journals[:1]

    def _payroll_net_amount(self):
        """Outstanding NET payable, independent of the payment journal."""
        self.ensure_one()
        lines = self.line_ids
        if not lines:
            return abs(self.source_amount_currency or self.source_amount or 0.0)
        currency = self.currency_id or self.source_currency_id or self.company_id.currency_id
        total = 0.0
        for line in lines:
            if currency and line.currency_id == currency:
                total += abs(line.amount_residual_currency)
            else:
                total += abs(line.amount_residual)
        return total

    @api.depends(
        "can_edit_wizard",
        "line_ids",
        "line_ids.amount_residual",
        "line_ids.amount_residual_currency",
        "source_amount",
        "source_amount_currency",
        "source_currency_id",
        "company_id",
        "currency_id",
        "payment_date",
        "installments_mode",
        "journal_id",
    )
    def _compute_amount(self):
        """Fill Net salary amount even before a payment journal is chosen.

        Standard Odoo keeps amount at 0 while journal_id is empty. For payroll
        Pay, the residual is already known from the NET payable line.
        """
        payroll_wizards = self.filtered(
            lambda w: self.env.context.get("hr_payroll_payment_register")
        )
        other = self - payroll_wizards
        if other:
            super(AccountPaymentRegister, other)._compute_amount()

        for wizard in payroll_wizards:
            if wizard.custom_user_amount:
                wizard.amount = wizard.amount
                continue
            net_amount = wizard._payroll_net_amount()
            if wizard.journal_id and wizard.currency_id and wizard.payment_date and wizard.batches:
                total_amount_values = wizard._get_total_amounts_to_pay(wizard.batches)
                wizard.amount = total_amount_values["amount_by_default"] or net_amount
            else:
                wizard.amount = net_amount
