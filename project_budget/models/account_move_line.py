# -*- coding: utf-8 -*-
# Budget achieved: analytic + product on posted journal lines (see budget.report SQL).

from odoo import _, api, fields, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    budget_line_id = fields.Many2one(
        "budget.line",
        string="Budget Line",
        ondelete="restrict",
        index=True,
        help="Select a budget line, or pick a product to find it automatically. "
             "Analytic account is filled from the budget line. Posting updates budget achieved.",
    )

    def _get_budget_line_search_domain_from_product(self, product, move_date, company, project=None):
        domain = [
            ("product_id", "=", product.id),
            ("budget_analytic_id.state", "in", ["confirmed", "done"]),
            ("budget_analytic_id.budget_type", "!=", "revenue"),
        ]
        if move_date:
            domain.extend([
                ("date_from", "<=", move_date),
                ("date_to", ">=", move_date),
            ])
        if company:
            domain.extend([
                "|", ("company_id", "=", False), ("company_id", "=", company.id),
            ])
        if project:
            domain.append(("budget_project_id", "=", project.id))
        return domain

    def _filter_budget_lines_by_analytic(self, budget_lines, analytic_distribution):
        if not analytic_distribution:
            return budget_lines
        account_ids = {int(account_id) for account_id in analytic_distribution}
        return budget_lines.filtered(
            lambda bl: bl._get_budget_line_analytic_account()
            and bl._get_budget_line_analytic_account().id in account_ids
        )

    def _find_budget_lines_for_product(
        self, product, move_date, company, analytic_distribution=None, project=None
    ):
        if not product:
            return self.env["budget.line"]
        domain = self._get_budget_line_search_domain_from_product(
            product, move_date, company, project
        )
        budget_lines = self.env["budget.line"].search(domain)
        return self._filter_budget_lines_by_analytic(budget_lines, analytic_distribution)

    def _find_budget_line_from_product(
        self, product, move_date, company, analytic_distribution=None, project=None
    ):
        budget_lines = self._find_budget_lines_for_product(
            product, move_date, company, analytic_distribution, project
        )
        return budget_lines if len(budget_lines) == 1 else self.env["budget.line"]

    def _resolve_budget_line_from_product(self, product, move, analytic_distribution=None):
        move_date = move.date or fields.Date.context_today(self)
        company = move.company_id or self.env.company
        return self._find_budget_line_from_product(
            product,
            move_date,
            company,
            analytic_distribution,
            move.project_id,
        )

    def _is_budget_impact_line(self):
        """True for the P&L / budget side. Counterpart (bank, cash, payable) is skipped."""
        self.ensure_one()
        if self.display_type in ("line_section", "line_note", "line_subsection"):
            return False
        if not (self.debit or self.credit):
            return False
        if self.budget_line_id or self.product_id or self.analytic_distribution:
            return True
        return self.account_id.internal_group in ("expense", "income")

    def _apply_budget_line_from_product(self, move, analytic_distribution=None):
        for line in self.filtered(
            lambda l: l.product_id
            and l.move_id.is_budget_journal
            and not l.budget_line_id
            and l.display_type not in ("line_section", "line_note", "line_subsection")
        ):
            budget_line = line._resolve_budget_line_from_product(
                line.product_id,
                move or line.move_id,
                analytic_distribution or line.analytic_distribution,
            )
            if budget_line:
                line.budget_line_id = budget_line
                line._apply_budget_line_distribution()

    def _get_budget_line_distribution_vals(self, budget_line):
        vals = {}
        acc = budget_line._get_budget_line_analytic_account()
        if acc:
            vals["analytic_distribution"] = {str(acc.id): 100.0}
        if budget_line.product_id:
            vals["product_id"] = budget_line.product_id.id
        return vals

    def _apply_budget_line_distribution(self):
        for line in self.filtered("budget_line_id"):
            line.update(line._get_budget_line_distribution_vals(line.budget_line_id))

    def _ensure_budget_analytic_100(self):
        """Force 100% analytic on the budget-impact line (from budget line or existing tag)."""
        for line in self.filtered(
            lambda l: l.move_id.is_budget_journal and l._is_budget_impact_line()
        ):
            if line.budget_line_id:
                line._apply_budget_line_distribution()
                continue
            dist = line.analytic_distribution or {}
            if len(dist) == 1:
                account_key = next(iter(dist))
                if dist[account_key] != 100.0:
                    line.analytic_distribution = {account_key: 100.0}

    def _validate_analytic_distribution(self):
        counterparts = self.filtered(
            lambda l: l.move_id.is_budget_journal and not l._is_budget_impact_line()
        )
        return super(
            AccountMoveLine, self - counterparts
        )._validate_analytic_distribution()

    def _compute_has_invalid_analytics(self):
        counterparts = self.filtered(
            lambda l: l.move_id.is_budget_journal and not l._is_budget_impact_line()
        )
        counterparts.has_invalid_analytics = False
        super(AccountMoveLine, self - counterparts)._compute_has_invalid_analytics()

    @api.onchange("budget_line_id")
    def _onchange_budget_line_id(self):
        if self.budget_line_id:
            for key, value in self._get_budget_line_distribution_vals(self.budget_line_id).items():
                setattr(self, key, value)
        elif not self.expense_id and not self.product_id:
            self.analytic_distribution = False

    @api.onchange("product_id")
    def _onchange_product_id_budget_line(self):
        if not self.product_id or not self.move_id.is_budget_journal:
            return
        if self.budget_line_id and self.budget_line_id.product_id == self.product_id:
            return
        move_date = self.move_id.date or fields.Date.context_today(self)
        company = self.move_id.company_id or self.env.company
        budget_lines = self._find_budget_lines_for_product(
            self.product_id,
            move_date,
            company,
            self.analytic_distribution,
            self.move_id.project_id,
        )
        if len(budget_lines) == 1:
            self.budget_line_id = budget_lines
            for key, value in self._get_budget_line_distribution_vals(budget_lines).items():
                if key != "product_id":
                    setattr(self, key, value)
            return
        self.budget_line_id = False
        if not budget_lines:
            return {
                "warning": {
                    "title": _("No Budget Line"),
                    "message": _(
                        "No open budget line found for product «%(product)s»%(project)s on %(date)s. "
                        "Select a budget line manually or check the budget setup.",
                        product=self.product_id.display_name,
                        project=(
                            _(" for project «%s»") % self.move_id.project_id.display_name
                            if self.move_id.project_id
                            else ""
                        ),
                        date=move_date,
                    ),
                },
            }
        return {
            "domain": {"budget_line_id": [("id", "in", budget_lines.ids)]},
            "warning": {
                "title": _("Multiple Budget Lines"),
                "message": _(
                    "Several budget lines match product «%(product)s». "
                    "Pick the correct budget line.",
                    product=self.product_id.display_name,
                ),
            },
        }

    def _prepare_budget_vals_from_product(self, vals, move):
        if vals.get("budget_line_id") or not vals.get("product_id") or not move.is_budget_journal:
            return vals
        product = self.env["product.product"].browse(vals["product_id"])
        budget_line = self._find_budget_line_from_product(
            product,
            move.date or fields.Date.context_today(self),
            move.company_id or self.env.company,
            vals.get("analytic_distribution"),
            move.project_id,
        )
        if budget_line:
            vals["budget_line_id"] = budget_line.id
            for key, value in self._get_budget_line_distribution_vals(budget_line).items():
                vals.setdefault(key, value)
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        moves = {}
        for vals in vals_list:
            if vals.get("expense_id") and not vals.get("product_id"):
                expense = self.env["hr.expense"].browse(vals["expense_id"])
                if expense.exists() and expense.product_id:
                    vals["product_id"] = expense.product_id.id
            move = moves.get(vals.get("move_id"))
            if move is None and vals.get("move_id"):
                move = self.env["account.move"].browse(vals["move_id"])
                moves[vals["move_id"]] = move
            if move:
                vals = self._prepare_budget_vals_from_product(vals, move)
            if vals.get("budget_line_id"):
                budget_line = self.env["budget.line"].browse(vals["budget_line_id"])
                for key, value in self._get_budget_line_distribution_vals(budget_line).items():
                    vals.setdefault(key, value)
        return super().create(vals_list)

    def write(self, vals):
        vals = dict(vals)
        if vals.get("expense_id") and not vals.get("product_id"):
            expense = self.env["hr.expense"].browse(vals["expense_id"])
            if expense.exists() and expense.product_id:
                vals["product_id"] = expense.product_id.id
        res = super().write(vals)
        if "budget_line_id" in vals:
            self.filtered("budget_line_id")._apply_budget_line_distribution()
        elif vals.get("product_id"):
            self._apply_budget_line_from_product(self.move_id)
        return res

    def _prepare_analytic_distribution_line(self, distribution, account_ids, distribution_on_each_plan):
        vals = super()._prepare_analytic_distribution_line(
            distribution, account_ids, distribution_on_each_plan
        )
        if not vals.get("product_id"):
            product = self.product_id
            if not product and self.expense_id:
                product = self.expense_id.product_id
            if not product and self.budget_line_id and self.budget_line_id.product_id:
                product = self.budget_line_id.product_id
            if product:
                vals["product_id"] = product.id
        return vals
