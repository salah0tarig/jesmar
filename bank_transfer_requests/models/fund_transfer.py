from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError, AccessError


class FundTransferRequest(models.Model):
    _name = "fund.transfer.request"
    _description = "Bank Transfer Request"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(
        string="Reference",
        required=True,
        readonly=True,
        copy=False,
        default="New",
        tracking=True,)

    company_id = fields.Many2one(
        "res.company",
        string="Requesting Branch",
        required=True,
        default=lambda self: self.env.company,
        readonly=True,
    )

    source_company_id = fields.Many2one(
        "res.company",
        string="Sending Branch",
        required=True,
    )

    destination_company_id = fields.Many2one(
        "res.company",
        string="Receiving Branch",
        required=True,
        default=lambda self: self.env.company,
        readonly=True,
        copy=False,
    )
    

    source_bank_journal_id = fields.Many2one(
        "account.journal",
        string="Sending Bank",
        domain="[('type', '=', 'bank'), "
               "('company_id', '=', source_company_id)]",
    )

    destination_bank_journal_id = fields.Many2one(
        "account.journal",
        string="Receiving Bank",
        required=True,
        domain="[('type', '=', 'bank'), "
               "('company_id', '=', destination_company_id)]",
    )

    currency_id = fields.Many2one(
        "res.currency",
        related="destination_company_id.currency_id",
        store=True,
    )

    amount = fields.Monetary(
        string="Amount",
        required=True,
        currency_field="currency_id",
    )

    memo = fields.Text(string="Purpose")

    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("pending", "Pending Approval"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("posted", "Posted"),  # legacy state retained for existing records
            ("awaiting_receipt", "Sent / Awaiting Receipt"),
            ("completed", "Completed"),
        ],
        default="draft",
        required=True,
        tracking=True,
        copy=False,
    )
    
    @api.onchange("source_company_id")
    def _onchange_source_company_id(self):
        self.source_bank_journal_id = False

    @api.onchange("destination_company_id")
    def _onchange_destination_company_id(self):
        self.destination_bank_journal_id = False

    @api.constrains(
    "source_company_id",
    "destination_company_id",
    "amount",
    "source_bank_journal_id",
    "destination_bank_journal_id",
    )
    def _check_transfer(self):
        for rec in self:
            if not rec.source_company_id:
                raise ValidationError(
                    _("Please select a Sending Branch.")
                )

            if not rec.destination_company_id:
                raise ValidationError(
                    _("Please select a Receiving Branch.")
                )

            if rec.source_company_id == rec.destination_company_id:
                raise ValidationError(
                    _("Sending and Receiving Branches must be different.")
                )

            if rec.amount <= 0:
                raise ValidationError(
                    _("Transfer amount must be greater than zero.")
                )

            if not rec.source_bank_journal_id:
                raise ValidationError(
                    _("Please select a Sending Bank.")
                )

            if not rec.destination_bank_journal_id:
                raise ValidationError(
                    _("Please select a Receiving Bank.")
                )

            if rec.source_bank_journal_id.type != "bank":
                raise ValidationError(
                    _("Sending Journal must be a Bank Journal.")
                )

            if rec.destination_bank_journal_id.type != "bank":
                raise ValidationError(
                    _("Receiving Journal must be a Bank Journal.")
                )

            if rec.source_bank_journal_id.company_id != rec.source_company_id:
                raise ValidationError(
                    _("Sending Bank must belong to the Sending Branch.")
                )

            if rec.destination_bank_journal_id.company_id != rec.destination_company_id:
                raise ValidationError(
                    _("Receiving Bank must belong to the Receiving Branch.")
                )
    @api.model_create_multi
    def create(self, vals_list):
        selected_company = self.env.company

        for vals in vals_list:
            if not self.env.user.has_group("bank_transfer_requests.group_branch_user"):
                raise AccessError(_("Only Branch Users may create transfer requests."))
            if vals.get("state", "draft") != "draft":
                raise AccessError(_("New requests must start in Draft."))
            if {"reject_reason", "approved_by_id", "approved_date"}.intersection(vals):
                raise AccessError(_("Approval metadata cannot be set at creation."))
            for field_name in ("company_id", "destination_company_id"):
                if (
                    field_name in vals
                    and vals[field_name] != selected_company.id
                ):
                    raise AccessError(
                        _("The receiving branch must match your selected company.")
                    )

                vals[field_name] = selected_company.id

            if not vals.get("name") or vals.get("name") == "New":
                reference = self.env["ir.sequence"].next_by_code(
                    "fund.transfer.request"
                )
                if not reference:
                    raise UserError(_(
                        "Bank Transfer sequence is missing. Configure sequence "
                        "code 'fund.transfer.request' for the selected company."
                    ))
                vals["name"] = reference


        return super().create(vals_list)
    

    reject_reason = fields.Text(string="Rejection Reason", readonly=True, copy=False)
    approved_by_id = fields.Many2one("res.users", string="Approved By", readonly=True, copy=False)
    approved_date = fields.Datetime(string="Approval Date", readonly=True, copy=False)

    sent_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    sent_date = fields.Datetime(readonly=True, copy=False)
    bank_reference = fields.Char(readonly=True, copy=False)
    received_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    received_date = fields.Datetime(readonly=True, copy=False)
    receipt_reference = fields.Char(readonly=True, copy=False)

    sending_move_id = fields.Many2one(
        "account.move", string="Sending Journal Entry", readonly=True, copy=False,
        check_company=False,
    )
    receiving_move_id = fields.Many2one(
    "account.move",
        string="Receiving Journal Entry",
        readonly=True,
        copy=False,
        check_company=False,
    )

    def _post_sending_bank_entry(self, bank_reference):
        """Post one direct bank-journal move, then atomically mark the request sent.

        WARNING: direct liquidity postings require an agreed bank statement
        reconciliation policy; do not also create an account.payment for this transfer.
        """
        self.ensure_one()
        # Lock the request row to serialize two concurrent send attempts.
        self.env.cr.execute(
            "SELECT id FROM fund_transfer_request WHERE id = %s FOR UPDATE", (self.id,)
        )
        self.invalidate_recordset(["state", "sending_move_id"])
        if self.state != "approved" or self.sending_move_id:
            raise UserError(_("This transfer has already been sent or is not approved."))
        self._check_approver()
        self._check_transfer()
        self._check_transfer_direction()
        bank_reference = (bank_reference or "").strip()
        if not bank_reference:
            raise UserError(_("A bank transfer reference is required."))

        company = self.source_company_id
        journal = self.source_bank_journal_id
        if journal.company_id != company or journal.type != "bank":
            raise UserError(_("The sending bank journal must belong to the sending branch."))
        if company.currency_id != self.destination_company_id.currency_id:
            raise UserError(_("Different company currencies are not supported in Step 4.2."))
        bank_account = journal.default_account_id
        if not bank_account:
            raise UserError(_("The sending bank journal has no liquidity account."))

        # This is an explicit account-code convention, NOT a hard-coded account ID.
        # Finance must confirm that account 101701 is suitable for interbranch transfers.
        Account = self.env["account.account"].sudo().with_company(company)
        clearing = Account.search([("code", "=", "101701")], limit=2)
        clearing = clearing.filtered(
            lambda a: company in a.company_ids
        )
        if len(clearing) != 1:
            raise UserError(_(
                "Exactly one Liquidity Transfer account (101701) must be available "
                "to the sending company. Ask Finance to verify its Companies field."
            ))
        clearing = clearing[0]
        if clearing == bank_account:
            raise UserError(_("Clearing and bank accounts must be different."))
        if clearing.account_type != "asset_current":
            raise UserError(_("The clearing account must be a Current Assets account."))
        if not clearing.reconcile:
            raise UserError(_("Enable reconciliation on the clearing account."))
        if company not in bank_account.company_ids:
            raise UserError(_("The liquidity account is not available to the sending company."))
        if clearing.currency_id and clearing.currency_id != company.currency_id:
            raise UserError(_("The clearing account has an incompatible currency."))

        # Elevated rights apply only after explicit authorization and company checks.
        Move = self.env["account.move"].sudo().with_company(company)
        move = Move.create({
            "move_type": "entry", "company_id": company.id,
            "journal_id": journal.id, "date": fields.Date.context_today(self),
            "ref": "%s / %s" % (self.name, bank_reference),
            "line_ids": [
                (0, 0, {"name": self.name, "account_id": clearing.id,
                        "debit": self.amount, "credit": 0.0}),
                (0, 0, {"name": self.name, "account_id": bank_account.id,
                        "debit": 0.0, "credit": self.amount}),
            ],
        })
        move.action_post()
        # Bypass this model's user-facing write gate only inside the trusted method.
        # The whole wizard call is one database transaction: failure rolls back both.
        super(FundTransferRequest, self).write({
            "sending_move_id": move.id,
            "state": "awaiting_receipt",
            "bank_reference": bank_reference,
            "sent_by_id": self.env.user.id,
            "sent_date": fields.Datetime.now(),
        })
        self.message_post(body=_(
            "Outgoing bank journal entry %s posted for transfer %s. "
            "Bank reference: %s. Receipt is still pending."
        ) % (move.name, self.name, bank_reference))
        return move

    def _check_receiving_finance(self):
        self.ensure_one()
        user = self.env.user
        if not user.has_group("bank_transfer_requests.group_branch_finance"):
            raise AccessError(_("Only Receiving Branch Finance can confirm receipt."))
        if self.destination_company_id not in user.btr_finance_branch_ids:
            raise AccessError(_("You are not assigned to the receiving branch."))
        if self.destination_company_id not in user.company_ids:
            raise AccessError(_("You do not have access to the receiving branch."))
   
    def _post_receiving_bank_entry(self, receipt_reference):
            """Post the receipt once, in the receiving company's journal."""
            self.ensure_one()
            self.env.cr.execute(
                "SELECT id FROM fund_transfer_request WHERE id = %s FOR UPDATE",
                (self.id,),
            )
            self.invalidate_recordset(["state", "sending_move_id", "receiving_move_id"])
            if self.state != "awaiting_receipt" or self.receiving_move_id:
                raise UserError(_("This transfer is not awaiting receipt or was already received."))
            self._check_receiving_finance()
            receipt_reference = (receipt_reference or "").strip()
            if not receipt_reference:
                raise UserError(_("A receipt reference is required."))
            if not self.sending_move_id or self.sending_move_id.state != "posted":
                raise UserError(_("The sending journal entry must be posted first."))
            self._check_transfer()
            self._check_transfer_direction()
            company = self.destination_company_id
            journal = self.destination_bank_journal_id.with_company(company)     
            if journal.type != "bank" or journal.company_id != company:
                raise UserError(_("The receiving bank must belong to the receiving company."))
            if self.source_company_id.currency_id != company.currency_id:
                raise UserError(_("Different company currencies are not supported."))
            bank_account = journal.default_account_id
            if not bank_account or company not in bank_account.company_ids:
                raise UserError(_("The receiving bank liquidity account is missing or unavailable."))
            Account = self.env["account.account"].sudo().with_company(company)
            clearing = Account.search([("code", "=", "101701")], limit=2).filtered(
                lambda a: company in a.company_ids
            )
            if len(clearing) != 1:
                raise UserError(_("Exactly one clearing account 101701 must be available to the receiving company."))
            clearing = clearing[0]
            if clearing == bank_account or clearing.account_type != "asset_current" or not clearing.reconcile:
                raise UserError(_("The receiving clearing account must be a distinct, reconcilable Current Assets account."))
            if clearing.currency_id and clearing.currency_id != company.currency_id:
                raise UserError(_("The clearing account currency is incompatible."))
            move = self.env["account.move"].sudo().with_company(company).create({
                "move_type": "entry", "company_id": company.id,
                "journal_id": journal.id, "date": fields.Date.context_today(self),
                "ref": "%s / Receipt: %s" % (self.name, receipt_reference),
                "line_ids": [
                    (0, 0, {"name": self.name, "account_id": bank_account.id,
                            "debit": self.amount, "credit": 0.0}),
                    (0, 0, {"name": self.name, "account_id": clearing.id,
                            "debit": 0.0, "credit": self.amount}),
                ],
            })
            move.action_post()
            super(FundTransferRequest, self).write({
                "receiving_move_id": move.id, "receipt_reference": receipt_reference,
                "received_by_id": self.env.user.id,
                "received_date": fields.Datetime.now(), "state": "completed",
            })
            self.message_post(body=_("Receipt confirmed by %s. Journal entry %s posted. Receipt reference: %s.") % (
                self.env.user.display_name, move.name, receipt_reference,
            ))
            return move
    
    def write(self, vals):
        immutable = {"company_id", "destination_company_id", "name"}
        if immutable.intersection(vals):
            raise AccessError(_("Request ownership and reference cannot be changed."))
        metadata = {"sending_move_id","receiving_move_id", "reject_reason", "approved_by_id", "approved_date",
                    "sent_by_id", "sent_date", "bank_reference",
                    "received_by_id", "received_date", "receipt_reference"}
       
        if "state" in vals:
            new_state = vals["state"]
            allowed_keys = {
                "pending": {"state"},
                "approved": {"state"},
                "rejected": {"state", "reject_reason"},
                "awaiting_receipt": {"state", "bank_reference"},
                "completed": {"state", "receipt_reference"},
            }
            if new_state not in allowed_keys or not set(vals) <= allowed_keys[new_state]:
                raise AccessError(_("Unauthorized state change or protected fields."))
            if new_state in ("awaiting_receipt", "completed") and len(self) != 1:
                raise UserError(_("Process one transfer at a time."))
            for rec in self:
                if rec.state == "draft" and new_state == "pending":
                    if not self.env.user.has_group("bank_transfer_requests.group_branch_user") or rec.company_id != self.env.company:
                        raise AccessError(_("Only the requesting Branch User may submit."))
                    rec._check_transfer()
                    rec._check_transfer_direction()
                elif rec.state == "pending" and new_state in ("approved", "rejected"):
                    rec._check_approver()
                    if new_state == "rejected" and not (vals.get("reject_reason") or "").strip():
                        raise UserError(_("A rejection reason is required."))
                elif rec.state == "approved" and new_state == "awaiting_receipt":
                    raise AccessError(_("Use Verify & Send to post the sending bank entry."))
                elif rec.state == "awaiting_receipt" and new_state == "completed":
                    rec._check_receiving_finance()
                    if not (vals.get("receipt_reference") or "").strip():
                        raise UserError(_("A receipt reference is required."))
                else:
                    raise AccessError(_("Invalid or unauthorized status transition."))
            vals = dict(vals)
            if new_state == "approved":
                vals["approved_by_id"] = self.env.user.id
                vals["approved_date"] = fields.Datetime.now()
            elif new_state == "awaiting_receipt":
                vals["sent_by_id"] = self.env.user.id
                vals["sent_date"] = fields.Datetime.now()
            elif new_state == "completed":
                vals["received_by_id"] = self.env.user.id
                vals["received_date"] = fields.Datetime.now()
            return super().write(vals)
        if metadata.intersection(vals):
            raise AccessError(_("Audit and decision fields are protected."))
        for rec in self:
            if rec.state != "draft":
                raise AccessError(_("Only draft requests can be edited."))
            if not self.env.user.has_group("bank_transfer_requests.group_branch_user") or rec.company_id != self.env.company:
                raise AccessError(_("Only the requesting Branch User may edit drafts."))
        return super().write(vals)

    def action_verify_send(self):
        self.ensure_one()
        if self.state != "approved":
            raise UserError(_("Only approved transfers can be sent."))
        self._check_approver()
        return {
            "type": "ir.actions.act_window", "name": _("Verify & Send"),
            "res_model": "btr.send.wizard", "view_mode": "form",
            "view_id": self.env.ref("bank_transfer_requests.view_btr_send_wizard_form").id,
            "target": "new", "context": {"default_request_id": self.id},
        }

    def action_confirm_receipt(self):
        self.ensure_one()
        if self.state != "awaiting_receipt":
            raise UserError(_("Only sent transfers can be confirmed."))
        self._check_receiving_finance()
        return {
            "type": "ir.actions.act_window", "name": _("Confirm Receipt"),
            "res_model": "btr.receipt.wizard", "view_mode": "form",
            "view_id": self.env.ref("bank_transfer_requests.view_btr_receipt_wizard_form").id,
            "target": "new", "context": {"default_request_id": self.id},
        }

    def _get_transfer_settings(self):
        settings = self.env["jasmar.bank.transfer.settings"].search(
            [], limit=1
        )

        if not settings:
            raise UserError(
                _("Please configure the Bank Transfer Settings first.")
            )

        return settings
    
    
    
    @api.constrains("source_company_id", "destination_company_id")
    def _check_transfer_direction(self):
        for rec in self:
            settings = rec._get_transfer_settings()

            parent = settings.parent_company_id
            hq = settings.hq_branch_id
            source = rec.source_company_id
            destination = rec.destination_company_id

            if source == destination:
                raise ValidationError(
                    _("Sending and receiving branches must be different.")
                )

            if destination == parent:
                raise ValidationError(
                    _("The parent organization cannot receive transfer requests.")
                )

            if destination == hq:
                raise ValidationError(
                    _("HQ cannot be a receiving branch.")
                )

            if source == parent:
                raise ValidationError(
                    _("The parent organization cannot send transfers.")
                )

            if source.parent_id != parent:
                raise ValidationError(
                    _("Sending branch must belong to the JASMAR organization.")
                )

            if destination.parent_id != parent:
                raise ValidationError(
                    _("Receiving branch must belong to the JASMAR organization.")
                )
                

    def _check_approver(self):
        self.ensure_one()

        settings = self._get_transfer_settings()
        user = self.env.user
        source_company = self.source_company_id

        if source_company == settings.hq_branch_id:
            if not user.has_group(
                "bank_transfer_requests.group_hq_finance"
            ):
                raise AccessError(
                    _("Only HQ Finance can approve HQ transfers.")
                )
        else:
            if not user.has_group(
                "bank_transfer_requests.group_branch_finance"
            ):
                raise AccessError(
                    _("Only Branch Finance can approve branch transfers.")
                )

        if source_company not in user.btr_finance_branch_ids:
            raise AccessError(
                _("You are not assigned as Finance for the sending branch.")
            )
        if source_company not in user.company_ids:
            raise AccessError(
                _("You do not have access to the sending branch.")
            )

    def action_submit(self):
        for rec in self:
            if rec.state != "draft":
                raise UserError(_("Only draft requests can be submitted."))

            if not self.env.user.has_group(
                "bank_transfer_requests.group_branch_user"
            ):
                raise AccessError(
                    _("Only Branch Users can submit requests.")
                )

            if rec.company_id != self.env.company:
                raise AccessError(
                    _("Select the requesting branch before submitting.")
                )

            if not rec.source_company_id or not rec.destination_bank_journal_id:
                raise UserError(
                    _("Please complete the transfer details.")
                )

            rec.write({"state": "pending"})


    def action_approve(self):
        for rec in self:
            if rec.state != "pending":
                raise UserError(
                    _("Only pending requests can be approved.")
                )

            rec._check_approver()
            rec.write({"state": "approved"})
            # Chatter audit is performed here; direct authorized RPC state
            # transitions are still possible and must be reviewed before production.
            rec.message_post(body=_("Bank transfer approved by %s.") % self.env.user.display_name)


    def action_reject(self):
        self.ensure_one()
        if self.state != "pending":
            raise UserError(_("Only pending requests can be rejected."))
        self._check_approver()
        return {
            "type": "ir.actions.act_window",
            "name": _("Reject Bank Transfer"),
            "res_model": "btr.reject.wizard",
            "view_mode": "form",
            "view_id": self.env.ref("bank_transfer_requests.view_btr_reject_wizard_form").id,
            "target": "new",
            "context": {"default_request_id": self.id},
        }
