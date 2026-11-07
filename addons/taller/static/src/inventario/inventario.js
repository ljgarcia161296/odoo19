/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";

class TallerInventario extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            data: { parts: [], symbol: "", is_manager: false, count: 0, low: 0, value: 0 },
            search: "",
            onlyLow: false,
            selected: {},
            adding: false,
            form: { name: "", code: "", cost: "", price: "", min_stock: "", stock: "" },
        });
        this.timer = null;
        this.onLive = () => {
            clearTimeout(this.liveTimer);
            this.liveTimer = setTimeout(() => this.load(), 700);
        };
        onWillStart(() => this.load());
        window.addEventListener("taller-refresh", this.onLive);
        onWillUnmount(() => {
            window.removeEventListener("taller-refresh", this.onLive);
            clearTimeout(this.timer);
            clearTimeout(this.liveTimer);
        });
    }

    async load() {
        this.state.data = await this.orm.call("service.order", "inv_data", [this.state.search, this.state.onlyLow]);
    }

    onSearch(ev) {
        this.state.search = ev.target.value;
        clearTimeout(this.timer);
        this.timer = setTimeout(() => this.load(), 300);
    }

    toggleLow() {
        this.state.onlyLow = !this.state.onlyLow;
        this.load();
    }

    money(value) {
        const number = new Intl.NumberFormat("es-UY", { maximumFractionDigits: 0 }).format(value || 0);
        return `${this.state.data.symbol || ""} ${number}`.trim();
    }

    async adjust(part, delta) {
        await this.orm.call("service.order", "inv_adjust", [part.id, delta, "Ajuste rápido"]);
        await this.load();
    }

    async adjustPrompt(part) {
        const raw = window.prompt(`Stock actual de ${part.name}: ${part.stock}\n¿Cuánto sumar (o restar con -)?`, "1");
        const delta = parseFloat(raw);
        if (!raw || isNaN(delta) || !delta) {
            return;
        }
        await this.adjust(part, delta);
    }

    async saveField(part, field, ev) {
        const value = parseFloat(ev.target.value) || 0;
        const current = { min_stock: part.min, price: part.price, cost: part.cost }[field];
        if (value === current) {
            return;
        }
        await this.orm.call("service.order", "inv_write", [part.id, { [field]: value }]);
        await this.load();
    }

    toggleSel(part) {
        this.state.selected[part.id] = !this.state.selected[part.id];
    }

    get selectedIds() {
        return Object.keys(this.state.selected).filter((k) => this.state.selected[k]).map(Number);
    }

    async makePurchase(all) {
        const ids = all ? [] : this.selectedIds;
        const action = await this.orm.call("service.order", "inv_make_purchase", [ids]);
        this.state.selected = {};
        if (action && action.type) {
            await this.action.doAction(action);
        }
    }

    async createPart() {
        const f = this.state.form;
        await this.orm.call("service.order", "inv_create_part", [f.name, f.code, f.cost, f.price, f.min_stock, f.stock]);
        this.state.form = { name: "", code: "", cost: "", price: "", min_stock: "", stock: "" };
        this.state.adding = false;
        this.notification.add("Repuesto creado.", { type: "success" });
        await this.load();
    }

    openPart(part) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "service.part",
            res_id: part.id,
            views: [[false, "form"]],
            target: "current",
        });
    }
}

TallerInventario.template = "taller.Inventario";

registry.category("actions").add("taller.inventario", TallerInventario);
