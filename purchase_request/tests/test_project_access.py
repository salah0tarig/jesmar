# -*- coding: utf-8 -*-
"""Regression: PR form must open when Program is blocked by project record rules."""

from odoo.tests import TransactionCase, tagged
from odoo.exceptions import AccessError


@tagged("post_install", "-at_install", "purchase_request")
class TestProcurementRequisitionProjectAccess(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_a = cls.env.company
        cls.company_b = cls.env["res.company"].create({"name": "Other Co PR Access Test"})

        # Program on company B — user on company A alone cannot read it via multi-company rule.
        cls.project_b = cls.env["project.project"].sudo().create({
            "name": "Program Other Company",
            "company_id": cls.company_b.id,
            "privacy_visibility": "followers",
        })

        cls.location = cls.env["stock.location"].search(
            [("usage", "=", "internal"), ("company_id", "in", [cls.company_a.id, False])],
            limit=1,
        )
        if not cls.location:
            warehouse = cls.env["stock.warehouse"].search(
                [("company_id", "=", cls.company_a.id)], limit=1
            )
            cls.location = warehouse.lot_stock_id if warehouse else cls.env["stock.location"].create({
                "name": "PR Test Stock",
                "usage": "internal",
                "company_id": cls.company_a.id,
            })

        cls.pr = cls.env["procurement.requisition"].sudo().create({
            "project_id": cls.project_b.id,
            "delivery_location_id": cls.location.id,
            "company_id": cls.company_a.id,
        })

        cls.user_limited = cls.env["res.users"].create({
            "name": "PR Limited User",
            "login": "pr_limited_access_test",
            "email": "pr_limited@example.com",
            "company_id": cls.company_a.id,
            "company_ids": [(6, 0, [cls.company_a.id])],
            "group_ids": [(6, 0, [
                cls.env.ref("base.group_user").id,
                cls.env.ref("purchase_request.group_pr_user").id,
                cls.env.ref("stock.group_stock_user").id,
            ])],
        })

    def test_project_field_bypasses_search_access(self):
        field = self.env["procurement.requisition"]._fields["project_id"]
        self.assertTrue(field.bypass_search_access)

    def test_limited_user_cannot_read_foreign_project_directly(self):
        Project = self.env["project.project"].with_user(self.user_limited)
        with self.assertRaises(AccessError):
            Project.browse(self.project_b.id).check_access("read")

    def test_limited_user_can_open_pr_and_compute_cost_center(self):
        pr = self.env["procurement.requisition"].with_user(self.user_limited).browse(self.pr.id)
        # Opening / reading the PR (including computed analytic) must not raise.
        data = pr.read(["name", "project_id", "analytic_account_id", "state"])
        self.assertEqual(data[0]["project_id"][0], self.project_b.id)
        # Cost center compute uses sudo — must not AccessError.
        _ = pr.analytic_account_id
