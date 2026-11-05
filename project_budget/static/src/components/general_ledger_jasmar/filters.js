/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { AccountReport } from "@account_reports/components/account_report/account_report";
import { AccountReportFilters } from "@account_reports/components/account_report/filters/filters";

export class GeneralLedgerJasmarFilters extends AccountReportFilters {
    static template = "project_budget.GeneralLedgerJasmarFilters";

    get hasJasmarHierarchyFilter() {
        return "jasmar_project_ids" in this.controller.cachedFilterOptions;
    }

    getHierarchyDomain(optionKey) {
        const opts = this.controller.cachedFilterOptions;
        if (optionKey === "jasmar_project_ids") {
            return [["account_level", "=", "project"]];
        }
        if (optionKey === "jasmar_outcome_ids") {
            const domain = [["account_level", "=", "outcome"]];
            if (opts.jasmar_project_ids?.length) {
                domain.push(["parent_id", "in", opts.jasmar_project_ids]);
            }
            return domain;
        }
        if (optionKey === "jasmar_output_ids") {
            const domain = [["account_level", "=", "output"]];
            if (opts.jasmar_outcome_ids?.length) {
                domain.push(["parent_id", "in", opts.jasmar_outcome_ids]);
            } else if (opts.jasmar_project_ids?.length) {
                domain.push(["parent_id.parent_id", "in", opts.jasmar_project_ids]);
            }
            return domain;
        }
        if (optionKey === "jasmar_activity_ids") {
            const domain = [["account_level", "=", "activity"]];
            if (opts.jasmar_output_ids?.length) {
                domain.push(["parent_id", "in", opts.jasmar_output_ids]);
            } else if (opts.jasmar_outcome_ids?.length) {
                domain.push(["parent_id.parent_id", "in", opts.jasmar_outcome_ids]);
            } else if (opts.jasmar_project_ids?.length) {
                domain.push(["id", "child_of", opts.jasmar_project_ids]);
            }
            return domain;
        }
        return [];
    }

    getHierarchyMultiRecordSelectorProps(optionKey) {
        return {
            resModel: "account.analytic.account",
            resIds: this.controller.cachedFilterOptions[optionKey] || [],
            domain: this.getHierarchyDomain(optionKey),
            update: async (resIds) => {
                await this.controller.updateOption(optionKey, resIds);
                if (optionKey === "jasmar_project_ids") {
                    await this.controller.updateOption("jasmar_outcome_ids", []);
                    await this.controller.updateOption("jasmar_output_ids", []);
                    await this.controller.updateOption("jasmar_activity_ids", []);
                } else if (optionKey === "jasmar_outcome_ids") {
                    await this.controller.updateOption("jasmar_output_ids", []);
                    await this.controller.updateOption("jasmar_activity_ids", []);
                } else if (optionKey === "jasmar_output_ids") {
                    await this.controller.updateOption("jasmar_activity_ids", []);
                }
                await this.applyFilters(optionKey);
            },
        };
    }

    get selectedJasmarHierarchyLabel() {
        const opts = this.controller.cachedFilterOptions;
        const parts = [];
        if (opts.jasmar_project_ids?.length) {
            parts.push(_t("Project"));
        }
        if (opts.jasmar_outcome_ids?.length) {
            parts.push(_t("Outcome"));
        }
        if (opts.jasmar_output_ids?.length) {
            parts.push(_t("Output"));
        }
        if (opts.jasmar_activity_ids?.length) {
            parts.push(_t("Activity"));
        }
        return parts.length ? parts.join(" > ") : _t("Project > Outcome > Output > Activity");
    }
}

AccountReport.registerCustomComponent(GeneralLedgerJasmarFilters);
