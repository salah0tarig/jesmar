# -*- coding: utf-8 -*-

from collections import defaultdict
import json

from odoo import api, fields, models, _
from odoo.fields import Domain


class ProjectProject(models.Model):
    _inherit = 'project.project'

    outcome_ids = fields.Many2many(
        'account.analytic.account',
        compute='_compute_outcome_ids',
        string='Outcomes',
    )

    @api.depends('account_id', 'account_id.child_ids')
    def _compute_outcome_ids(self):
        for project in self:
            if project.account_id:
                project.outcome_ids = project.account_id.child_ids
            else:
                project.outcome_ids = self.env['account.analytic.account']

    def _get_budget_analytic_account_domain(self):
        """Override: use child_of to include Outcome/Output analytic accounts (descendants)."""
        if not self.account_id:
            return Domain([])
        plan_col = self.account_id.plan_id._column_name()
        return Domain([(plan_col, 'child_of', self.account_id.id)])

    def _compute_budget(self):
        """Override: aggregate budget from project + Outcome + Output accounts (child_of)."""
        budget_items_by_project = defaultdict(lambda: {
            'budget_amount': 0,
            'budget_amount_for_progress': 0,
            'achieved_amount_for_progress': 0,
        })
        for project in self:
            if not project.account_id:
                continue
            plan_col = project.account_id.plan_id._column_name()
            budget_items = self.env['budget.line'].sudo()._read_group(
                [(plan_col, 'child_of', project.account_id.id)],
                groupby=['account_id', 'budget_analytic_id'],
                aggregates=['budget_amount:sum', 'achieved_amount:sum'],
            )
            for _analytic_account, budget_analytic_id, budget_amount_sum, achieved_amount_sum in budget_items:
                type_factor = -1 if budget_analytic_id.budget_type == 'expense' else 1
                budget_items_by_project[project.id]["budget_amount"] += budget_amount_sum
                budget_items_by_project[project.id]["budget_amount_for_progress"] += budget_amount_sum * type_factor
                budget_items_by_project[project.id]["achieved_amount_for_progress"] += achieved_amount_sum * type_factor

        for project in self:
            if not project.account_id:
                project.total_budget_amount = 0
                project.total_budget_progress = 0
                continue
            data = budget_items_by_project[project.id]
            total_budget_amount_fp = data['budget_amount_for_progress']
            total_achieved_amount_fp = data['achieved_amount_for_progress']
            project.total_budget_progress = total_budget_amount_fp and (
                total_achieved_amount_fp - total_budget_amount_fp
            ) / abs(total_budget_amount_fp)
            project.total_budget_amount = data['budget_amount']

    def action_view_budget_lines(self, domain=None):
        """Override: use child_of to include Outcome/Output budget lines. Opens budget lines list."""
        self.ensure_one()
        if not self.account_id:
            return {}
        plan_col = self.account_id.plan_id._column_name()
        budget_domain = Domain.AND([
            [(plan_col, 'child_of', self.account_id.id), ('budget_analytic_id.state', 'in', ['confirmed', 'done'])],
            domain or [],
        ])
        budget_lines = self.env['budget.line'].search(budget_domain)
        if not budget_lines:
            # No budget lines: offer to create budget for this project
            return {
                "type": "ir.actions.act_window",
                "res_model": "budget.analytic",
                "view_mode": "list,form",
                "context": {
                    'default_project_id': self.id,
                },
                "name": _("Budgets"),
                "domain": [('project_id', '=', self.id)],
            }
        # Open budget lines analysis for this project
        return {
            "type": "ir.actions.act_window",
            "res_model": "budget.line",
            "view_mode": "list,pivot,graph",
            "context": {'search_default_budget_analytic_id': budget_lines.budget_analytic_id.ids[:1]},
            "name": _("Budget Lines"),
            "domain": budget_domain,
        }

    def _get_budget_items(self, with_action=True):
        """Override: use child_of for Outcome/Output hierarchy."""
        self.ensure_one()
        if not self.account_id:
            return
        plan_col = self.account_id.plan_id._column_name()
        budget_lines = self.env['budget.line'].sudo()._read_group(
            [
                (plan_col, 'child_of', self.account_id.id),
                ('budget_analytic_id', '!=', False),
                ('budget_analytic_id.state', 'in', ['confirmed', 'done']),
            ],
            ['budget_analytic_id', 'company_id'],
            ['budget_amount:sum', 'achieved_amount:sum', 'id:array_agg'],
        )
        has_company_access = False
        for line in budget_lines:
            if line[1].id in self.env.context.get('allowed_company_ids', []):
                has_company_access = True
                break
        total_allocated = total_spent = 0.0
        total_allocated_for_progress = total_spent_for_progress = 0.0
        can_see_budget_items = with_action and has_company_access and (
            self.env.user.has_group('account.group_account_readonly')
            or self.env.user.has_group('analytic.group_analytic_accounting')
        )
        budget_data_per_budget = defaultdict(
            lambda: {
                'allocated': 0,
                'spent': 0,
                'budget_type': False,
                **({
                    'ids': [],
                    'budgets': [],
                } if can_see_budget_items else {})
            }
        )

        for budget_analytic, _dummy, allocated, spent, ids in budget_lines:
            budget_data = budget_data_per_budget[budget_analytic]
            budget_data['id'] = budget_analytic.id
            budget_data['name'] = budget_analytic.display_name
            budget_data['allocated'] += allocated
            budget_data['spent'] += spent
            budget_data['budget_type'] = budget_analytic.budget_type
            total_allocated += allocated
            total_spent += spent
            total_allocated_for_progress += allocated * -1 if budget_analytic.budget_type == 'expense' else allocated
            total_spent_for_progress += spent * -1 if budget_analytic.budget_type == 'expense' else spent

            if can_see_budget_items:
                budget_item = {
                    'id': budget_analytic.id,
                    'name': budget_analytic.display_name,
                    'allocated': allocated,
                    'spent': spent,
                    'budget_type': budget_analytic.budget_type,
                    'progress': allocated and (spent - allocated) / abs(allocated) * (-1 if budget_analytic.budget_type == 'expense' else 1),
                }
                budget_data['budgets'].append(budget_item)
                budget_data['ids'] += ids
            else:
                budget_data['budgets'] = []

        for budget_data in budget_data_per_budget.values():
            budget_data['progress'] = budget_data['allocated'] and (budget_data['spent'] - budget_data['allocated']) / abs(budget_data['allocated']) \
                * (-1 if budget_data['budget_type'] == 'expense' else 1)

        budget_data_per_budget = list(budget_data_per_budget.values())
        if can_see_budget_items:
            for budget_data in budget_data_per_budget:
                if len(budget_data['budgets']) == 1:
                    budget_data['budgets'].clear()
                budget_data['action'] = {
                    'name': 'action_view_budget_lines',
                    'type': 'object',
                    'args': json.dumps([[('id', 'in', budget_data.pop('ids'))]]),
                }

        can_add_budget = with_action and self.env.user.has_group('account.group_account_user')
        budget_items = {
            'data': budget_data_per_budget,
            'total': {
                'allocated': total_allocated,
                'spent': total_spent,
                'progress': (total_spent_for_progress - total_allocated_for_progress) / abs(total_allocated_for_progress) if total_allocated_for_progress else 0,
            },
            'can_add_budget': can_add_budget,
        }
        if can_add_budget:
            budget_items['form_view_id'] = self.env.ref('project_account_budget.view_budget_analytic_form_dialog').id
            budget_items['company_id'] = self.company_id.id or self.env.company.id
        return budget_items
