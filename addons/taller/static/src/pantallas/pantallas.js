/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";

const MODEL = "service.order";

function fmtMoney(symbol, value) {
    const n = new Intl.NumberFormat("es-UY", { maximumFractionDigits: 0 }).format(value || 0);
    return `${symbol || ""} ${n}`.trim();
}

function readFile(file) {
    return new Promise((resolve, reject) => {
        const r = new FileReader();
        r.onload = () => resolve(r.result);
        r.onerror = reject;
        r.readAsDataURL(file);
    });
}

/* ------------------------------------------------------------ Calendario */
class TallerCalendario extends Component {
    static template = "taller.Calendario";
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({ data: null, loading: true, drag: null, over: null });
        this.ym = null;
        this.weekdays = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];
        onWillStart(() => this.load());
    }
    async load() {
        this.state.loading = true;
        const a = this.ym ? [this.ym.year, this.ym.month] : [];
        this.state.data = await this.orm.call(MODEL, "cal_data", a);
        this.ym = { year: this.state.data.year, month: this.state.data.month };
        this.state.loading = false;
    }
    shift(delta) {
        let { year, month } = this.ym;
        month += delta;
        if (month < 1) { month = 12; year -= 1; }
        if (month > 12) { month = 1; year += 1; }
        this.ym = { year, month };
        return this.load();
    }
    today() {
        this.ym = null;
        return this.load();
    }
    open(item) {
        this.action.doAction({ type: "ir.actions.client", tag: "taller.ficha", params: { id: item.id }, name: item.name });
    }
    onDragStart(ev, item) {
        if (!item.movable) {
            ev.preventDefault();
            return;
        }
        this.state.drag = item;
        ev.dataTransfer.effectAllowed = "move";
        ev.dataTransfer.setData("text/plain", String(item.id));
    }
    onDragOver(ev, cell) {
        if (this.state.drag && !cell.empty) {
            ev.preventDefault();
            this.state.over = cell.iso;
        }
    }
    async onDrop(ev, cell) {
        ev.preventDefault();
        const item = this.state.drag;
        this.state.drag = null;
        this.state.over = null;
        if (!item || cell.empty) {
            return;
        }
        try {
            await this.orm.call(MODEL, "cal_move", [item.id, cell.iso]);
            this.notification.add(`${item.name} reprogramada al ${cell.iso.split("-").reverse().join("/")}`, { type: "success" });
        } catch (e) {
            this.notification.add((e.data && e.data.message) || "No se pudo mover la orden", { type: "danger" });
        }
        await this.load();
    }
    onDragEnd() {
        this.state.drag = null;
        this.state.over = null;
    }
}

/* --------------------------------------------------------------- Compras */
class TallerCompras extends Component {
    static template = "taller.Compras";
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({ data: { rows: [], symbol: "" }, loading: true, filter: "all", error: "" });
        onWillStart(() => this.load());
    }
    async load() {
        try {
            this.state.data = await this.orm.call(MODEL, "compras_list", []);
        } catch (e) {
            this.state.error = (e.data && e.data.message) || "Sin acceso";
        }
        this.state.loading = false;
    }
    money(v) {
        return fmtMoney(this.state.data.symbol, v);
    }
    get rows() {
        const f = this.state.filter;
        return this.state.data.rows.filter((r) => f === "all" || r.state === f);
    }
    async op(row, op) {
        try {
            await this.orm.call(MODEL, "compras_action", [row.id, op]);
        } catch (e) {
            this.notification.add((e.data && e.data.message) || "No se pudo completar", { type: "danger" });
        }
        await this.load();
    }
    openForm(row) {
        this.action.doAction({ type: "ir.actions.act_window", res_model: "service.purchase", res_id: row.id, views: [[false, "form"]] });
    }
    newPurchase() {
        this.action.doAction({ type: "ir.actions.act_window", res_model: "service.purchase", views: [[false, "form"]] });
    }
}

/* ------------------------------------------------------------- Garantías */
class TallerGarantias extends Component {
    static template = "taller.Garantias";
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({ rows: [], loading: true, filter: "all" });
        onWillStart(() => this.load());
    }
    async load() {
        const d = await this.orm.call(MODEL, "garantias_list", []);
        this.state.rows = d.rows;
        this.state.loading = false;
    }
    get rows() {
        const f = this.state.filter;
        return this.state.rows.filter((r) => f === "all" || r.kind === f);
    }
    count(kind) {
        return this.state.rows.filter((r) => r.kind === kind).length;
    }
    label(r) {
        if (r.days_left < 0) {
            return `Venció hace ${-r.days_left} d`;
        }
        return r.days_left === 0 ? "Vence hoy" : `Quedan ${r.days_left} d`;
    }
    open(r) {
        this.action.doAction({ type: "ir.actions.client", tag: "taller.ficha", params: { id: r.id }, name: r.name });
    }
    async reentry(r) {
        try {
            const id = await this.orm.call(MODEL, "garantia_reentry", [r.id]);
            this.action.doAction({ type: "ir.actions.client", tag: "taller.ficha", params: { id }, name: "Reingreso" });
        } catch (e) {
            this.notification.add((e.data && e.data.message) || "No se pudo crear el reingreso", { type: "danger" });
        }
    }
    wa(r) {
        window.open(r.wa_url, "_blank");
    }
}

