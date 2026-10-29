# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import UserError


class AccountPaymentRegister(models.TransientModel):
    _inherit = "account.payment.register"

    # Allow branch bank journals even when the salary entry is on HQ.
    journal_id = fields.Many2one(check_company=False)
    payment_method_line_id = fields.Many2one(check_company=False)

    payroll_journal_ids = fields.Many2many(
        "account.journal",
        compute="_compute_payroll_journal_ids",
        string="Branch payment journals",
    )

    def _payroll_mode(self):
        return bool(self.env.context.get("hr_payroll_payment_register"))

    def _payroll_branch_company_ids(self):
        """Companies whose bank journals may be used for payroll Pay."""
        ctx_ids = self.env.context.get("hr_payroll_payment_company_ids")
        if ctx_ids:
            return self.env["res.company"].browse(ctx_ids).exists()
        roots = self.line_ids.company_id.root_id | self.company_id.root_id
        return self.env.companies.filtered(lambda c: c.root_id in roots)

    @api.depends("line_ids", "can_group_payments", "payment_type")
    def _compute_payroll_journal_ids(self):
        Journal = self.env["account.journal"]
        for wizard in self:
            if not wizard._payroll_mode():
                wizard.payroll_journal_ids = wizard.available_journal_ids
                continue
            companies = wizard._payroll_branch_company_ids()
            if not companies:
                wizard.payroll_journal_ids = wizard.available_journal_ids
                continue
            journals = Journal.search([
                ("company_id", "in", companies.ids),
                ("type", "in", ("bank", "cash", "credit")),
            ])
            if wizard.payment_type == "inbound":
                journals = journals.filtered("inbound_payment_method_line_ids") or journals
            else:
                journals = journals.filtered("outbound_payment_method_line_ids") or journals
            wizard.payroll_journal_ids = journals

    @api.depends("available_journal_ids", "payroll_journal_ids")
    def _compute_journal_id(self):
        # Avoid company check when pre-selecting a branch journal.
        wizards = self
        if self._payroll_mode():
            wizards = self.with_context(tracking_disable=True)
        super(AccountPaymentRegister, wizards)._compute_journal_id()
        if not self._payroll_mode():
            return
        for wizard in self:
            journals = wizard.payroll_journal_ids
            if journals and wizard.journal_id not in journals:
                wizard.journal_id = journals[:1]

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
        payroll = self.filtered(lambda w: w._payroll_mode())
        other = self - payroll
        if other:
            super(AccountPaymentRegister, other)._compute_amount()
        for wizard in payroll:
            if wizard.custom_user_amount:
                continue
            lines = wizard.line_ids
            residual = abs(sum(lines.mapped("amount_residual_currency")))
            if lines and lines.currency_id[:1].is_zero(residual):
                residual = abs(sum(lines.mapped("amount_residual")))
            if wizard.journal_id and wizard.currency_id and wizard.payment_date and wizard.batches:
                total_amount_values = wizard._get_total_amounts_to_pay(wizard.batches)
                wizard.amount = total_amount_values["amount_by_default"] or residual
            else:
                wizard.amount = residual

    def _create_payment_vals_from_wizard(self, batch_result):
        payment_vals = super()._create_payment_vals_from_wizard(batch_result)
        if self._payroll_mode() and self.journal_id:
            payment_vals["company_id"] = self.journal_id.company_id.id
        return payment_vals

    def _create_payment_vals_from_batch(self, batch_result):
        payment_vals = super()._create_payment_vals_from_batch(batch_result)
        if self._payroll_mode() and self.journal_id:
            payment_vals["company_id"] = self.journal_id.company_id.id
        return payment_vals

    def _create_payments(self):
        """Allow HQ salary payable lines to be paid from a branch bank journal."""
        if not self._payroll_mode():
            return super()._create_payments()

        self.ensure_one()
        if not self.journal_id:
            raise UserError(self.env._("Please select a payment journal."))

        journal_company = self.journal_id.company_id
        line_companies = self.line_ids.company_id

        # Same company (or journal is parent of lines): standard flow.
        if journal_company in line_companies:
            return super()._create_payments()

        batches = list(self.batches)
        if not batches:
            raise UserError(self.env._("There's nothing left to pay."))

        payment_vals = self._create_payment_vals_from_wizard(batches[0])
        payment_vals["company_id"] = journal_company.id
        payment = (
            self.env["account.payment"]
            .with_company(journal_company)
            .with_context(check_company=False)
            .create(payment_vals)
        )
        payment.action_post()

        payslips = self.line_ids.move_id.payslip_ids
        if payslips:
            payslips.filtered(lambda s: s.state == "validated").action_payslip_paid()
        return payment
