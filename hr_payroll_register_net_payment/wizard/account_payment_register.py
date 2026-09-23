# -*- coding: utf-8 -*-

from odoo import api, models


class AccountPaymentRegister(models.TransientModel):
    _inherit = "account.payment.register"

    @api.depends(
        "can_edit_wizard",
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
        Pay, the residual is already known from the NET payable line — show it.
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
            if wizard.journal_id and wizard.currency_id and wizard.payment_date:
                total_amount_values = wizard._get_total_amounts_to_pay(wizard.batches)
                wizard.amount = total_amount_values["amount_by_default"]
            else:
                # Prefer currency residual from the NET payable line(s).
                wizard.amount = abs(wizard.source_amount_currency or wizard.source_amount or 0.0)
