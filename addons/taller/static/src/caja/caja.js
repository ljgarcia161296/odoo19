/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, onMounted, onWillUnmount, useState } from "@odoo/owl";

class TallerCaja extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ data: null, date: "", counted: "" });
        this.onLive = () => {
            clearTimeout(this.liveTimer);
            this.liveTimer = setTimeout(() => this.load(), 700);
        };
        onMounted(() => {
            this.load();
            window.addEventListener("taller-refresh", this.onLive);
        });
        onWillUnmount(() => {
            window.removeEventListener("taller-refresh", this.onLive);
            clearTimeout(this.liveTimer);
        });
    }

    async load() {
        this.state.data = await this.orm.call("service.order", "caja_data", [this.state.date || false]);
        this.state.date = this.state.data.date;
    }

    shiftDay(delta) {
        const d = new Date(this.state.date + "T12:00:00");
        d.setDate(d.getDate() + delta);
        this.state.date = d.toISOString().slice(0, 10);
        this.load();
    }

    goToday() {
        this.state.date = "";
        this.load();
    }

    onDate(ev) {
        this.state.date = ev.target.value;
        this.load();
    }

    money(value) {
        const number = new Intl.NumberFormat("es-UY", { maximumFractionDigits: 0 }).format(value || 0);
        return `${this.state.data ? this.state.data.symbol : ""} ${number}`.trim();
    }

    get cash() {
        const m = this.state.data.methods.find((x) => x.key === "cash");
        return m ? m.total : 0;
    }

    get diff() {
        const counted = parseFloat(this.state.counted);
        return isNaN(counted) ? null : counted - this.cash;
    }

    get weekMax() {
        return Math.max(1, ...this.state.data.week.map((w) => w.total));
    }

    openOrder(row) {
        if (!row.order_id) {
            return;
        }
        this.action.doAction({
            type: "ir.actions.client",
            tag: "taller.ficha",
            params: { id: row.order_id },
            name: row.order,
        });
    }

    print() {
        window.print();
    }
}

TallerCaja.template = "taller.Caja";

registry.category("actions").add("taller.caja", TallerCaja);
