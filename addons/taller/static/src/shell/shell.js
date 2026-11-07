/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onMounted, onWillUnmount, useState, useRef } from "@odoo/owl";

import { TOUR, SHORTCUTS, helpFor } from "@taller/common/help";

const TOUR_KEY = "taller.tour.done";
const STORAGE_KEY = "taller.sidebar.collapsed";
const DARK_KEY = "taller.dark";
const THEME_KEY = "taller.theme";
const THEMES = [
    { key: "teal", color: "#0f4c5c", label: "Verde azulado" },
    { key: "blue", color: "#1f4e8c", label: "Azul" },
    { key: "green", color: "#1f6b43", label: "Verde" },
    { key: "violet", color: "#5b3fd1", label: "Violeta" },
];

function readTheme() {
    try {
        return localStorage.getItem(THEME_KEY) || "teal";
    } catch (e) {
        return "teal";
    }
}

function applyTheme(key) {
    const cl = document.documentElement.classList;
    THEMES.forEach((t) => cl.remove(`o_taller_theme_${t.key}`));
    if (key && key !== "teal") {
        cl.add(`o_taller_theme_${key}`);
    }
}

function readDark() {
    try {
        return localStorage.getItem(DARK_KEY) === "1";
    } catch (e) {
        return false;
    }
}

const ICONS_BY_XMLID = {
    "taller.menu_taller_home": "fa-home",
    "taller.menu_taller_counter": "fa-plus-circle",
    "taller.menu_taller_tech": "fa-wrench",
    "taller.menu_service_order": "fa-th-large",
    "taller.menu_taller_calendar": "fa-calendar",
    "taller.menu_taller_garantias": "fa-shield",
    "taller.menu_taller_panel": "fa-area-chart",
    "taller.menu_taller_mensajes": "fa-whatsapp",
    "taller.menu_taller_actividad": "fa-history",
    "taller.menu_taller_purchases": "fa-truck",
    "taller.menu_taller_config_ui": "fa-cog",
    "taller.menu_taller_to_invoice": "fa-file-text-o",
    "taller.menu_taller_clientes": "fa-users",
    "taller.menu_taller_activities": "fa-bell-o",
    "taller.menu_taller_inventory": "fa-cubes",
    "taller.menu_taller_reports": "fa-bar-chart",
    "taller.menu_taller_caja": "fa-money",
    "taller.menu_taller_finanzas": "fa-line-chart",
    "taller.menu_taller_venta": "fa-shopping-cart",
    "taller.menu_taller_inventario_ui": "fa-cubes",
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
    "Caja diaria": "fa-money",
    "Finanzas": "fa-line-chart",
    "Venta de mostrador": "fa-shopping-cart",
    "Inventario ágil": "fa-cubes",
    "Configuración": "fa-cog",
};

