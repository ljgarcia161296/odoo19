/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, onMounted, onWillUnmount, useState } from "@odoo/owl";

const TABS = [
    { key: "open", label: "Pendientes" },
    { key: "late", label: "Atrasadas" },
    { key: "ready", label: "Listas" },
    { key: "all", label: "Todas" },
];

class TallerTech extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.tabs = TABS;
        this.timer = null;
        this.partTimer = null;
        this.state = useState({
            mode: "open",
            mine: false,
            isManager: false,
            data: { counts: { open: 0, ready: 0, late: 0 }, orders: [], symbol: "" },
            detail: null,
            partQuery: "",
            parts: [],
            qty: 1,
            labor: "",
            busy: false,
        });
        this.onLive = () => {
            clearTimeout(this.timer);
            this.timer = setTimeout(() => this.reload(), 700);
        };
        onWillStart(async () => {
            const init = await this.orm.call("service.order", "counter_init", []);
            this.state.isManager = init.is_manager;
            await this.reload();
        });
        onMounted(() => window.addEventListener("taller-refresh", this.onLive));
        onWillUnmount(() => {
            window.removeEventListener("taller-refresh", this.onLive);
            clearTimeout(this.timer);
            clearTimeout(this.partTimer);
        });
    }

    async reload() {
        this.state.data = await this.orm.call("service.order", "tech_orders", [
            this.state.mode,
            this.state.mine,
        ]);
        if (this.state.detail) {
            await this.refreshDetail();
        }
    }

    setMode(mode) {
        this.state.mode = mode;
        this.reload();
    }

    toggleMine() {
        this.state.mine = !this.state.mine;
        this.reload();
    }

    tabCount(key) {
        const counts = this.state.data.counts;
        return key === "all" ? "" : counts[key];
    }

    money(value, symbol) {
        const number = new Intl.NumberFormat("es-UY", { maximumFractionDigits: 0 }).format(value || 0);
        return `${symbol || this.state.data.symbol || ""} ${number}`.trim();
    }

    // ------------------------------------------------------------ detalle
    async openDetail(order) {
        this.state.detail = await this.orm.call("service.order", "tech_order_detail", [order.id]);
        this.state.labor = this.state.detail.labor ? String(this.state.detail.labor) : "";
        this.state.partQuery = "";
        this.state.parts = [];
        this.state.qty = 1;
    }

    async refreshDetail() {
        try {
            this.state.detail = await this.orm.call("service.order", "tech_order_detail", [
                this.state.detail.id,
            ]);
        } catch (e) {
            this.state.detail = null;
        }
    }

    closeDetail() {
        this.state.detail = null;
    }

    openForm() {
        const id = this.state.detail.id;
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "service.order",
            res_id: id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    async runAction(key) {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            await this.orm.call("service.order", "tech_action", [this.state.detail.id, key]);
            this.notification.add("Estado actualizado.", { type: "success" });
            await this.reload();
        } finally {
            this.state.busy = false;
        }
    }

    // ------------------------------------------------------------ repuestos y mano de obra
    onPartQuery(ev) {
        this.state.partQuery = ev.target.value;
        clearTimeout(this.partTimer);
        this.partTimer = setTimeout(async () => {
            this.state.parts = this.state.partQuery.trim().length >= 2
                ? await this.orm.call("service.order", "tech_search_parts", [this.state.partQuery])
                : [];
        }, 300);
    }

    async addPart(part) {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            await this.orm.call("service.order", "tech_add_line", [
                this.state.detail.id,
                part.id,
                this.state.qty || 1,
            ]);
            this.state.parts = [];
            this.state.partQuery = "";
            this.state.qty = 1;
            await this.reload();
        } finally {
            this.state.busy = false;
        }
    }

    async removeLine(line) {
        await this.orm.call("service.order", "tech_remove_line", [line.id]);
        await this.reload();
    }

    async saveLabor() {
        await this.orm.call("service.order", "tech_set_labor", [
            this.state.detail.id,
            parseFloat(this.state.labor) || 0,
        ]);
        this.notification.add("Mano de obra guardada.", { type: "success" });
        await this.reload();
    }
}

TallerTech.template = "taller.Tech";

registry.category("actions").add("taller.tech", TallerTech);
