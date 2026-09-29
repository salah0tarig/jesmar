# -*- coding: utf-8 -*-

from odoo import api, models
from odoo.orm.domains import Domain


class AccountJournal(models.Model):
    _inherit = "account.journal"

    @api.model
    def _search(self, domain, offset=0, limit=None, order=None, **kwargs):
        """Pay dropdown: include journals of the payslip company.

        The standard journal rule only shows journals of the company selected
        in the switcher. A payslip on Omdurman then lists no journals while the
        user is on JASMAR, even when that user is allowed on Omdurman.
        """
        company_ids = self.env.context.get("hr_payroll_payment_company_ids")
        if (
            company_ids
            and self.env.context.get("hr_payroll_payment_register")
            and not self.env.su
            and not kwargs.get("bypass_access")
        ):
            allowed = set(self.env.user.company_ids.ids)
            company_ids = [cid for cid in company_ids if cid in allowed]
            if company_ids:
                domain = Domain(domain) & Domain("company_id", "in", company_ids)
                kwargs = dict(kwargs, bypass_access=True)
        return super()._search(domain, offset=offset, limit=limit, order=order, **kwargs)