const COMMANDS = [
    { key: "new_order", label: "Nueva orden", icon: "fa-plus-circle", words: "nueva orden recepcion ingreso equipo", xmlid: "taller.action_taller_counter" },
    { key: "sale", label: "Venta de mostrador", icon: "fa-shopping-cart", words: "cobrar vender venta mostrador accesorio", xmlid: "taller.action_taller_venta" },
    { key: "board", label: "Tablero de órdenes", icon: "fa-th-large", words: "tablero ordenes kanban estados", xmlid: "taller.action_taller_board" },
    { key: "caja", label: "Caja diaria", icon: "fa-money", words: "caja diaria cobros arqueo", xmlid: "taller.action_taller_caja" },
    { key: "fin", label: "Finanzas", icon: "fa-line-chart", words: "finanzas comisiones gastos resultado ganancia", xmlid: "taller.action_taller_finanzas" },
    { key: "inv", label: "Inventario", icon: "fa-cubes", words: "inventario repuestos stock", xmlid: "taller.action_taller_inventario_ui" },
    { key: "clients", label: "Clientes", icon: "fa-users", words: "clientes lista", xmlid: "taller.action_taller_clientes_ui" },
    { key: "new_client", label: "Nuevo cliente", icon: "fa-user-plus", words: "nuevo cliente agregar alta", fn: "newClient" },
    { key: "calendar", label: "Calendario de entregas", icon: "fa-calendar", words: "calendario entregas fechas", xmlid: "taller.action_taller_calendar_ui" },
    { key: "purchases", label: "Compras a proveedores", icon: "fa-truck", words: "compras proveedores pedidos", xmlid: "taller.action_taller_compras_ui" },
    { key: "warranty", label: "Garantías", icon: "fa-shield", words: "garantias vencimientos reingreso", xmlid: "taller.action_taller_garantias_ui" },
    { key: "config", label: "Configuración del taller", icon: "fa-cog", words: "configuracion ajustes logo datos taller", xmlid: "taller.action_taller_config_ui" },
    { key: "panel", label: "Panel de gestión", icon: "fa-area-chart", words: "panel gestion graficos ingresos metas ranking alertas", xmlid: "taller.action_taller_panel_ui" },
    { key: "msgs", label: "Mensajes pendientes", icon: "fa-whatsapp", words: "mensajes whatsapp avisos pendientes posventa", xmlid: "taller.action_taller_mensajes_ui" },
    { key: "log", label: "Registro de actividad", icon: "fa-history", words: "actividad registro historial auditoria cambios", xmlid: "taller.action_taller_actividad_ui" },
    { key: "help", label: "Ayuda y recorrido", icon: "fa-question-circle", words: "ayuda tutorial recorrido tour atajos como se usa", fn: "openHelp" },
    { key: "dark", label: "Cambiar modo oscuro / claro", icon: "fa-moon-o", words: "modo oscuro claro tema noche", fn: "toggleDark" },
    { key: "scan", label: "Escanear QR de etiqueta", icon: "fa-qrcode", words: "escanear qr etiqueta camara", fn: "startScan" },
];

