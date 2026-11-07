/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { initials, avatarColor, deviceIcon } from "@taller/common/ui";

const EMPTY = { name: "", phone: "", email: "", street: "", city: "", vat: "", comment: "" };

class TallerClientes extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        const act = this.props.action || {};
        const params = act.params || {};
        this.notification = useService("notification");
        this.initials = initials;
        this.avatarColor = avatarColor;
        this.deviceIcon = deviceIcon;
        this.state = useState({
            editing: false,
            form: { ...EMPTY },
            list: { rows: [], symbol: "" },
            search: "",
            detail: null,
            partnerId: params.id || null,
        });
        this.timer = null;
        onWillStart(async () => {
            if (params.new) {
                this.state.editing = true;
                await this.loadList();
            } else if (this.state.partnerId) {
                await this.loadDetail();
            } else {
                await this.loadList();
            }
        });
        onWillUnmount(() => clearTimeout(this.timer));
    }

    async loadList() {
        this.state.list = await this.orm.call("service.order", "clientes_list", [this.state.search]);
    }

    async loadDetail() {
        this.state.detail = await this.orm.call("service.order", "cliente_get", [this.state.partnerId]);
    }

    onSearch(ev) {
        this.state.search = ev.target.value;
        clearTimeout(this.timer);
        this.timer = setTimeout(() => this.loadList(), 300);
    }

    money(value) {
        const symbol = (this.state.detail && this.state.detail.symbol) || this.state.list.symbol || "";
        const number = new Intl.NumberFormat("es-UY", { maximumFractionDigits: 0 }).format(value || 0);
        return `${symbol} ${number}`.trim();
    }

    async open(row) {
        this.state.partnerId = row.id;
        await this.loadDetail();
    }

    async back() {
        this.state.partnerId = null;
        this.state.detail = null;
        await this.loadList();
    }

    openOrder(order) {
        this.action.doAction({ type: "ir.actions.client", tag: "taller.ficha", params: { id: order.id }, name: order.name });
    }

    editPartner() {
        const c = this.state.detail;
        this.state.form = {
            name: c.name, phone: c.phone, email: c.email, street: c.street,
            city: c.city, vat: c.vat, comment: c.comment,
        };
        this.state.editing = true;
    }

    newPartner() {
        this.state.form = { ...EMPTY };
        this.state.partnerId = null;
        this.state.detail = null;
        this.state.editing = true;
    }

    cancelEdit() {
        this.state.editing = false;
    }

    async saveForm() {
        const form = this.state.form;
        if (!form.name.trim()) {
            this.notification.add("Escribí el nombre del cliente.", { type: "warning" });
            return;
        }
        const id = await this.orm.call("service.order", "cliente_save", [this.state.partnerId || false, { ...form }]);
        this.state.editing = false;
        this.state.partnerId = id;
        await this.loadDetail();
        this.notification.add("Cliente guardado.", { type: "success" });
    }

    newOrder() {
        this.action.doAction("taller.action_taller_counter");
    }

    openUrl(url) {
        if (url) {
            window.open(url, "_blank");
        }
    }
}

TallerClientes.template = "taller.Clientes";

registry.category("actions").add("taller.clientes", TallerClientes);
