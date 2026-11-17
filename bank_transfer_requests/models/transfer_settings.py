from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class BankTransferSettings(models.Model):
    _name = "jasmar.bank.transfer.settings"
    _description = "Bank Transfer Settings"

    name = fields.Char(default="JASMAR Transfer Configuration", required=True)
    parent_company_id = fields.Many2one("res.company", string="Parent Organization", required=True)
    hq_branch_id = fields.Many2one("res.company", string="HQ Branch", required=True)
    branch_accounting_ids = fields.One2many(
        "jasmar.bank.transfer.branch.accounting", "settings_id",
        string="Branch Accounting Configuration",
    )


class BankTransferBranchAccounting(models.Model):
    _name = "jasmar.bank.transfer.branch.accounting"
    _description = "Bank Transfer Branch Accounting Configuration"
    _rec_name = "branch_id"
    _order = "branch_id"

    settings_id = fields.Many2one(
        "jasmar.bank.transfer.settings", required=True, ondelete="cascade",
    )
    branch_id = fields.Many2one("res.company", string="Branch", required=True)
    clearing_account_id = fields.Many2one(
        "account.account", string="Interbranch Clearing Account", required=True,
        help="Use an appropriate interbranch receivable/payable or clearing account."
    )
    transfer_journal_id = fields.Many2one(
        "account.journal", string="Transfer Journal", required=False,
        domain="[('company_id', '=', branch_id), ('type', '=', 'general')]",
        help="Optional legacy miscellaneous journal; Step 4.2 posts through the selected sending bank journal."
    )

    @api.constrains("settings_id", "branch_id", "transfer_journal_id")
    def _check_branch_configuration(self):
        for rec in self:
            if rec.settings_id and rec.branch_id:
                if rec.branch_id.parent_id != rec.settings_id.parent_company_id:
                    raise ValidationError(_("The configured branch must be a direct child of the parent organization."))
            if rec.transfer_journal_id and rec.transfer_journal_id.company_id != rec.branch_id:
                raise ValidationError(_("The transfer journal must belong to the configured branch."))
            if rec.transfer_journal_id and rec.transfer_journal_id.type != "general":
                raise ValidationError(_("The transfer journal must be a Miscellaneous journal."))
            if rec.settings_id and rec.branch_id:
                duplicate = self.search_count([
                    ("settings_id", "=", rec.settings_id.id),
                    ("branch_id", "=", rec.branch_id.id),
                    ("id", "!=", rec.id),
                ])
                if duplicate:
                    raise ValidationError(_("Configure each branch only once per settings record."))