function normalize(text) {
    return (text || "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
}

const QUICK_ACTIONS = [
    { label: "Nueva recepción", icon: "fa-plus-circle", xmlid: "taller.action_taller_counter" },
    { label: "Mi trabajo", icon: "fa-wrench", xmlid: "taller.action_taller_tech" },
    { label: "Calendario de entregas", icon: "fa-calendar", xmlid: "taller.action_taller_calendar_ui" },
    { label: "Venta de mostrador", icon: "fa-shopping-cart", xmlid: "taller.action_taller_venta" },
    { label: "Caja diaria", icon: "fa-money", xmlid: "taller.action_taller_caja" },
    { label: "Tablero para TV", icon: "fa-tv", xmlid: "taller.action_taller_tv" },
];

class TallerShell extends Component {
    setup() {
        this.menu = useService("menu");
        this.action = useService("action");
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.bus = useService("bus_service");
        this.state = useState({
            visible: false,
            collapsed: localStorage.getItem(STORAGE_KEY) === "1",
            dark: readDark(),
            theme: readTheme(),
            canInstall: false,
            scan: { open: false, msg: "" },
            open: {},
            tick: 0,
            search: { open: false, query: "", orders: [], partners: [], index: 0 },
            help: { open: false, mode: "screen", step: 0 },
        });
        this.tour = TOUR;
        this.shortcuts = SHORTCUTS;
        this.searchTimer = null;
        this.themes = THEMES;
        this.videoRef = useRef("scanVideo");
        this.installEvent = null;
        this.stream = null;
        this.scanTimer = null;
        this.onInstall = (ev) => {
            ev.preventDefault();
            this.installEvent = ev;
            this.state.canInstall = true;
        };
        this.sync = () => this.syncShell();
        this.onKey = (ev) => this.handleGlobalKey(ev);
        onMounted(() => {
            document.documentElement.classList.toggle("o_taller_dark", this.state.dark);
            applyTheme(this.state.theme);
            this.sync();
            this.poll = setInterval(this.sync, 1500);
            this.env.bus.addEventListener("MENUS:APP-CHANGED", this.sync);
            this.env.bus.addEventListener("ACTION_MANAGER:UI-UPDATED", this.sync);
            try {
                this.bus.subscribe("taller_event", (payload) => this.onLiveEvent(payload));
                this.bus.start();
            } catch (e) {
                // sin bus: no hay avisos en vivo, el resto funciona igual
            }
            window.addEventListener("keydown", this.onKey, true);
            window.addEventListener("beforeinstallprompt", this.onInstall);
        });
        onWillUnmount(() => {
            clearInterval(this.poll);
            clearTimeout(this.searchTimer);
            this.env.bus.removeEventListener("MENUS:APP-CHANGED", this.sync);
            this.env.bus.removeEventListener("ACTION_MANAGER:UI-UPDATED", this.sync);
            window.removeEventListener("keydown", this.onKey, true);
            window.removeEventListener("beforeinstallprompt", this.onInstall);
            this.stopScan();
            document.body.classList.remove("o_taller_shell", "o_taller_shell_collapsed");
        });
    }

    // ------------------------------------------------------------ visibilidad
    syncShell() {
        const app = this.menu.getCurrentApp();
        const visible = !!app && (app.xmlid === "taller.menu_taller_root" || app.name === "Taller");
        if (visible !== this.state.visible) {
            this.state.visible = visible;
            if (visible) {
                this.maybeWelcome();
            }
        }
        document.body.classList.toggle("o_taller_shell", visible);
        document.body.classList.toggle("o_taller_shell_collapsed", visible && this.state.collapsed);
        const nav = document.querySelector(".o_main_navbar");
        if (nav) {
            document.documentElement.style.setProperty("--ts-top", `${nav.offsetHeight}px`);
        }
        this.state.tick += 1;
    }

    // ------------------------------------------------------------ avisos en vivo
    onLiveEvent(payload) {
        if (!payload) {
            return;
        }
        this.notification.add(payload.message || "", {
            title: payload.title || "Taller",
            type: payload.kind === "warning" ? "warning" : payload.kind === "success" ? "success" : "info",
            buttons: payload.id ? [{
                name: "Abrir",
                onClick: () => this.openOrder(payload.id),
            }] : [],
        });
        window.dispatchEvent(new CustomEvent("taller-refresh"));
    }

    // ------------------------------------------------------------ ayuda
    maybeWelcome() {
        let done = true;
        try {
            done = localStorage.getItem(TOUR_KEY) === "1";
        } catch (e) {
            done = true;
        }
        if (!done && !this.welcomed) {
            this.welcomed = true;
            this.state.help = { open: true, mode: "tour", step: 0 };
        }
    }

    get helpScreen() {
        const controller = this.action.currentController;
        const act = controller && controller.action;
        return helpFor(act && act.tag);
    }

    openHelp(mode = "screen") {
        this.state.help = { open: true, mode: typeof mode === "string" ? mode : "screen", step: 0 };
    }

    closeHelp() {
        if (this.state.help.mode === "tour") {
            try {
                localStorage.setItem(TOUR_KEY, "1");
            } catch (e) {
                // sin almacenamiento: el recorrido volverá a ofrecerse
            }
        }
        this.state.help.open = false;
    }

    helpStep(delta) {
        const next = this.state.help.step + delta;
        if (next >= this.tour.length) {
            this.closeHelp();
        } else if (next >= 0) {
            this.state.help.step = next;
        }
    }

    // ------------------------------------------------------------ app instalable y escaneo de QR
    async installApp() {
        if (!this.installEvent) {
            return;
        }
        this.installEvent.prompt();
        await this.installEvent.userChoice;
        this.installEvent = null;
        this.state.canInstall = false;
    }

    async startScan() {
        this.state.scan.open = true;
        this.state.scan.msg = "Apuntá la cámara al QR de la etiqueta.";
        if (!("BarcodeDetector" in window) || !navigator.mediaDevices) {
            this.state.scan.msg = "Este navegador no puede escanear aquí. Usá la cámara del celular y abrí el enlace del QR.";
            return;
        }
        try {
            this.stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
        } catch (e) {
            this.state.scan.msg = "No se pudo abrir la cámara. Revisá el permiso del navegador.";
            return;
        }
        setTimeout(() => {
            const video = this.videoRef.el;
            if (video) {
                video.srcObject = this.stream;
                video.play();
            }
        }, 50);
        const detector = new window.BarcodeDetector({ formats: ["qr_code"] });
        this.scanTimer = setInterval(async () => {
            const video = this.videoRef.el;
            if (!video || video.readyState < 2) {
                return;
            }
            try {
                const codes = await detector.detect(video);
                if (codes.length) {
                    this.onCode(codes[0].rawValue || "");
                }
            } catch (e) {
                // un cuadro que falla no detiene el escaneo
            }
        }, 350);
    }

    onCode(text) {
        const match = text.match(/[#&?]id=(\d+)/) || text.match(/\/(\d+)\/?$/);
        if (match && /service\.order|service_order|action-/.test(text)) {
            this.stopScan();
            this.openOrder(parseInt(match[1], 10));
        } else {
            this.state.scan.msg = "Ese QR no es de una orden del taller.";
        }
    }

    stopScan() {
        clearInterval(this.scanTimer);
        this.scanTimer = null;
        if (this.stream) {
            this.stream.getTracks().forEach((t) => t.stop());
            this.stream = null;
        }
        if (this.state && this.state.scan) {
            this.state.scan.open = false;
        }
    }

    setTheme(key) {
        this.state.theme = key;
        applyTheme(key);
        try {
            localStorage.setItem(THEME_KEY, key);
        } catch (e) {
            // sin almacenamiento: el tema vale solo para esta sesion
        }
    }

    toggleDark() {
        this.state.dark = !this.state.dark;
        document.documentElement.classList.toggle("o_taller_dark", this.state.dark);
        try {
            localStorage.setItem(DARK_KEY, this.state.dark ? "1" : "0");
        } catch (e) {
            // sin almacenamiento: el modo vale solo para esta sesion
        }
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
            return;
        }
        if (ev.key === "Escape" && this.state.help.open) {
            this.closeHelp();
            return;
        }
        const target = ev.target;
        const typing = target && (/^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName) || target.isContentEditable);
        if (ev.key === "?" && !typing && !ev.ctrlKey && !ev.metaKey) {
            this.state.help.open ? this.closeHelp() : this.openHelp();
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
        const text = search.query.trim();
        if (text.length < 1) {
            return QUICK_ACTIONS.map((q) => ({
                kind: "quick", icon: q.icon, label: q.label, sub: "Acceso rápido", xmlid: q.xmlid,
            }));
        }
        const tokens = normalize(text).split(/\s+/).filter(Boolean);
        const commands = COMMANDS.filter((c) => {
            const hay = normalize(`${c.label} ${c.words}`);
            return tokens.every((t) => hay.includes(t));
        }).slice(0, 6).map((c) => ({ kind: "cmd", cmd: c, icon: c.icon, label: c.label, sub: "Ir a / acción" }));
        if (text.length < 2) {
            return commands;
        }
        const list = [...commands];
        for (const o of search.orders) {
            list.push({
                kind: "order", id: o.id, icon: "fa-wrench", label: `${o.name} · ${o.customer}`,
                sub: [o.device, o.serial].filter(Boolean).join(" · "),
                status: o.status, pill: o.status_label,
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
        if (result.kind === "cmd") {
            if (result.cmd.xmlid) {
                this.action.doAction(result.cmd.xmlid);
            } else {
                this[result.cmd.fn]();
            }
        } else if (result.kind === "quick") {
            this.action.doAction(result.xmlid);
        } else if (result.kind === "order") {
            this.openOrder(result.id);
        } else if (result.kind === "partner") {
            this.action.doAction({ type: "ir.actions.client", tag: "taller.clientes", params: { id: result.id }, name: result.label });
        }
    }

    newClient() {
        this.action.doAction({ type: "ir.actions.client", tag: "taller.clientes", params: { new: true }, name: "Nuevo cliente" });
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
