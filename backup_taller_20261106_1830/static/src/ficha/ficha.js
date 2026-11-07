/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, onMounted, onWillUnmount, useState, useRef } from "@odoo/owl";

const TABS = [
    { key: "lines", label: "Repuestos y costos", icon: "fa-cubes" },
    { key: "payments", label: "Pagos", icon: "fa-money" },
    { key: "checks", label: "Checklist", icon: "fa-check-square-o" },
    { key: "photos", label: "Fotos", icon: "fa-camera" },
    { key: "timeline", label: "Historial", icon: "fa-history" },
];
const RESULT_CYCLE = ["untested", "ok", "fail", "na"];
const RESULT_LABEL = { untested: "Sin probar", ok: "Funciona", fail: "No funciona", na: "No aplica" };
const METHODS = [
    { key: "cash", label: "Efectivo" },
    { key: "transfer", label: "Transferencia" },
    { key: "card", label: "Tarjeta" },
    { key: "other", label: "Otro" },
];

function readAsDataURL(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = reject;
        reader.readAsDataURL(file);
    });
}

function loadImage(src) {
    return new Promise((resolve, reject) => {
        const img = new Image();
        img.onload = () => resolve(img);
        img.onerror = reject;
        img.src = src;
    });
}

async function fileToJpeg(file, maxSize = 1024, quality = 0.82) {
    const img = await loadImage(await readAsDataURL(file));
    const scale = Math.min(1, maxSize / Math.max(img.width, img.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(img.width * scale);
    canvas.height = Math.round(img.height * scale);
    canvas.getContext("2d").drawImage(img, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL("image/jpeg", quality);
}

class TallerFicha extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.cameraRef = useRef("cameraInput");
        this.galleryRef = useRef("galleryInput");
        this.tabs = TABS;
        this.methods = METHODS;
        this.resultLabel = RESULT_LABEL;
        const act = this.props.action || {};
        const params = act.params || {};
        const context = act.context || {};
        this.orderId = params.id || context.active_id || null;
        this.state = useState({
            data: null,
            missing: false,
            tab: "lines",
            busy: false,
            partQuery: "",
            parts: [],
            qty: 1,
            labor: "",
            payment: { amount: "", method: "cash", note: "" },
            note: "",
        });
        this.edit = useState({
            problem: "", condition: "", brand: "", model: "", serial: "",
            accessories: "", promise: "", user_id: "",
        });
        this.dirty = {};
        this.timer = null;
        this.partTimer = null;
        this.onLive = () => {
            clearTimeout(this.timer);
            this.timer = setTimeout(() => this.load(true), 700);
        };
        onWillStart(async () => {
            if (!this.orderId) {
                this.state.missing = true;
                return;
            }
            await this.load();
        });
        onMounted(() => window.addEventListener("taller-refresh", this.onLive));
        onWillUnmount(() => {
            window.removeEventListener("taller-refresh", this.onLive);
            clearTimeout(this.timer);
            clearTimeout(this.partTimer);
        });
    }

    // ------------------------------------------------------------ carga
    async load(silent = false) {
        try {
            this.state.data = await this.orm.call("service.order", "ficha_get", [this.orderId]);
        } catch (e) {
            if (!silent) {
                throw e;
            }
            return;
        }
        this.syncEdit();
        if (!this.dirty.labor) {
            this.state.labor = this.state.data.labor ? String(this.state.data.labor) : "";
        }
    }

    syncEdit() {
        const d = this.state.data;
        const map = {
            problem: d.problem,
            condition: d.condition,
            brand: d.device.brand,
            model: d.device.model,
            serial: d.device.serial,
            accessories: d.device.accessories,
            promise: d.promise_date,
            user_id: d.user.id ? String(d.user.id) : "",
        };
        for (const [key, value] of Object.entries(map)) {
            if (!this.dirty[key]) {
                this.edit[key] = value;
            }
        }
    }

    markDirty(key) {
        this.dirty[key] = true;
    }

    async saveField(key, field) {
        if (!this.dirty[key]) {
            return;
        }
        await this.orm.call("service.order", "ficha_write", [this.orderId, { [field]: this.edit[key] }]);
        this.dirty[key] = false;
        await this.load(true);
    }

    async saveSelect(key, field) {
        this.dirty[key] = true;
        await this.saveField(key, field);
    }

    money(value) {
        const number = new Intl.NumberFormat("es-UY", { maximumFractionDigits: 0 }).format(value || 0);
        return `${this.state.data.symbol || ""} ${number}`.trim();
    }

    setTab(key) {
        this.state.tab = key;
    }

    // ------------------------------------------------------------ navegación y documentos
    goBoard() {
        this.action.doAction("taller.action_taller_board");
    }

    openClassic() {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "service.order",
            res_id: this.orderId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    printReport(reportName) {
        this.action.doAction({
            type: "ir.actions.report",
            report_type: "qweb-pdf",
            report_name: reportName,
            report_file: reportName,
            display_name: "Documento",
            context: { active_ids: [this.orderId], active_id: this.orderId, active_model: "service.order" },
        });
    }

    printOrder() {
        this.printReport("taller.report_service_order");
    }

    printLabel() {
        this.printReport("taller.report_label");
    }

    openUrl(url) {
        if (url) {
            window.open(url, "_blank");
        } else {
            this.notification.add("El cliente no tiene teléfono cargado.", { type: "warning" });
        }
    }

    async copyLink() {
        const url = this.state.data.links.public_url;
        try {
            await navigator.clipboard.writeText(url);
            this.notification.add("Enlace copiado.", { type: "success" });
        } catch (e) {
            window.prompt("Copia el enlace:", url);
        }
    }

    // ------------------------------------------------------------ flujo
    async runAction(key) {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        let popup = null;
        if (key === "send_quote" && this.state.data.links.wa_url) {
            popup = window.open("about:blank", "_blank");
        }
        try {
            await this.orm.call("service.order", "tech_action", [this.orderId, key]);
            await this.load(true);
            this.notification.add("Estado actualizado.", { type: "success" });
            if (popup) {
                popup.location = this.state.data.links.wa_url;
            }
        } catch (e) {
            if (popup) {
                popup.close();
            }
            throw e;
        } finally {
            this.state.busy = false;
        }
    }

    async createInvoice() {
        const result = await this.orm.call("service.order", "action_create_invoice", [[this.orderId]]);
        if (result && result.type) {
            await this.action.doAction(result);
        }
    }

    async openInvoice() {
        const result = await this.orm.call("service.order", "action_view_invoice", [[this.orderId]]);
        if (result && result.type) {
            await this.action.doAction(result);
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
        await this.orm.call("service.order", "tech_add_line", [this.orderId, part.id, this.state.qty || 1]);
        this.state.parts = [];
        this.state.partQuery = "";
        this.state.qty = 1;
        await this.load(true);
    }

    async removeLine(line) {
        await this.orm.call("service.order", "tech_remove_line", [line.id]);
        await this.load(true);
    }

    async saveLabor() {
        await this.orm.call("service.order", "tech_set_labor", [
            this.orderId,
            parseFloat(this.state.labor) || 0,
        ]);
        this.dirty.labor = false;
        this.notification.add("Mano de obra guardada.", { type: "success" });
        await this.load(true);
    }

    // ------------------------------------------------------------ pagos
    fillBalance() {
        this.state.payment.amount = String(this.state.data.balance || "");
    }

    async addPayment() {
        const p = this.state.payment;
        await this.orm.call("service.order", "ficha_add_payment", [
            this.orderId, parseFloat(p.amount) || 0, p.method, p.note,
        ]);
        this.state.payment = { amount: "", method: "cash", note: "" };
        this.notification.add("Pago registrado.", { type: "success" });
        await this.load(true);
    }

    // ------------------------------------------------------------ checklist
    async cycleCheck(check) {
        const index = RESULT_CYCLE.indexOf(check.result);
        check.result = RESULT_CYCLE[(index + 1) % RESULT_CYCLE.length];
        await this.orm.call("service.order", "ficha_check", [check.id, check.result]);
    }

    // ------------------------------------------------------------ fotos
    pickCamera() {
        this.cameraRef.el.click();
    }

    pickGallery() {
        this.galleryRef.el.click();
    }

    async onPhotos(ev) {
        const files = Array.from(ev.target.files || []);
        for (const file of files) {
            try {
                const data = await fileToJpeg(file);
                await this.orm.call("service.order", "ficha_add_photo", [
                    this.orderId, file.name || "Foto", data, "intake",
                ]);
            } catch (e) {
                this.notification.add("No se pudo subir una de las fotos.", { type: "danger" });
            }
        }
        ev.target.value = "";
        await this.load(true);
    }

    // ------------------------------------------------------------ historial
    onNoteKey(ev) {
        if (ev.key === "Enter") {
            this.addNote();
        }
    }

    async addNote() {
        if (!this.state.note.trim()) {
            return;
        }
        await this.orm.call("service.order", "ficha_add_note", [this.orderId, this.state.note]);
        this.state.note = "";
        await this.load(true);
    }
}

TallerFicha.template = "taller.Ficha";

registry.category("actions").add("taller.ficha", TallerFicha);
