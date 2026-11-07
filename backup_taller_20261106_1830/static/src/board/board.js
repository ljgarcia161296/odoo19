/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, onMounted, onWillUnmount, useState } from "@odoo/owl";

class TallerBoard extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            data: { columns: [], symbol: "" },
            search: "",
            mine: false,
            late: false,
            dragId: null,
            overKey: null,
        });
        this.searchTimer = null;
        this.liveTimer = null;
        this.onLive = () => {
            clearTimeout(this.liveTimer);
            this.liveTimer = setTimeout(() => this.load(), 600);
        };
        onWillStart(() => this.load());
        onMounted(() => window.addEventListener("taller-refresh", this.onLive));
        onWillUnmount(() => {
            window.removeEventListener("taller-refresh", this.onLive);
            clearTimeout(this.searchTimer);
            clearTimeout(this.liveTimer);
        });
    }

    async load() {
        this.state.data = await this.orm.call("service.order", "board_data", [
            this.state.search,
            this.state.mine,
            this.state.late,
        ]);
    }

    onSearch(ev) {
        this.state.search = ev.target.value;
        clearTimeout(this.searchTimer);
        this.searchTimer = setTimeout(() => this.load(), 300);
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
    dragStart(ev, card) {
        this.state.dragId = card.id;
        ev.dataTransfer.setData("text/plain", String(card.id));
        ev.dataTransfer.effectAllowed = "move";
    }

    dragEnd() {
        this.state.dragId = null;
        this.state.overKey = null;
    }

    dragOver(ev, column) {
        ev.preventDefault();
        this.state.overKey = column.key;
    }

    async drop(ev, column) {
        ev.preventDefault();
        const id = this.state.dragId;
        this.state.dragId = null;
        this.state.overKey = null;
        if (!id) {
            return;
        }
        try {
            await this.orm.call("service.order", "board_move", [id, column.key]);
        } finally {
            await this.load();
        }
    }

    // ------------------------------------------------------------ navegación
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
