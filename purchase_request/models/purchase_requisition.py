from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ProcurementRequisition(models.Model):
    _name = 'procurement.requisition'
    _description = 'Procurement Requisition'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(default='New', readonly=True, copy=False)

    project_id = fields.Many2one('project.project',string="Program", tracking=True)
    
    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        compute='_compute_cost_center',
        string="Cost Center"
    )

    delivery_location_id = fields.Many2one(
        'stock.location',
        required=True
    )

    company_id = fields.Many2one(
        'res.company',
        default=lambda self: self.env.company,
        required=True
    )

    request_user_id = fields.Many2one(
        'res.users',
        default=lambda self: self.env.user
    )

    approver_id = fields.Many2one('res.users', tracking=True)

    reject_reason = fields.Text()
    rejected_by = fields.Many2one('res.users')
    rejected_date = fields.Datetime()

    line_ids = fields.One2many(
        'procurement.requisition.line',
        'pr_id'
    )

    estimated_total = fields.Float(
        compute='_compute_total',
        store=True
    )
    purchase_order_ids = fields.One2many(
        'purchase.order',
        'pr_id',
        string='Purchase Orders'
    )
    po_count = fields.Integer(compute="_compute_po_count")
    
    is_over_budget = fields.Boolean(
        compute="_compute_budget_status",store=False )
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('budget', 'Budget Approved'),
        ('po_draft', 'PO Draft'),
        ('po_approved', 'PO Approved'),
        ('received', 'Received'),
        ('paid', 'Paid'),
        ('rejected', 'Rejected')
    ], default='draft', tracking=True)

    @api.depends('project_id')
    def _compute_cost_center(self):
        for rec in self:
            rec.analytic_account_id = rec.project_id.account_id

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    "procurement.requisition"
                )
        return super().create(vals_list)
    
    def button_confirm(self):
        res = super().button_confirm()

        for po in self:
            if po.pr_id:
                po.pr_id.update_state_from_po()

        return res

    @api.depends('line_ids.total')
    def _compute_total(self):
        for rec in self:
            rec.estimated_total = sum(rec.line_ids.mapped('total'))

    def _compute_po_count(self):
        for rec in self:
            rec.po_count = self.env['purchase.order'].search_count([
                ('pr_id', '=', rec.id)
            ])

    def write(self, vals):
            for rec in self:
                if rec.state  in ( 'paid'):
                    raise UserError("Locked document")
            return super().write(vals)
        
    @api.depends(
        'line_ids.total',
        'line_ids.task_id',
        'line_ids.product_id',
        'company_id',
        'project_id',
    )
    def _compute_budget_status(self):
        for rec in self:
            rec.is_over_budget = bool(rec._get_pr_budget_errors())

    def update_state_from_po(self):
        for rec in self:

            pos = rec.purchase_order_ids
            if not pos:
                continue

            # 1️⃣ PO Draft
            if any(po.state in ['draft', 'sent'] for po in pos):
                rec.state = 'po_draft'
                continue

            # 2️⃣ PO Approved
            if any(po.state in ['purchase', 'done'] for po in pos):
                rec.state = 'po_approved'

            # 3️⃣ RECEIVED (based on qty_received)
            all_received = all(
                line.qty_received >= line.product_qty
                for po in pos
                for line in po.order_line
                if line.product_id.type != 'service'
            )

            if all_received:
                rec.state = 'received'

            # 4️⃣ PAID (based on invoice payment)
            invoices = pos.mapped('invoice_ids')

            all_paid = invoices and all(
                inv.payment_state == 'paid'
                for inv in invoices
            )

            if all_paid:
                rec.state = 'paid'
    # def update_state_from_po(self):
    #     for rec in self:
    #         pos = self.env['purchase.order'].search([
    #             ('pr_id', '=', rec.id)
    #         ])

    #         if not pos:
    #             continue

    #         # 1. PO Draft
    #         if any(po.state in ['draft', 'sent'] for po in pos):
    #             rec.state = 'po_draft'
    #             continue

    #         # 2. PO Approved
    #         if any(po.state in ['purchase', 'done'] for po in pos):
    #             rec.state = 'po_approved'
    #         # moves = pos.mapped('order_line.move_ids')

    #         # # Only incoming moves
    #         # incoming_moves = moves.filtered(lambda m: m.picking_id.picking_type_id.code == 'incoming')

    #         # if incoming_moves and all(m.state == 'done' for m in incoming_moves):
    #         #     rec.state = 'received'

    #         all_received = all(
    #             line.qty_received >= line.product_qty
    #             for po in pos
    #             for line in po.order_line
    #             if line.product_id.type != 'service'
    #         )

    #         if all_received:
    #             rec.state = 'received'

    #         # all_pickings = pos.mapped('picking_ids')
    #         # if all_pickings and all(p.state == 'done' for p in all_pickings):
    #         #     rec.state = 'received'

    #         # 4. Paid (Invoices Paid)
    #         invoices = pos.mapped('invoice_ids')
    #         all_paid = invoices and all(inv.payment_state == 'paid' for inv in invoices)
    #         if invoices and all_paid:
    #             rec.state = 'paid'
                
    # ================= ACTIONS =================

    def action_submit(self):
        # self._check_group('group_pr_user')
        self.state = 'submitted'

    def action_budget_approve(self):
        # self._check_group('group_finance_approval')
        for rec in self:
            errors = rec._get_pr_budget_errors()
            if errors:
                raise UserError('\n'.join(errors))
            rec.state = 'budget'

    def action_reject(self, reason=None):
        for rec in self:
            rec._release_budget()

            rec.with_context(allow_reject=True).write({
                'state': 'rejected',
                'reject_reason': reason,
                'rejected_by': self.env.user.id,
                'rejected_date': fields.Datetime.now()
            })
            
    def action_open_reject_wizard(self):
        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': 'Reject Reason',
            'res_model': 'procurement.reject.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_id': self.id
            }
        }

    def _pr_budget_check_date(self):
        return fields.Date.context_today(self)

    def _get_budget_lines_for_pr_line(self, line):
        """Match budget lines the same way project_budget matches PO lines."""
        if not line.task_id or not line.product_id:
            return self.env['budget.line']
        acc = line.task_id.activity_analytic_account_id or line.task_id.output_id
        if not acc:
            return self.env['budget.line']
        check_date = self._pr_budget_check_date()
        domain = [
            '|', ('task_id', '=', line.task_id.id),
            '&', ('task_id', '=', False), ('account_id', '=', acc.id),
            ('budget_analytic_id.budget_type', '!=', 'revenue'),
            ('budget_analytic_id.state', 'in', ['confirmed', 'done']),
            ('date_from', '<=', check_date),
            ('date_to', '>=', check_date),
            '|', ('product_id', '=', False), ('product_id', '=', line.product_id.id),
        ]
        company = line.pr_id.company_id
        if company:
            domain.extend(['|', ('company_id', '=', False), ('company_id', '=', company.id)])
        BudgetLine = self.env['budget.line'].sudo()
        if line.project_id:
            matches = BudgetLine.search(domain + [('budget_project_id', '=', line.project_id.id)])
            if matches:
                return matches
        return BudgetLine.search(domain)

    def _budget_line_available(self, budget):
        budget.invalidate_recordset([
            'committed_amount',
            'achieved_amount',
            'committed_percentage',
            'achieved_percentage',
            'balance',
        ])
        return (
            (budget.budget_amount or 0.0)
            - (budget.achieved_amount or 0.0)
            - (budget.committed_amount or 0.0)
        )

    def _pick_budget_line_for_pr_line(self, line, budget_lines):
        exact = budget_lines.filtered(
            lambda b: b.task_id == line.task_id and b.product_id == line.product_id
        )
        candidates = exact or budget_lines.filtered(lambda b: b.task_id == line.task_id) or budget_lines
        best = self.env['budget.line']
        best_avail = None
        for budget in candidates:
            available = self._budget_line_available(budget)
            if available >= (line.total or 0.0):
                return budget
            if best_avail is None or available > best_avail:
                best = budget
                best_avail = available
        return best

    def _format_pr_budget_error(self, line, budget, requested, available):
        if not budget:
            return _(
                "No confirmed budget line found for Activity '%(activity)s' "
                "and Product '%(product)s'."
            ) % {
                'activity': line.task_id.display_name,
                'product': line.product_id.display_name,
            }
        currency = (
            budget.budget_display_currency_id
            or line.pr_id.company_id.currency_id
            or self.env.company.currency_id
        )
        return _(
            "Budget exceeded for Activity '%(activity)s' and Product '%(product)s'. "
            "Available balance: %(available).2f %(currency)s. "
            "Requested amount: %(requested).2f %(currency)s."
        ) % {
            'activity': line.task_id.display_name,
            'product': line.product_id.display_name,
            'available': available,
            'requested': requested,
            'currency': currency.name,
        }

    def _get_pr_budget_errors(self):
        """Check each PR line against its activity + product budget remaining.

        Remaining matches purchase.order.line: budgeted - achieved - committed.
        Does not write budget.line.committed_amount (that field is computed from POs).
        """
        self.ensure_one()
        errors = []
        requested_by_budget = {}
        lines_without_budget = []
        for line in self.line_ids:
            if (line.total or 0.0) <= 0:
                continue
            if not line.task_id or not line.product_id:
                errors.append(_(
                    "Each purchase request line needs an Activity and a Product "
                    "to check the budget."
                ))
                continue
            matches = self._get_budget_lines_for_pr_line(line)
            if not matches:
                lines_without_budget.append(line)
                continue
            budget = self._pick_budget_line_for_pr_line(line, matches)
            requested_by_budget.setdefault(budget, 0.0)
            requested_by_budget[budget] += line.total or 0.0

        for line in lines_without_budget:
            errors.append(self._format_pr_budget_error(line, False, line.total, 0.0))

        reported = set()
        for budget, requested in requested_by_budget.items():
            available = self._budget_line_available(budget)
            if requested <= available:
                continue
            sample = self.line_ids.filtered(
                lambda l: l.task_id == budget.task_id and l.product_id == budget.product_id
            )[:1]
            line = sample or self.line_ids[:1]
            key = (budget.id, requested, available)
            if key in reported:
                continue
            reported.add(key)
            errors.append(self._format_pr_budget_error(line, budget, requested, available))
        return errors

    def _release_budget(self):
        """PR no longer reserves budget.line.committed_amount.

        Commitment is computed by project_budget from confirmed purchase orders.
        """
        return

    def action_create_po(self):
        # self._check_group('group_procurement_officer')
        self.ensure_one()

        if not self.line_ids:
            raise UserError("Add lines first")

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order',
            'view_mode': 'form',
            'context': {
                'default_pr_id': self.id
            }
        }

    def action_view_po(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order',
            'view_mode': 'list,form',
            'domain': [('pr_id', '=', self.id)],
        }
    def action_view_pos(self):
        self.ensure_one()

        action = {
            'type': 'ir.actions.act_window',
            'name': 'Purchase Orders',
            'res_model': 'purchase.order',
            'view_mode': 'list,form',
            'domain': [('pr_id', '=', self.id)],
            'context': {
                'default_pr_id': self.id
            }
        }

        if len(self.purchase_order_ids) == 1:
            action['view_mode'] = 'form'
            action['res_id'] = self.purchase_order_ids.id

        return action
   