/* ----------------------------------------------------------- Configuración */
class TallerConfig extends Component {
    static template = "taller.Config";
    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({ f: null, loading: true, saving: false, logo: null, error: "" });
        onWillStart(async () => {
            try {
                this.state.f = await this.orm.call(MODEL, "cfg_get", []);
            } catch (e) {
                this.state.error = (e.data && e.data.message) || "Sin acceso";
            }
            this.state.loading = false;
        });
    }
    async pickLogo(ev) {
        const file = ev.target.files && ev.target.files[0];
        if (!file) {
            return;
        }
        if (file.size > 3 * 1024 * 1024) {
            this.notification.add("El logo pesa demasiado (máximo 3 MB).", { type: "warning" });
            return;
        }
        this.state.logo = await readFile(file);
    }
    async save() {
        const f = this.state.f;
        this.state.saving = true;
        try {
            await this.orm.call(MODEL, "cfg_save", [{
                name: f.name, phone: f.phone, email: f.email, street: f.street, city: f.city,
                website: f.website, warranty_days: f.warranty_days, terms: f.terms,
            }, this.state.logo]);
            this.notification.add("Configuración guardada", { type: "success" });
            this.state.f = await this.orm.call(MODEL, "cfg_get", []);
            this.state.logo = null;
        } catch (e) {
            this.notification.add((e.data && e.data.message) || "No se pudo guardar", { type: "danger" });
        }
        this.state.saving = false;
    }
}

/* ------------------------------------------------------------ Panel de gestión */
class TallerPanel extends Component {
    static template = "taller.Panel";
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({ d: null, loading: true, goalEdit: false, goalValue: 0 });
        onWillStart(() => this.load());
    }
    async load() {
        this.state.d = await this.orm.call(MODEL, "panel_data", []);
        this.state.goalValue = this.state.d.goal || 0;
        this.state.loading = false;
    }
    money(v) {
        return fmtMoney(this.state.d.symbol, v);
    }
    get maxIncome() {
        return Math.max(1, ...this.state.d.months.map((m) => m.income));
    }
    barH(m) {
        return Math.max(2, Math.round((100 * m.income) / this.maxIncome));
    }
    get maxTech() {
        return Math.max(1, ...this.state.d.techs.map((t) => t.count));
    }
    techW(t) {
        return Math.max(4, Math.round((100 * t.count) / this.maxTech));
    }
    get linePoints() {
        const ms = this.state.d.months;
        const max = Math.max(1, ...ms.map((m) => m.orders));
        return ms.map((m, i) => `${(i * 100) / Math.max(1, ms.length - 1)},${100 - (m.orders * 90) / max}`).join(" ");
    }
    openAlert(a) {
        if (a.id) {
            this.action.doAction({ type: "ir.actions.client", tag: "taller.ficha", params: { id: a.id }, name: a.text });
        } else {
            this.action.doAction("taller.action_taller_inventario_ui");
        }
    }
    async saveGoal() {
        await this.orm.call(MODEL, "panel_set_goal", [this.state.goalValue]);
        this.state.goalEdit = false;
        await this.load();
        this.notification.add("Meta guardada", { type: "success" });
    }
}

/* ------------------------------------------------------- Mensajes pendientes */
class TallerMensajes extends Component {
    static template = "taller.Mensajes";
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ rows: [], loading: true, filter: "all" });
        onWillStart(() => this.load());
    }
    async load() {
        const d = await this.orm.call(MODEL, "msgs_list", []);
        this.state.rows = d.rows;
        this.state.loading = false;
    }
    get rows() {
        return this.state.rows.filter((r) => this.state.filter === "all" || r.kind === this.state.filter);
    }
    count(kind) {
        return this.state.rows.filter((r) => r.kind === kind).length;
    }
    async send(r) {
        window.open(r.wa_url, "_blank");
        await this.orm.call(MODEL, "msgs_mark", [r.id, r.kind]);
        this.state.rows = this.state.rows.filter((x) => !(x.id === r.id && x.kind === r.kind));
    }
    async skip(r) {
        await this.orm.call(MODEL, "msgs_mark", [r.id, r.kind]);
        this.state.rows = this.state.rows.filter((x) => !(x.id === r.id && x.kind === r.kind));
    }
    open(r) {
        this.action.doAction({ type: "ir.actions.client", tag: "taller.ficha", params: { id: r.id }, name: r.name });
    }
}

/* ------------------------------------------------------------- Actividad */
class TallerActividad extends Component {
    static template = "taller.Actividad";
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ rows: [], loading: true, error: "", q: "" });
        onWillStart(async () => {
            try {
                this.state.rows = (await this.orm.call(MODEL, "act_log", [200])).rows;
            } catch (e) {
                this.state.error = (e.data && e.data.message) || "Sin acceso";
            }
            this.state.loading = false;
        });
    }
    get rows() {
        const q = this.state.q.trim().toLowerCase();
        if (!q) {
            return this.state.rows;
        }
        return this.state.rows.filter((r) => `${r.order} ${r.who} ${r.text} ${r.changes.join(" ")}`.toLowerCase().includes(q));
    }
    open(r) {
        this.action.doAction({ type: "ir.actions.client", tag: "taller.ficha", params: { id: r.id }, name: r.order });
    }
}

registry.category("actions").add("taller.calendar", TallerCalendario);
registry.category("actions").add("taller.compras", TallerCompras);
registry.category("actions").add("taller.garantias", TallerGarantias);
registry.category("actions").add("taller.config", TallerConfig);
registry.category("actions").add("taller.panel", TallerPanel);
registry.category("actions").add("taller.mensajes", TallerMensajes);
registry.category("actions").add("taller.actividad", TallerActividad);
