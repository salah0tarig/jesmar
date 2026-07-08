# -*- coding: utf-8 -*-


def migrate(cr, version):
    """Remove hierarchy card view bindings added in earlier revisions."""
    cr.execute(
        """
        DELETE FROM ir_act_window_view
         WHERE id IN (
            SELECT res_id FROM ir_model_data
             WHERE module = 'project_budget'
               AND name IN (
                   'action_account_analytic_account_form_hierarchy',
                   'action_analytic_account_form_hierarchy'
               )
               AND model = 'ir.actions.act_window.view'
         )
        """
    )
    cr.execute(
        """
        DELETE FROM ir_ui_view
         WHERE id IN (
            SELECT res_id FROM ir_model_data
             WHERE module = 'project_budget'
               AND name = 'view_account_analytic_account_hierarchy_budget'
               AND model = 'ir.ui.view'
         )
        """
    )
    cr.execute(
        """
        DELETE FROM ir_model_data
         WHERE module = 'project_budget'
           AND name IN (
               'action_account_analytic_account_form_hierarchy',
               'action_analytic_account_form_hierarchy',
               'view_account_analytic_account_hierarchy_budget'
           )
        """
    )
