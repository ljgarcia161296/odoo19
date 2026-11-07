/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, onMounted, onWillUnmount, useState } from "@odoo/owl";

class TallerBoard extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.peekTimer = null;
        this.state = useState({
            data: { columns: [], symbol: "" },
            search: "",
            mine: false,
            late: false,
            tech: 0,
            loading: true,
            peek: null,
            dragId: null,
            overKey: null,
            view: (() => {
                try {
                    return localStorage.getItem("taller.board.view") === "list" ? "list" : "cols";
                } catch (e) {
                    return "cols";
                }
            })(),
            sort: "days",
            sortDir: -1,
        });
        this.searchTimer = null;
        this.liveTimer = null;
        this.onLive = () => {
            clearTimeout(this.liveTimer);
            this.liveTimer = setTimeout(() => this.load(), 600);
        };
        onMounted(async () => {
            await this.load();
            this.state.loading = false;
        });
        this.onKey = (ev) => this.handleKey(ev);
        onMounted(() => {
            window.addEventListener("taller-refresh", this.onLive);
            window.addEventListener("keydown", this.onKey);
        });
        onWillUnmount(() => {
            window.removeEventListener("taller-refresh", this.onLive);
            window.removeEventListener("keydown", this.onKey);
            clearTimeout(this.searchTimer);
            clearTimeout(this.liveTimer);
            clearTimeout(this.peekTimer);
        });
    }

    async load() {
        this.state.data = await this.orm.call("service.order", "board_data", [
            this.state.search,
            this.state.mine,
            this.state.late,
            this.state.tech || false,
        ]);
    }

    onSearch(ev) {
        this.state.search = ev.target.value;
        clearTimeout(this.searchTimer);
        this.searchTimer = setTimeout(() => this.load(), 300);
    }

    handleKey(ev) {
        const tag = (ev.target && ev.target.tagName) || "";
        if (["INPUT", "TEXTAREA", "SELECT"].includes(tag) || (ev.target && ev.target.isContentEditable)) {
            return;
        }
        if (ev.ctrlKey || ev.metaKey || ev.altKey || document.querySelector(".modal.show, .ts-overlay")) {
            return;
        }
        const key = ev.key.toLowerCase();
        if (key === "/") {
            const input = document.querySelector(".o_taller_board .tb-search input");
            if (input) {
                ev.preventDefault();
                input.focus();
            }
        } else if (key === "n") {
            this.newOrder();
        } else if (key === "m") {
            this.toggleMine();
        } else if (key === "l") {
            this.toggleLate();
        }
    }

    setTech(id) {
        this.state.tech = id;
        this.state.mine = false;
        this.load();
    }

    columnLabel(key) {
        const col = this.state.data.columns.find((c) => c.key === key);
        return col ? col.label : key;
    }

    async moveCard(id, name, fromKey, toKey) {
        try {
            await this.orm.call("service.order", "board_move", [id, toKey]);
        } finally {
            await this.load();
        }
        const buttons = [];
        if (fromKey && fromKey !== toKey && toKey !== "delivered") {
            buttons.push({
                name: "Deshacer",
                primary: true,
                onClick: async () => {
                    try {
                        await this.orm.call("service.order", "board_move", [id, fromKey]);
                    } finally {
                        await this.load();
                    }
                },
            });
        }
        this.notification.add(`${name} pasó a "${this.columnLabel(toKey)}".`, {
            type: "success", buttons, autocloseDelay: 7000,
        });
    }

    async advance(card, fromKey) {
        this.hidePeek();
        await this.moveCard(card.id, card.name, fromKey, card.next_key);
    }

    showPeek(ev, card) {
        clearTimeout(this.peekTimer);
        const target = ev.currentTarget;
        this.peekTimer = setTimeout(() => {
            const root = document.querySelector(".o_taller_board");
            if (!root || !target.isConnected || this.state.dragId) {
                return;
            }
            const r = target.getBoundingClientRect();
            const base = root.getBoundingClientRect();
            let x = r.right - base.left + 10;
            if (x + 300 > base.width) {
                x = Math.max(8, r.left - base.left - 310);
            }
            const y = Math.max(8, Math.min(r.top - base.top, base.height - 240));
            this.state.peek = { card, x, y };
        }, 550);
    }

    hidePeek() {
        clearTimeout(this.peekTimer);
        this.state.peek = null;
    }

    toggleMine() {
        this.state.mine = !this.state.mine;
        this.load();
    }

    toggleLate() {
        this.state.late = !this.state.late;
        this.load();
    }

    money(value) {
        const number = new Intl.NumberFormat("es-UY", { maximumFractionDigits: 0 }).format(value || 0);
        return `${this.state.data.symbol || ""} ${number}`.trim();
    }

    // ------------------------------------------------------------ arrastrar y soltar
    dragStart(ev, card, col) {
        this.hidePeek();
        this._dragId = card.id;
        this._dragFrom = col ? col.key : null;
        this._dragName = card.name;
        ev.dataTransfer.setData("text/plain", String(card.id));
        ev.dataTransfer.effectAllowed = "move";
        // diferido: cambiar el DOM dentro de dragstart cancela el arrastre en Chrome
        setTimeout(() => {
            this.state.dragId = card.id;
        }, 0);
    }

    dragEnd() {
        this.state.dragId = null;
        this.state.overKey = null;
    }

    dragOver(ev, column) {
        ev.preventDefault();
        if (ev.dataTransfer) {
            ev.dataTransfer.dropEffect = "move";
        }
        if (this.state.overKey !== column.key) {
            this.state.overKey = column.key;
        }
    }

    dragLeave(ev, column) {
        const next = ev.relatedTarget;
        if (next && ev.currentTarget.contains(next)) {
            return;
        }
        if (this.state.overKey === column.key) {
            this.state.overKey = null;
        }
    }

    async drop(ev, column) {
        ev.preventDefault();
        let id = this._dragId || this.state.dragId;
        const raw = ev.dataTransfer && ev.dataTransfer.getData("text/plain");
        if (raw) {
            id = parseInt(raw, 10) || id;
        }
        this._dragId = null;
        this.state.dragId = null;
        this.state.overKey = null;
        if (!id) {
            return;
        }
        const from = this._dragFrom;
        const name = this._dragName || "La orden";
        if (from === column.key) {
            return;
        }
        await this.moveCard(id, name, from, column.key);
    }

    // ------------------------------------------------------------ navegación
    setView(view) {
        this.state.view = view;
        try {
            localStorage.setItem("taller.board.view", view);
        } catch (e) {
            // sin almacenamiento: la vista vale solo para esta sesion
        }
    }

    setSort(key) {
        if (this.state.sort === key) {
            this.state.sortDir = -this.state.sortDir;
        } else {
            this.state.sort = key;
            this.state.sortDir = key === "name" || key === "customer" ? 1 : -1;
        }
    }

    get listRows() {
        const rows = [];
        for (const col of this.state.data.columns) {
            for (const card of col.cards) {
                rows.push({ ...card, col_key: col.key, col_label: col.label });
            }
        }
        const key = this.state.sort;
        const dir = this.state.sortDir;
        return rows.sort((a, b) => {
            const x = a[key];
            const y = b[key];
            if (typeof x === "string" || typeof y === "string") {
                return dir * String(x || "").localeCompare(String(y || ""));
            }
            return dir * ((x || 0) - (y || 0));
        });
    }

    openCard(card) {
        this.action.doAction({
            type: "ir.actions.client",
            tag: "taller.ficha",
            params: { id: card.id },
            name: card.name,
        });
    }

    newOrder() {
        this.action.doAction("taller.action_taller_counter");
    }
}

TallerBoard.template = "taller.Board";

registry.category("actions").add("taller.board", TallerBoard);
