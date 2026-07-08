# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class AccountAnalyticAccount(models.Model):
    _inherit = 'account.analytic.account'
    _order = 'parent_path, name, id'
    _parent_name = 'parent_id'
    _parent_store = True

    parent_id = fields.Many2one(
        'account.analytic.account',
        string='Parent',
        index=True,
        ondelete='cascade',
        domain="['!', ('id', 'child_of', id)]",
    )
    parent_path = fields.Char(index='btree')
    account_level = fields.Selection(
        [
            ('project', 'Project'),
            ('outcome', 'Outcome'),
            ('output', 'Output'),
            ('activity', 'Activity'),
        ],
        string='Level',
        compute='_compute_account_level',
        store=True,
        index=True,
        help=(
            'Project=root, Outcome=child of project, Output=child of outcome, '
            'Activity=child of output'
        ),
    )
    hierarchy_name = fields.Char(
        string='Account',
        compute='_compute_hierarchy_name',
        help='Indented name for Project → Outcome → Output → Activity list display',
    )
    child_ids = fields.One2many(
        'account.analytic.account',
        'parent_id',
        string='Children',
    )
    child_count = fields.Integer(
        string='Sub-Accounts',
        compute='_compute_child_count',
    )

    @api.depends('child_ids')
    def _compute_child_count(self):
        for account in self:
            account.child_count = len(account.child_ids)

    @api.depends('name', 'account_level', 'parent_path')
    def _compute_hierarchy_name(self):
        level_depth = {
            'project': 0,
            'outcome': 1,
            'output': 2,
            'activity': 3,
        }
        for account in self:
            depth = level_depth.get(account.account_level)
            if depth is None and account.parent_path:
                depth = max(account.parent_path.count('/') - 1, 0)
            depth = depth or 0
            prefix = ('\u00A0' * 4 * depth) + ('↳ ' if depth else '')
            account.hierarchy_name = f'{prefix}{account.name or ""}'

    def action_view_children(self):
        """Open child analytic accounts of this account."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sub-Accounts'),
            'res_model': 'account.analytic.account',
            'view_mode': 'list,form',
            'domain': [('parent_id', '=', self.id)],
            'context': {'default_parent_id': self.id, 'default_plan_id': self.plan_id.id},
        }

    @api.onchange('parent_id')
    def _onchange_parent_id(self):
        if self.parent_id:
            self.plan_id = self.parent_id.plan_id

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('parent_id') and not vals.get('plan_id'):
                parent = self.browse(vals['parent_id'])
                if parent:
                    vals['plan_id'] = parent.plan_id.id
        return super().create(vals_list)

    @api.depends(
        'parent_id',
        'parent_id.parent_id',
        'parent_id.parent_id.parent_id',
        'parent_id.project_ids',
        'parent_id.parent_id.project_ids',
        'project_ids',
    )
    def _compute_account_level(self):
        """Resolve hierarchy depth:
        Project → Outcome → Output → Activity
        """
        for account in self:
            if account.project_ids:
                account.account_level = 'project'
            elif account.parent_id and account.parent_id.project_ids:
                account.account_level = 'outcome'
            elif (
                account.parent_id
                and account.parent_id.parent_id
                and account.parent_id.parent_id.project_ids
            ):
                account.account_level = 'output'
            elif (
                account.parent_id
                and account.parent_id.parent_id
                and account.parent_id.parent_id.parent_id
            ):
                account.account_level = 'activity'
            else:
                account.account_level = False
