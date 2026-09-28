# -*- coding: utf-8 -*-

from odoo import api, models


class AccountPaymentRegister(models.TransientModel):
    _inherit = "account.payment.register"

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
