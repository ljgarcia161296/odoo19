/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, onWillUnmount, useState, useRef, useEffect } from "@odoo/owl";

const DEVICE_TYPES = [
    { key: "phone", label: "Celular", icon: "fa-mobile" },
    { key: "computer", label: "Computadora", icon: "fa-laptop" },
    { key: "tablet", label: "Tablet", icon: "fa-tablet" },
    { key: "other", label: "Otro", icon: "fa-cube" },
];
const RESULT_CYCLE = ["untested", "ok", "fail", "na"];
const RESULT_LABEL = { untested: "Sin probar", ok: "Funciona", fail: "No funciona", na: "No aplica" };
const STEPS = ["Cliente", "Equipo y problema", "Checklist y fotos", "Firma y confirmar"];

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

class TallerCounter extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.sigRef = useRef("sigCanvas");
        this.cameraRef = useRef("cameraInput");
        this.galleryRef = useRef("galleryInput");
        this.deviceTypes = DEVICE_TYPES;
        this.steps = STEPS;
        this.resultLabel = RESULT_LABEL;
        this.searchTimer = null;
        this.signatureData = null;
        this.drawing = false;
        this.state = useState(this.freshState());

        onWillStart(async () => {
            const init = await this.orm.call("service.order", "counter_init", []);
            this.state.isManager = init.is_manager;
            this.state.users = init.users;
            this.state.form.user_id = init.uid;
            await this.loadChecklist();
        });
        useEffect(
            () => {
                if (this.state.step === 4 && !this.state.done) {
                    this.setupCanvas();
                }
            },
            () => [this.state.step, this.state.done]
        );
        onWillUnmount(() => clearTimeout(this.searchTimer));
    }

    freshState() {
        return {
            step: 1,
            query: "",
            partners: [],
            devices: [],
            partner: null,
            showNew: false,
            newCustomer: { name: "", phone: "" },
            form: {
                device_type: "phone",
                brand: "",
                model: "",
                serial: "",
                accessories: "",
                problem: "",
                condition: "",
                promise_date: "",
                user_id: false,
            },
            history: null,
            checks: [],
            photos: [],
            isManager: false,
            users: [],
            saving: false,
            done: null,
        };
    }

    // ------------------------------------------------------------ navegación
    stepClass(index) {
        const number = index + 1;
        if (number === this.state.step) {
            return "tc-step active";
        }
        return number < this.state.step ? "tc-step done" : "tc-step";
    }

    get canNext() {
        if (this.state.step === 1) {
            return !!this.state.partner;
        }
        if (this.state.step === 2) {
            return !!this.state.form.problem.trim();
        }
        return true;
    }

    next() {
        if (this.canNext && this.state.step < 4) {
            this.state.step += 1;
        }
    }

    back() {
        if (this.state.step > 1) {
            this.state.step -= 1;
        }
    }

    // ------------------------------------------------------------ cliente
    onQuery(ev) {
        this.state.query = ev.target.value;
        clearTimeout(this.searchTimer);
        this.searchTimer = setTimeout(() => this.search(), 300);
    }

    async search() {
        const result = await this.orm.call("service.order", "counter_search", [this.state.query]);
        this.state.partners = result.partners;
        this.state.devices = result.devices;
    }

    selectPartner(partner) {
        this.state.partner = partner;
        this.state.showNew = false;
    }

    selectDevice(device) {
        this.state.partner = {
            id: device.partner_id,
            name: device.partner_name,
            phone: device.partner_phone,
        };
        this.state.form.device_type = device.device_type;
        this.state.form.brand = device.brand;
        this.state.form.model = device.model;
        this.state.form.serial = device.serial;
        this.loadChecklist();
        this.loadHistory();
    }

    clearPartner() {
        this.state.partner = null;
    }

    toggleNew() {
        this.state.showNew = !this.state.showNew;
    }

    async createCustomer() {
        const { name, phone } = this.state.newCustomer;
        const partner = await this.orm.call("service.order", "counter_create_partner", [name, phone]);
        this.selectPartner(partner);
        this.state.newCustomer = { name: "", phone: "" };
    }

    // ------------------------------------------------------------ equipo
    async setType(key) {
        this.state.form.device_type = key;
        await this.loadChecklist();
    }

    async loadHistory() {
        const serial = this.state.form.serial.trim();
        this.state.history = serial
            ? await this.orm.call("service.order", "counter_history", [serial])
            : null;
    }

    async loadChecklist() {
        const items = await this.orm.call("service.order", "counter_checklist", [
            this.state.form.device_type,
        ]);
        this.state.checks = items.map((item) => ({ ...item, result: "untested" }));
    }

    cycle(check) {
        const index = RESULT_CYCLE.indexOf(check.result);
        check.result = RESULT_CYCLE[(index + 1) % RESULT_CYCLE.length];
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
            if (this.state.photos.length >= 8) {
                this.notification.add("Máximo 8 fotos por orden.", { type: "warning" });
                break;
            }
            try {
                const data = await fileToJpeg(file);
                this.state.photos.push({ name: `Foto ${this.state.photos.length + 1}`, data });
            } catch (e) {
                this.notification.add("No se pudo leer una de las fotos.", { type: "danger" });
            }
        }
        ev.target.value = "";
    }

    removePhoto(index) {
        this.state.photos.splice(index, 1);
    }

    // ------------------------------------------------------------ firma
    setupCanvas() {
        const canvas = this.sigRef.el;
        if (!canvas) {
            return;
        }
        const ratio = window.devicePixelRatio || 1;
        const rect = canvas.getBoundingClientRect();
        canvas.width = Math.max(1, Math.round(rect.width * ratio));
        canvas.height = Math.max(1, Math.round(rect.height * ratio));
        const ctx = canvas.getContext("2d");
        ctx.scale(ratio, ratio);
        ctx.lineWidth = 2.4;
        ctx.lineCap = "round";
        ctx.lineJoin = "round";
        ctx.strokeStyle = "#0f4c5c";
        this.ctx = ctx;
        if (this.signatureData) {
            loadImage(this.signatureData).then((img) => ctx.drawImage(img, 0, 0, rect.width, rect.height));
        }
    }

    sigDown(ev) {
        if (!this.ctx) {
            return;
        }
        this.drawing = true;
        this.sigRef.el.setPointerCapture(ev.pointerId);
        this.ctx.beginPath();
        this.ctx.moveTo(ev.offsetX, ev.offsetY);
    }

    sigMove(ev) {
        if (!this.drawing) {
            return;
        }
        this.ctx.lineTo(ev.offsetX, ev.offsetY);
        this.ctx.stroke();
    }

    sigUp() {
        if (!this.drawing) {
            return;
        }
        this.drawing = false;
        this.signatureData = this.sigRef.el.toDataURL("image/png");
    }

    clearSignature() {
        const canvas = this.sigRef.el;
        if (canvas && this.ctx) {
            const rect = canvas.getBoundingClientRect();
            this.ctx.clearRect(0, 0, rect.width, rect.height);
        }
        this.signatureData = null;
    }

    // ------------------------------------------------------------ guardar
    get summary() {
        const f = this.state.form;
        const type = DEVICE_TYPES.find((t) => t.key === f.device_type);
        return {
            type: type ? type.label : "",
            device: [f.brand, f.model].filter(Boolean).join(" ") || "—",
            failed: this.state.checks.filter((c) => c.result === "fail").length,
            tested: this.state.checks.filter((c) => c.result !== "untested").length,
        };
    }

    async submit() {
        if (this.state.saving) {
            return;
        }
        this.state.saving = true;
        try {
            const f = this.state.form;
            const result = await this.orm.call("service.order", "counter_create", [
                {
                    partner_id: this.state.partner.id,
                    device_type: f.device_type,
                    brand: f.brand,
                    model: f.model,
                    serial: f.serial,
                    accessories: f.accessories,
                    problem: f.problem,
                    condition: f.condition,
                    promise_date: f.promise_date || false,
                    user_id: f.user_id || false,
                    checks: this.state.checks.map((c) => ({ item_id: c.item_id, result: c.result })),
                    photos: this.state.photos,
                    signature: this.signatureData,
                },
            ]);
            this.state.done = result;
        } finally {
            this.state.saving = false;
        }
    }

    // ------------------------------------------------------------ después de crear
    printReport(reportName) {
        const id = this.state.done.id;
        this.action.doAction({
            type: "ir.actions.report",
            report_type: "qweb-pdf",
            report_name: reportName,
            report_file: reportName,
            display_name: "Documento",
            context: { active_ids: [id], active_id: id, active_model: "service.order" },
        });
    }

    printLabel() {
        this.printReport("taller.report_label");
    }

    printOrder() {
        this.printReport("taller.report_service_order");
    }

    openOrder() {
        this.action.doAction({
            type: "ir.actions.client",
            tag: "taller.ficha",
            params: { id: this.state.done.id },
        });
    }

    reset() {
        this.signatureData = null;
        const manager = this.state.isManager;
        const users = this.state.users;
        const uid = this.state.form.user_id;
        Object.assign(this.state, this.freshState());
        this.state.isManager = manager;
        this.state.users = users;
        this.state.form.user_id = uid;
        this.loadChecklist();
    }
}

TallerCounter.template = "taller.Counter";

registry.category("actions").add("taller.counter", TallerCounter);
