/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, onMounted, onWillUnmount, useState } from "@odoo/owl";

const METHODS = [
    { key: "cash", label: "Efectivo", icon: "fa-money" },
    { key: "transfer", label: "Transferencia", icon: "fa-exchange" },
    { key: "card", label: "Tarjeta", icon: "fa-credit-card" },
    { key: "other", label: "Otro", icon: "fa-ellipsis-h" },
];

class TallerVenta extends Component {
    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.methods = METHODS;
        this.state = useState({
            query: "",
            parts: [],
            cart: [],
            method: "cash",
            customer: "",
            free: { name: "", price: "" },
            today: { sales: [], total: 0, symbol: "", is_manager: false },
            busy: false,
        });
        this.timer = null;
        onWillStart(() => this.loadToday());
        onMounted(() => this.searchParts());
        onWillUnmount(() => clearTimeout(this.timer));
    }

    async loadToday() {
        this.state.today = await this.orm.call("service.order", "venta_today", []);
    }

    onQuery(ev) {
        this.state.query = ev.target.value;
        clearTimeout(this.timer);
        this.timer = setTimeout(() => this.searchParts(), 250);
    }

    async searchParts() {
        this.state.parts = await this.orm.call("service.order", "venta_parts", [this.state.query]);
    }

    money(value) {
        const number = new Intl.NumberFormat("es-UY", { maximumFractionDigits: 0 }).format(value || 0);
        return `${this.state.today.symbol || ""} ${number}`.trim();
    }

    addPart(part) {
        const line = this.state.cart.find((l) => l.part_id === part.id);
        if (line) {
            line.qty += 1;
        } else {
            this.state.cart.push({ key: `p${part.id}`, part_id: part.id, name: part.name, qty: 1, price: part.price, stock: part.stock });
        }
    }

    addFree() {
        const f = this.state.free;
        if (!f.name.trim()) {
            return;
        }
        this.state.cart.push({ key: `f${Date.now()}`, part_id: false, name: f.name.trim(), qty: 1, price: parseFloat(f.price) || 0 });
        this.state.free = { name: "", price: "" };
    }

    change(line, delta) {
        line.qty = Math.max(1, (line.qty || 1) + delta);
    }

    remove(line) {
        this.state.cart = this.state.cart.filter((l) => l.key !== line.key);
    }

    onPrice(line, ev) {
        line.price = parseFloat(ev.target.value) || 0;
    }

    get total() {
        return this.state.cart.reduce((acc, l) => acc + (l.qty || 0) * (l.price || 0), 0);
    }

    async confirm() {
        if (!this.state.cart.length || this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            const res = await this.orm.call("service.order", "venta_create", [
                this.state.cart.map((l) => ({ part_id: l.part_id, name: l.name, qty: l.qty, price: l.price })),
                this.state.method,
                this.state.customer,
            ]);
            this.notification.add(`Venta ${res.name} cobrada: ${this.money(res.total)}`, { type: "success" });
            this.state.cart = [];
            this.state.customer = "";
            await Promise.all([this.loadToday(), this.searchParts()]);
        } finally {
            this.state.busy = false;
        }
    }

    async cancelSale(sale) {
        if (!window.confirm(`¿Anular la venta ${sale.name}? Se devuelve el stock.`)) {
            return;
        }
        await this.orm.call("service.order", "venta_cancel", [sale.id]);
        await Promise.all([this.loadToday(), this.searchParts()]);
    }
}

TallerVenta.template = "taller.Venta";

registry.category("actions").add("taller.venta", TallerVenta);
