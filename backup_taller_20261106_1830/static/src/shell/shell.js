/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onMounted, onWillUnmount, useState } from "@odoo/owl";

const STORAGE_KEY = "taller.sidebar.collapsed";

const ICONS_BY_XMLID = {
    "taller.menu_taller_home": "fa-home",
    "taller.menu_taller_counter": "fa-plus-circle",
    "taller.menu_taller_tech": "fa-wrench",
    "taller.menu_service_order": "fa-th-large",
    "taller.menu_taller_calendar": "fa-calendar",
    "taller.menu_taller_to_invoice": "fa-file-text-o",
    "taller.menu_taller_clientes": "fa-users",
    "taller.menu_taller_activities": "fa-bell-o",
    "taller.menu_taller_inventory": "fa-cubes",
    "taller.menu_taller_reports": "fa-bar-chart",
    "taller.menu_taller_config": "fa-cog",
};
const ICONS_BY_NAME = {
    "Inicio": "fa-home",
    "Recepción": "fa-plus-circle",
    "Mi trabajo": "fa-wrench",
    "Órdenes de Servicio": "fa-th-large",
    "Calendario": "fa-calendar",
    "Por facturar": "fa-file-text-o",
    "Clientes": "fa-users",
    "Actividades": "fa-bell-o",
    "Inventario": "fa-cubes",
    "Reportes": "fa-bar-chart",
    "Configuración": "fa-cog",
};

const QUICK_ACTIONS = [
    { label: "Nueva recepción", icon: "fa-plus-circle", xmlid: "taller.action_taller_counter" },
    { label: "Mi trabajo", icon: "fa-wrench", xmlid: "taller.action_taller_tech" },
    { label: "Calendario de entregas", icon: "fa-calendar", xmlid: "taller.action_taller_calendar" },
    { label: "Tablero para TV", icon: "fa-tv", xmlid: "taller.action_taller_tv" },
];

class TallerShell extends Component {
    setup() {
        this.menu = useService("menu");
        this.action = useService("action");
        this.orm = useService("orm");
        this.state = useState({
            visible: false,
            collapsed: localStorage.getItem(STORAGE_KEY) === "1",
            open: {},
            tick: 0,
            search: { open: false, query: "", orders: [], partners: [], index: 0 },
        });
        this.searchTimer = null;
        this.sync = () => this.syncShell();
        this.onKey = (ev) => this.handleGlobalKey(ev);
        onMounted(() => {
            this.sync();
            this.poll = setInterval(this.sync, 1500);
            this.env.bus.addEventListener("MENUS:APP-CHANGED", this.sync);
            this.env.bus.addEventListener("ACTION_MANAGER:UI-UPDATED", this.sync);
            window.addEventListener("keydown", this.onKey, true);
        });
        onWillUnmount(() => {
            clearInterval(this.poll);
            clearTimeout(this.searchTimer);
            this.env.bus.removeEventListener("MENUS:APP-CHANGED", this.sync);
            this.env.bus.removeEventListener("ACTION_MANAGER:UI-UPDATED", this.sync);
            window.removeEventListener("keydown", this.onKey, true);
            document.body.classList.remove("o_taller_shell", "o_taller_shell_collapsed");
        });
    }

    // ------------------------------------------------------------ visibilidad
    syncShell() {
        const app = this.menu.getCurrentApp();
        const visible = !!app && (app.xmlid === "taller.menu_taller_root" || app.name === "Taller");
        if (visible !== this.state.visible) {
            this.state.visible = visible;
        }
        document.body.classList.toggle("o_taller_shell", visible);
        document.body.classList.toggle("o_taller_shell_collapsed", visible && this.state.collapsed);
        const nav = document.querySelector(".o_main_navbar");
        if (nav) {
            document.documentElement.style.setProperty("--ts-top", `${nav.offsetHeight}px`);
        }
        this.state.tick += 1;
    }

    toggleCollapsed() {
        this.state.collapsed = !this.state.collapsed;
        localStorage.setItem(STORAGE_KEY, this.state.collapsed ? "1" : "0");
        this.syncShell();
    }

    // ------------------------------------------------------------ menú
    iconFor(item) {
        return ICONS_BY_XMLID[item.xmlid] || ICONS_BY_NAME[item.name] || "fa-circle-o";
    }

    childrenOf(node) {
        if (node.childrenTree) {
            return node.childrenTree;
        }
        return (node.children || []).map((child) =>
            typeof child === "object" ? child : this.menu.getMenuAsTree(child)
        );
    }