class ProcurementRequisitionLine(models.Model):
    _name = 'procurement.requisition.line'

    pr_id = fields.Many2one('procurement.requisition')
    project_id = fields.Many2one(
        'project.project',
        related='pr_id.project_id',
        string="Program",
        store=True,
        readonly=True
    )
    task_id = fields.Many2one(
        'project.task',
        domain="[('project_id','=',project_id)]", 
        string="Activity"
    )
    budget_line_id = fields.Many2one(
        'budget.line',
        compute='_compute_budget_line',
        store=False
    )
    product_id = fields.Many2one('product.product')
    quantity = fields.Float()
    price = fields.Float()

    total = fields.Float(compute='_compute_total', store=True)

    @api.onchange('product_id')
    def _onchange_product(self):
        self.price = self.product_id.standard_price

    @api.depends('quantity', 'price')
    def _compute_total(self):
        for rec in self:
            rec.total = rec.quantity * rec.price
        
    @api.depends('project_id', 'task_id', 'product_id', 'pr_id.company_id')
    def _compute_budget_line(self):
        for rec in self:
            if not rec.pr_id:
                rec.budget_line_id = False
                continue
            matches = rec.pr_id._get_budget_lines_for_pr_line(rec)
            rec.budget_line_id = (
                rec.pr_id._pick_budget_line_for_pr_line(rec, matches) if matches else False
            )

    @api.onchange('task_id')
    def _onchange_task_filter_products(self):
        if not self.task_id:
            return {'domain': {'product_id': []}}

        domain = [
            ('task_id', '=', self.task_id.id),
            ('budget_analytic_id.budget_type', '!=', 'revenue'),
            ('budget_analytic_id.state', 'in', ['confirmed', 'done']),
        ]
        if self.project_id:
            domain.append(('budget_project_id', '=', self.project_id.id))
        budgets = self.env['budget.line'].sudo().search(domain)
        product_ids = set(budgets.mapped('product_id').ids)
        for budget in budgets:
            if budget.allowed_product_ids:
                product_ids.update(budget.allowed_product_ids.ids)
        if product_ids:
            return {'domain': {'product_id': [('id', 'in', list(product_ids))]}}
        return {'domain': {'product_id': []}}  
                
class BudgetLine(models.Model):
    _inherit = 'budget.line'

    project_id = fields.Many2one('project.project')
    task_id = fields.Many2one('project.task')

    allowed_product_ids = fields.Many2many(
        'product.product',
        string="Allowed Products"
    )