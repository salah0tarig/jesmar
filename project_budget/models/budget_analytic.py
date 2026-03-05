# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class BudgetAnalytic(models.Model):
    _inherit = 'budget.analytic'

    project_id = fields.Many2one(
        'project.project',
        string='Project',
        ondelete='set null',
        help='Optional: scope budget to a project (Outcome/Output hierarchy)',
    )
    budget_currency_option = fields.Selection(
        [
            ('company', 'Budget in Company Currency'),
            ('other', 'Budget in Other Currency'),
        ],
        string='Budget Currency Option',
        default='company',
        required=True,
        help='Choose whether to budget in company currency or in another currency.',
    )
    budget_currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        help='When "Budget in Other Currency" is selected, achieved amount is converted from company currency to this currency.',
    )
    company_currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
        string='Company Currency',
        readonly=True,
    )

    @api.constrains('budget_currency_option', 'budget_currency_id')
    def _check_budget_currency_option(self):
        for record in self:
            if record.budget_currency_option == 'other' and not record.budget_currency_id:
                raise ValidationError(
                    _('Please select a Currency when "Budget in Other Currency" is chosen.')
                )

    @api.onchange('budget_currency_option')
    def _onchange_budget_currency_option(self):
        """Clear currency when switching to company currency."""
        if self.budget_currency_option == 'company':
            self.budget_currency_id = False
