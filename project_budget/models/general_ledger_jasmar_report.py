# -*- coding: utf-8 -*-
from collections import defaultdict

from odoo import fields, models, _
from odoo.fields import Domain
from odoo.tools import float_is_zero


class AccountGeneralLedgerJasmarReportHandler(models.AbstractModel):
    _name = "account.general.ledger.jasmar.report.handler"
    _inherit = ["account.report.custom.handler"]
    _description = "General Ledger Jasmer Custom Handler"

    # -------------------------------------------------------------------------
    # Options / filters
    # -------------------------------------------------------------------------

    def _custom_options_initializer(self, report, options, previous_options):
        super()._custom_options_initializer(report, options, previous_options=previous_options)

        for key in (
            "jasmar_project_ids",
            "jasmar_outcome_ids",
            "jasmar_output_ids",
            "jasmar_activity_ids",
        ):
            raw = previous_options.get(key) or []
            options[key] = [int(x) for x in raw]

        # Hide currency column when user has no multi-currency (same as standard GL)
        if not self.env.user.has_group("base.group_multi_currency"):
            options["columns"] = [
                col for col in options["columns"] if col["expression_label"] != "amount_currency"
            ]

        options["custom_display_config"] = {
            **(options.get("custom_display_config") or {}),
            "css_custom_class": "general_ledger_jasmar",
            "components": {
                "AccountReportFilters": "GeneralLedgerJasmarFilters",
            },
        }

        # Hierarchy filter is optional and must NOT fill the standard Analytic chips.
        # - nothing selected → show ALL journal items (like standard GL)
        # - Project/Outcome/Output/Activity selected → restrict via forced_domain only
        activity_ids = self._get_filtered_activity_ids(options)
        if activity_ids is not None:
            forced = list(options.get("forced_domain") or [])
            if not activity_ids:
                forced.append(("id", "=", 0))
            else:
                forced.append(("analytic_distribution", "in", activity_ids))
            options["forced_domain"] = forced


    def _has_jasmar_hierarchy_filter(self, options):
        return bool(
            options.get("jasmar_project_ids")
            or options.get("jasmar_outcome_ids")
            or options.get("jasmar_output_ids")
            or options.get("jasmar_activity_ids")
        )

    def _get_filtered_activity_ids(self, options):
        """Return activity AA ids from Project>Outcome>Output>Activity filters.

        ``None`` means no hierarchy filter applied → do not restrict the dataset.
        """
        if not self._has_jasmar_hierarchy_filter(options):
            return None

        Analytic = self.env["account.analytic.account"]
        if options.get("jasmar_activity_ids"):
            return Analytic.browse(options["jasmar_activity_ids"]).ids
        if options.get("jasmar_output_ids"):
            return Analytic.search(
                [
                    ("id", "child_of", options["jasmar_output_ids"]),
                    ("account_level", "=", "activity"),
                ]
            ).ids
        if options.get("jasmar_outcome_ids"):
            return Analytic.search(
                [
                    ("id", "child_of", options["jasmar_outcome_ids"]),
                    ("account_level", "=", "activity"),
                ]
            ).ids
        # Project only
        return Analytic.search(
            [
                ("id", "child_of", options["jasmar_project_ids"]),
                ("account_level", "=", "activity"),
            ]
        ).ids

    # -------------------------------------------------------------------------
    # Hierarchy helpers
    # -------------------------------------------------------------------------

    def _analytic_ids_from_distribution(self, distribution):
        ids = []
        for key in distribution or {}:
            for part in str(key).split(","):
                part = part.strip()
                if part.isdigit():
                    ids.append(int(part))
        return ids

    def _resolve_hierarchy(self, analytic, cache):
        """Walk parents → (project, outcome, output, activity)."""
        if not analytic:
            return False, False, False, False
        if analytic.id in cache:
            return cache[analytic.id]

        project = outcome = output = activity = self.env["account.analytic.account"]
        current = analytic
        # Prefer deepest known levels while walking up
        chain = []
        while current:
            chain.append(current)
            current = current.parent_id

        for acc in reversed(chain):
            level = acc.account_level
            if level == "project" or acc.project_ids:
                project = acc
            elif level == "outcome":
                outcome = acc
            elif level == "output":
                output = acc
            elif level == "activity":
                activity = acc

        # If levels missing, map by depth from root
        if not activity and analytic:
            activity = analytic
        if chain and not project:
            project = chain[-1]
        if len(chain) >= 2 and not outcome:
            outcome = chain[-2] if chain[-2] != project else self.env["account.analytic.account"]
        if len(chain) >= 3 and not output:
            output = chain[-3] if chain[-3] not in (project, outcome) else self.env["account.analytic.account"]

        result = (project, outcome, output, activity)
        cache[analytic.id] = result
        return result

    def _pick_activity_analytic(self, aml, analytics_by_id, cache):
        aa_ids = self._analytic_ids_from_distribution(aml.analytic_distribution)
        if not aa_ids:
            return self.env["account.analytic.account"]
        accounts = [analytics_by_id[i] for i in aa_ids if i in analytics_by_id]
        if not accounts:
            return self.env["account.analytic.account"]
        # Prefer explicit activity level, else deepest (most parents)
        for acc in accounts:
            if acc.account_level == "activity":
                return acc
        return max(accounts, key=lambda a: (a.parent_path or "").count("/"))

    # -------------------------------------------------------------------------
    # Lines
    # -------------------------------------------------------------------------

    def _dynamic_lines_generator(
        self, report, options, all_column_groups_expression_totals, warnings=None
    ):
        amls = self._query_amls(report, options)
        tree = self._build_tree(amls)
        lines = self._render_tree_lines(report, options, tree)
        return [(0, line) for line in lines]

    def _query_amls(self, report, options):
        """Same date scope as standard General Ledger: from beginning until date_to.

        ``strict_range`` only returns lines inside the month, so periods like Nov 2026
        look empty while GL still shows opening balances / prior activity.
        """
        options_date_from = fields.Date.from_string(options["date"]["date_from"])
        fiscalyear_date_from = self.env.company.compute_fiscalyear_dates(options_date_from)[
            "date_from"
        ]
        # Mirror GL: keep BS accounts from the start; P&L only from fiscal year start
        additional_domain = Domain(
            [
                "|",
                ("account_id.include_initial_balance", "=", True),
                ("date", ">=", fiscalyear_date_from),
            ]
        )
        domain = report._get_options_domain(options, "from_beginning") & additional_domain
        return self.env["account.move.line"].search(domain, order="date asc, id asc")

    def _build_tree(self, amls):
        """
        Nested dict:
        project_id -> outcome_id -> output_id -> activity_id -> aml recordset
        Missing parents use 0 as key (No Project / …).
        """
        Analytic = self.env["account.analytic.account"]
        all_aa_ids = set()
        for aml in amls:
            all_aa_ids.update(self._analytic_ids_from_distribution(aml.analytic_distribution))
        analytics_by_id = {a.id: a for a in Analytic.browse(list(all_aa_ids))}
        cache = {}

        tree = defaultdict(
            lambda: defaultdict(
                lambda: defaultdict(lambda: defaultdict(lambda: self.env["account.move.line"]))
            )
        )
        names = {
            "project": {},
            "outcome": {},
            "output": {},
            "activity": {},
        }

        for aml in amls:
            activity = self._pick_activity_analytic(aml, analytics_by_id, cache)
            project, outcome, output, activity = self._resolve_hierarchy(activity, cache)

            p_id = project.id if project else 0
            o_id = outcome.id if outcome else 0
            u_id = output.id if output else 0
            a_id = activity.id if activity else 0

            if project:
                names["project"][p_id] = project.display_name
            if outcome:
                names["outcome"][o_id] = outcome.display_name
            if output:
                names["output"][u_id] = output.display_name
            if activity:
                names["activity"][a_id] = activity.display_name

            tree[p_id][o_id][u_id][a_id] |= aml

        return {"tree": tree, "names": names}

    def _sum_amls(self, amls):
        debit = sum(amls.mapped("debit"))
        credit = sum(amls.mapped("credit"))
        return debit, credit, debit - credit

    def _column_values(
        self,
        options,
        debit,
        credit,
        balance,
        date=None,
        partner_name=None,
        label=None,
        amount_currency=None,
        currency=None,
    ):
        col_values = {}
        for col in options["columns"]:
            label_key = col["expression_label"]
            if label_key == "date":
                col_values[label_key] = date
            elif label_key == "partner_name":
                col_values[label_key] = partner_name
            elif label_key == "name":
                col_values[label_key] = label
            elif label_key == "amount_currency":
                col_values[label_key] = amount_currency
            elif label_key == "debit":
                col_values[label_key] = debit
            elif label_key == "credit":
                col_values[label_key] = credit
            elif label_key == "balance":
                col_values[label_key] = balance
            else:
                col_values[label_key] = None
        return col_values, currency

    def _build_line(
        self,
        report,
        options,
        *,
        name,
        level,
        parent_id,
        line_id,
        debit,
        credit,
        balance,
        unfoldable=False,
        unfolded=False,
        caret_options=False,
        date=None,
        partner_name=None,
        label=None,
        amount_currency=None,
        currency=None,
        markup=None,
    ):
        columns = []
        col_values, line_currency = self._column_values(
            options,
            debit,
            credit,
            balance,
            date=date,
            partner_name=partner_name,
            label=label,
            amount_currency=amount_currency,
            currency=currency,
        )
        for col in options["columns"]:
            expr = col["expression_label"]
            value = col_values.get(expr)
            kwargs = {"options": options}
            if expr == "amount_currency" and line_currency:
                kwargs["currency"] = line_currency
            columns.append(report._build_column_dict(value, col, **kwargs))

        return {
            "id": line_id,
            "name": name,
            "level": level,
            "parent_id": parent_id,
            "columns": columns,
            "unfoldable": unfoldable,
            "unfolded": unfolded,
            "caret_options": caret_options,
        }

    def _is_unfolded(self, options, line_id):
        return options.get("unfold_all") or line_id in (options.get("unfolded_lines") or [])

    def _render_tree_lines(self, report, options, packed):
        tree = packed["tree"]
        names = packed["names"]
        lines = []
        company_currency = self.env.company.currency_id

        # Grand total of everything shown
        all_amls = self.env["account.move.line"]
        for outcomes in tree.values():
            for outputs in outcomes.values():
                for activities in outputs.values():
                    for amls in activities.values():
                        all_amls |= amls

        for p_id in sorted(tree.keys(), key=lambda i: (i == 0, names["project"].get(i, ""))):
            project_amls = self.env["account.move.line"]
            for outputs in tree[p_id].values():
                for activities in outputs.values():
                    for amls in activities.values():
                        project_amls |= amls
            p_debit, p_credit, p_balance = self._sum_amls(project_amls)
            p_name = names["project"].get(p_id) or _("No Project")
            p_line_id = report._get_generic_line_id(
                "account.analytic.account" if p_id else None,
                p_id or None,
                markup="jasmar_project",
            )
            p_unfolded = self._is_unfolded(options, p_line_id)
            # Always emit full tree; UI hides children of folded parents.
            lines.append(
                self._build_line(
                    report,
                    options,
                    name=_("Project: %s", p_name),
                    level=1,
                    parent_id=None,
                    line_id=p_line_id,
                    debit=p_debit,
                    credit=p_credit,
                    balance=p_balance,
                    unfoldable=True,
                    unfolded=p_unfolded,
                )
            )

            for o_id in sorted(
                tree[p_id].keys(), key=lambda i: (i == 0, names["outcome"].get(i, ""))
            ):
                outcome_amls = self.env["account.move.line"]
                for activities in tree[p_id][o_id].values():
                    for amls in activities.values():
                        outcome_amls |= amls
                o_debit, o_credit, o_balance = self._sum_amls(outcome_amls)
                o_name = names["outcome"].get(o_id) or _("No Outcome")
                o_line_id = report._get_generic_line_id(
                    "account.analytic.account" if o_id else None,
                    o_id or None,
                    markup="jasmar_outcome",
                    parent_line_id=p_line_id,
                )
                o_unfolded = self._is_unfolded(options, o_line_id)
                lines.append(
                    self._build_line(
                        report,
                        options,
                        name=_("Outcome: %s", o_name),
                        level=2,
                        parent_id=p_line_id,
                        line_id=o_line_id,
                        debit=o_debit,
                        credit=o_credit,
                        balance=o_balance,
                        unfoldable=True,
                        unfolded=o_unfolded,
                    )
                )

                for u_id in sorted(
                    tree[p_id][o_id].keys(),
                    key=lambda i: (i == 0, names["output"].get(i, "")),
                ):
                    output_amls = self.env["account.move.line"]
                    for amls in tree[p_id][o_id][u_id].values():
                        output_amls |= amls
                    u_debit, u_credit, u_balance = self._sum_amls(output_amls)
                    u_name = names["output"].get(u_id) or _("No Output")
                    u_line_id = report._get_generic_line_id(
                        "account.analytic.account" if u_id else None,
                        u_id or None,
                        markup="jasmar_output",
                        parent_line_id=o_line_id,
                    )
                    u_unfolded = self._is_unfolded(options, u_line_id)
                    lines.append(
                        self._build_line(
                            report,
                            options,
                            name=_("Output: %s", u_name),
                            level=3,
                            parent_id=o_line_id,
                            line_id=u_line_id,
                            debit=u_debit,
                            credit=u_credit,
                            balance=u_balance,
                            unfoldable=True,
                            unfolded=u_unfolded,
                        )
                    )

                    for a_id in sorted(
                        tree[p_id][o_id][u_id].keys(),
                        key=lambda i: (i == 0, names["activity"].get(i, "")),
                    ):
                        activity_amls = tree[p_id][o_id][u_id][a_id]
                        a_debit, a_credit, a_balance = self._sum_amls(activity_amls)
                        a_name = names["activity"].get(a_id) or _("No Activity")
                        a_line_id = report._get_generic_line_id(
                            "account.analytic.account" if a_id else None,
                            a_id or None,
                            markup="jasmar_activity",
                            parent_line_id=u_line_id,
                        )
                        a_unfolded = self._is_unfolded(options, a_line_id)
                        lines.append(
                            self._build_line(
                                report,
                                options,
                                name=_("Activity: %s", a_name),
                                level=4,
                                parent_id=u_line_id,
                                line_id=a_line_id,
                                debit=a_debit,
                                credit=a_credit,
                                balance=a_balance,
                                unfoldable=True,
                                unfolded=a_unfolded,
                            )
                        )

                        date_from = fields.Date.from_string(options["date"]["date_from"])
                        initial_amls = activity_amls.filtered(lambda l: l.date < date_from)
                        period_amls = activity_amls.filtered(lambda l: l.date >= date_from)
                        running = 0.0
                        if initial_amls:
                            i_debit, i_credit, i_balance = self._sum_amls(initial_amls)
                            running = i_balance
                            init_line_id = report._get_generic_line_id(
                                None,
                                None,
                                markup=f"jasmar_initial_{a_id}",
                                parent_line_id=a_line_id,
                            )
                            lines.append(
                                self._build_line(
                                    report,
                                    options,
                                    name=_("Initial Balance"),
                                    level=5,
                                    parent_id=a_line_id,
                                    line_id=init_line_id,
                                    debit=i_debit,
                                    credit=i_credit,
                                    balance=running,
                                    unfoldable=False,
                                )
                            )
                        for aml in period_amls:
                            running += aml.balance
                            aml_line_id = report._get_generic_line_id(
                                "account.move.line",
                                aml.id,
                                parent_line_id=a_line_id,
                            )
                            move_name = aml.move_id.display_name or aml.move_name or ""
                            lines.append(
                                self._build_line(
                                    report,
                                    options,
                                    name=f"{move_name} - {aml.name or aml.ref or ''}",
                                    level=5,
                                    parent_id=a_line_id,
                                    line_id=aml_line_id,
                                    debit=aml.debit,
                                    credit=aml.credit,
                                    balance=running,
                                    unfoldable=False,
                                    date=aml.date,
                                    partner_name=aml.partner_id.display_name if aml.partner_id else "",
                                    amount_currency=aml.amount_currency,
                                    currency=aml.currency_id,
                                    caret_options="account.move.line",
                                )
                            )

        # Report total
        t_debit, t_credit, t_balance = self._sum_amls(all_amls)
        if not float_is_zero(t_debit, precision_rounding=company_currency.rounding) or not float_is_zero(
            t_credit, precision_rounding=company_currency.rounding
        ):
            total_id = report._get_generic_line_id(None, None, markup="jasmar_total")
            lines.append(
                self._build_line(
                    report,
                    options,
                    name=_("Total"),
                    level=0,
                    parent_id=None,
                    line_id=total_id,
                    debit=t_debit,
                    credit=t_credit,
                    balance=t_balance,
                    unfoldable=False,
                )
            )
        return lines

    def open_journal_items(self, options, params):
        report = self.env["account.report"].browse(options["report_id"])
        return report.open_journal_items(options, params)
