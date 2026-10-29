/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, onMounted, onWillUnmount, useState } from "@odoo/owl";

class TallerDashboard extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ data: null, shown: [], barsReady: false });
        this.frame = null;
        onWillStart(async () => {
            await this.load();
        });
        onMounted(() => {
            setTimeout(() => {
                this.state.barsReady = true;
            }, 80);
            this.countUp();
        });
        onWillUnmount(() => {
            if (this.frame) {
                cancelAnimationFrame(this.frame);
            }
        });
    }

    async load() {
        const data = await this.orm.call("service.order", "get_dashboard_data", []);
        this.state.data = data;
        this.state.shown = data.kpis.map(() => 0);
    }

    async refresh() {
        this.state.barsReady = false;
        await this.load();
        setTimeout(() => {
            this.state.barsReady = true;
        }, 80);
        this.countUp();
    }

    get greeting() {
        const hour = new Date().getHours();
        if (hour < 12) {
            return "Buenos días";
        }
        return hour < 20 ? "Buenas tardes" : "Buenas noches";
    }

    countUp() {
        if (this.frame) {
            cancelAnimationFrame(this.frame);
        }
        const kpis = this.state.data.kpis;
        const start = performance.now();
        const duration = 900;
        const tick = (now) => {
            const progress = Math.min((now - start) / duration, 1);
            const eased = 1 - Math.pow(1 - progress, 3);
            this.state.shown = kpis.map((kpi) => kpi.value * eased);
            if (progress < 1) {
                this.frame = requestAnimationFrame(tick);
            }
        };
        this.frame = requestAnimationFrame(tick);
    }

    format(kpi, index) {
        const value = this.state.shown[index] || 0;
        if (kpi.money) {
            const number = new Intl.NumberFormat("es-UY", { maximumFractionDigits: 0 }).format(value);
            return (kpi.symbol || "") + " " + number;
        }
        if (kpi.decimals) {
            return value.toFixed(kpi.decimals) + (kpi.suffix || "");
        }
        return String(Math.round(value)) + (kpi.suffix || "");
    }

    openList(name, model, domain) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: name,
            res_model: model,
            views: [[false, "list"], [false, "form"]],
            domain: domain,
            target: "current",
        });
    }

    openKpi(kpi) {
        this.openList(kpi.label, kpi.model, kpi.domain);
    }

    openStage(stage) {
        this.openList(stage.label, "service.order", stage.domain);
    }

    openOrder(id) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "service.order",
            res_id: id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    newOrder() {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "service.order",
            views: [[false, "form"]],
            target: "current",
        });
    }

    goTo(xmlid) {
        this.action.doAction(xmlid);
    }
}

TallerDashboard.template = "taller.Dashboard";

registry.category("actions").add("taller.dashboard", TallerDashboard);