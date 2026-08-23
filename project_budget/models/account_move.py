# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = "account.move"

    is_budget_journal = fields.Boolean(
        string="Budget Journal Entry",
        default=False,
        help="When enabled, journal items show Budget Line and posting validates against budget.",
        copy=False,
    )
    project_id = fields.Many2one(
        "project.project",
        string="Project",
        ondelete="restrict",
        index=True,
        copy=True,
        help="Limits Budget Line options and product auto-fill to this project's budget.",
    )

    @api.onchange("project_id")
    def _onchange_project_id_budget_lines(self):
        if not self.is_budget_journal:
            return
        for line in self.line_ids:
            if line.display_type in ("line_section", "line_note", "line_subsection"):
                continue
            if (
                line.budget_line_id
                and self.project_id
                and line.budget_line_id.budget_project_id
                and line.budget_line_id.budget_project_id != self.project_id
            ):
                line.budget_line_id = False
            if line.product_id and not line.budget_line_id:
                budget_line = line._resolve_budget_line_from_product(
                    line.product_id, self, line.analytic_distribution
                )
                if budget_line:
                    line.budget_line_id = budget_line
                    line._apply_budget_line_distribution()

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        if self.env.context.get("default_is_budget_journal"):
            defaults["is_budget_journal"] = True
        return defaults

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if (
                self.env.context.get("default_is_budget_journal")
                and vals.get("move_type", "entry") == "entry"
                and "is_budget_journal" not in vals
            ):
                vals["is_budget_journal"] = True
        return super().create(vals_list)

    def _check_budget_lines_before_post(self):
        for move in self.filtered(
            lambda m: m.move_type == "entry" and m.is_budget_journal
        ):
            move_date = move.date or move.invoice_date
            move.line_ids._apply_budget_line_from_product(move)
            for line in move.line_ids.filtered("budget_line_id"):
                if line.display_type in ("line_section", "line_note", "line_subsection"):
                    continue
                line._apply_budget_line_distribution()
            move.line_ids._ensure_budget_analytic_100()
            impact_lines = move.line_ids.filtered(lambda l: l._is_budget_impact_line())
            if not impact_lines:
                raise UserError(
                    _(
                        "Set a product or budget line on the expense/income item. "
                        "The counterpart (bank, cash, payable) does not need a budget line."
                    )
                )
            for line in impact_lines.filtered(lambda l: not l.budget_line_id):
                if line.product_id:
                    raise UserError(
                        _(
                            "No budget line found for product «%(product)s» on journal item «%(label)s». "
                            "Select a budget line manually.",
                            product=line.product_id.display_name,
                            label=line.name or line.account_id.display_name,
                        )
                    )
                raise UserError(
                    _(
                        "Budget journal item «%(label)s» has no budget line. "
                        "Select a product or budget line on this line. "
                        "The counterpart account does not need one.",
                        label=line.name or line.account_id.display_name,
                    )
                )
            for line in move.line_ids.filtered("budget_line_id"):
                if line.display_type in ("line_section", "line_note", "line_subsection"):
                    continue
                amount = line.debit or line.credit
                if not amount:
                    continue
                budget = line.budget_line_id
                if move_date and (
                    move_date < budget.date_from or move_date > budget.date_to
                ):
                    raise UserError(
                        _(
                            "Journal date %(date)s is outside budget line «%(line)s» "
                            "(%(start)s → %(end)s)."
                        )
                        % {
                            "date": move_date,
                            "line": budget.display_name,
                            "start": budget.date_from,
                            "end": budget.date_to,
                        }
                    )
                budget.invalidate_recordset(
                    ["committed_amount", "achieved_amount", "balance"]
                )
                budget._compute_all()
                balance = budget.balance or 0.0
                if amount > balance:
                    currency = budget.budget_display_currency_id or move.company_currency_id
                    raise UserError(
                        _(
                            "Budget exceeded for «%(line)s». "
                            "Available: %(balance).2f %(currency)s. "
                            "Journal line amount: %(amount).2f %(currency)s."
                        )
                        % {
                            "line": budget.display_name,
                            "balance": balance,
                            "amount": amount,
                            "currency": currency.name,
                        }
                    )

    def action_post(self):
        self._check_budget_lines_before_post()
        return super().action_post()
