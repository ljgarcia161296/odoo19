/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onMounted, useState } from "@odoo/owl";

class TallerFinanzas extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({ data: null, month: "" });
        onMounted(() => this.load());
    }

    async load() {
        this.state.data = await this.orm.call("service.order", "fin_data", [this.state.month || false]);
        this.state.month = this.state.data.month;
    }

    onMonth(ev) {
        if (ev.target.value) {
            this.state.month = ev.target.value;
            this.load();
        }
    }

    shiftMonth(delta) {
        const [y, m] = this.state.month.split("-").map(Number);
        const d = new Date(y, m - 1 + delta, 1);
        this.state.month = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
        this.load();
    }

    money(value) {
        const number = new Intl.NumberFormat("es-UY", { maximumFractionDigits: 0 }).format(value || 0);
        return `${this.state.data ? this.state.data.symbol : ""} ${number}`.trim();
    }

    async savePct(tech, ev) {
        const pct = parseFloat(ev.target.value) || 0;
        if (pct === tech.pct || !tech.id) {
            return;
        }
        await this.orm.call("service.order", "fin_set_commission", [tech.id, pct]);
        this.notification.add("Comisión guardada.", { type: "success" });
        await this.load();
    }

    newExpense() {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "taller.expense",
            views: [[false, "form"]],
            target: "new",
        }, { onClose: () => this.load() });
    }

    openExpense(exp) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "taller.expense",
            res_id: exp.id,
            views: [[false, "form"]],
            target: "new",
        }, { onClose: () => this.load() });
    }

    print() {
        window.print();
    }
}

TallerFinanzas.template = "taller.Finanzas";

registry.category("actions").add("taller.finanzas", TallerFinanzas);
