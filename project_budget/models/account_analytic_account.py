# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class AccountAnalyticAccount(models.Model):
    _inherit = 'account.analytic.account'

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
        ],
        string='Level',
        compute='_compute_account_level',
        store=True,
        help='Project=root, Outcome=child of project, Output=child of outcome',
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

    _parent_store = True

    @api.depends('child_ids')
    def _compute_child_count(self):
        for account in self:
            account.child_count = len(account.child_ids)

    def action_view_children(self):
        """Open child analytic accounts (Outcomes or Outputs) of this account."""
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

    @api.depends('parent_id', 'parent_id.parent_id', 'project_ids')
    def _compute_account_level(self):
        for account in self:
            if account.project_ids:
                account.account_level = 'project'
            elif account.parent_id and account.parent_id.project_ids:
                account.account_level = 'outcome'
            elif account.parent_id and account.parent_id.parent_id:
                account.account_level = 'output'
            else:
                account.account_level = False