    get items() {
        const app = this.menu.getCurrentApp();
        if (!app) {
            return [];
        }
        const tree = this.menu.getMenuAsTree(app.id);
        return this.childrenOf(tree).map((item) => ({
            id: item.id,
            name: item.name,
            xmlid: item.xmlid,
            actionID: item.actionID,
            icon: this.iconFor(item),
            children: this.childrenOf(item).map((child) => ({
                id: child.id,
                name: child.name,
                xmlid: child.xmlid,
                actionID: child.actionID,
            })),
        }));
    }

    isActive(item) {
        const controller = this.action.currentController;
        const current = controller && controller.action && controller.action.id;
        return !!item.actionID && item.actionID === current;
    }

    isGroupActive(item) {
        return item.children.some((child) => this.isActive(child));
    }

    isOpen(item) {
        return this.state.open[item.id] === undefined
            ? this.isGroupActive(item)
            : this.state.open[item.id];
    }

    clickItem(item) {
        if (item.children.length) {
            this.state.open[item.id] = !this.isOpen(item);
        } else {
            this.menu.selectMenu(item.id);
        }
    }

    clickChild(child) {
        this.menu.selectMenu(child.id);
    }

    // ------------------------------------------------------------ búsqueda global
    handleGlobalKey(ev) {
        if (!this.state.visible) {
            return;
        }
        if ((ev.ctrlKey || ev.metaKey) && ev.key && ev.key.toLowerCase() === "k") {
            ev.preventDefault();
            ev.stopPropagation();
            this.state.search.open ? this.closeSearch() : this.openSearch();
        }
    }

    openSearch() {
        Object.assign(this.state.search, { open: true, query: "", orders: [], partners: [], index: 0 });
        setTimeout(() => {
            const input = document.querySelector(".ts-search-input");
            if (input) {
                input.focus();
            }
        }, 30);
    }

    closeSearch() {
        this.state.search.open = false;
    }

    onQuery(ev) {
        this.state.search.query = ev.target.value;
        this.state.search.index = 0;
        clearTimeout(this.searchTimer);
        this.searchTimer = setTimeout(() => this.runSearch(), 200);
    }

    async runSearch() {
        const query = this.state.search.query.trim();
        if (query.length < 2) {
            this.state.search.orders = [];
            this.state.search.partners = [];
            return;
        }
        const result = await this.orm.call("service.order", "global_search", [query]);
        this.state.search.orders = result.orders;
        this.state.search.partners = result.partners;
    }

    get results() {
        const search = this.state.search;
        if (search.query.trim().length < 2) {
            return QUICK_ACTIONS.map((q) => ({
                kind: "quick", icon: q.icon, label: q.label, sub: "Acceso rápido", xmlid: q.xmlid,
            }));
        }
        const list = [];
        for (const o of search.orders) {
            list.push({
                kind: "order", id: o.id, icon: "fa-wrench", label: `${o.name} · ${o.customer}`,
                sub: [o.device, o.serial, o.status_label].filter(Boolean).join(" · "),
            });
        }
        for (const p of search.partners) {
            list.push({ kind: "partner", id: p.id, icon: "fa-user", label: p.name, sub: p.phone || "Cliente" });
        }
        return list;
    }

    onSearchKey(ev) {
        const total = this.results.length;
        if (ev.key === "ArrowDown") {
            ev.preventDefault();
            this.state.search.index = (this.state.search.index + 1) % Math.max(total, 1);
        } else if (ev.key === "ArrowUp") {
            ev.preventDefault();
            this.state.search.index = (this.state.search.index - 1 + total) % Math.max(total, 1);
        } else if (ev.key === "Enter") {
            ev.preventDefault();
            const chosen = this.results[this.state.search.index];
            if (chosen) {
                this.run(chosen);
            }
        } else if (ev.key === "Escape") {
            this.closeSearch();
        }
    }

    run(result) {
        this.closeSearch();
        if (result.kind === "quick") {
            this.action.doAction(result.xmlid);
        } else if (result.kind === "order") {
            this.openOrder(result.id);
        } else if (result.kind === "partner") {
            this.action.doAction({
                type: "ir.actions.act_window",
                res_model: "res.partner",
                res_id: result.id,
                views: [[false, "form"]],
                target: "current",
            });
        }
    }

    openOrder(id) {
        if (registry.category("actions").contains("taller.ficha")) {
            this.action.doAction({ type: "ir.actions.client", tag: "taller.ficha", params: { id } });
        } else {
            this.action.doAction({
                type: "ir.actions.act_window",
                res_model: "service.order",
                res_id: id,
                views: [[false, "form"]],
                target: "current",
            });
        }
    }
}

TallerShell.template = "taller.Shell";

registry.category("main_components").add("TallerShell", { Component: TallerShell });
