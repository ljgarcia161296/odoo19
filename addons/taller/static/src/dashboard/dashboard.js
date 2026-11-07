/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, onMounted, onWillUnmount, useState } from "@odoo/owl";

const ORDER_KEY = "taller.dashboard.order";

function readOrder() {
    try {
        return JSON.parse(localStorage.getItem(ORDER_KEY) || "[]");
    } catch (e) {
        return [];
    }
}

class TallerDashboard extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ data: null, shown: [], barsReady: false, extra: null });
        this.frame = null;
        this.refreshTimer = null;
        this.onLive = () => {
            clearTimeout(this.refreshTimer);
            this.refreshTimer = setTimeout(() => this.silentRefresh(), 800);
        };
        onWillStart(async () => {
            await this.load();
        });
        onMounted(() => {
            setTimeout(() => {
                this.state.barsReady = true;
            }, 80);
            this.countUp();
            window.addEventListener("taller-refresh", this.onLive);
        });
        onWillUnmount(() => {
            if (this.frame) {
                cancelAnimationFrame(this.frame);
            }
            clearTimeout(this.refreshTimer);
            window.removeEventListener("taller-refresh", this.onLive);
        });
    }

    async load() {
        const data = await this.orm.call("service.order", "get_dashboard_data", []);
        this.applyOrder(data);
        this.state.data = data;
        this.state.shown = data.kpis.map(() => 0);
        try {
            this.state.extra = await this.orm.call("service.order", "dash_extra", []);
        } catch (e) {
            this.state.extra = null;
        }
    }

    applyOrder(data) {
        const order = readOrder();
        if (order.length) {
            const rank = (k) => (order.indexOf(k) === -1 ? 999 : order.indexOf(k));
            data.kpis.sort((a, b) => rank(a.key) - rank(b.key));
        }
    }

    kpiDragStart(kpi, ev) {
        this.dragKey = kpi.key;
        ev.dataTransfer.effectAllowed = "move";
        ev.dataTransfer.setData("text/plain", kpi.key);
    }

    kpiDrop(target, ev) {
        ev.preventDefault();
        const from = this.state.data.kpis.findIndex((k) => k.key === this.dragKey);
        const to = this.state.data.kpis.findIndex((k) => k.key === target.key);
        this.dragKey = null;
        if (from < 0 || to < 0 || from === to) {
            return;
        }
        const [moved] = this.state.data.kpis.splice(from, 1);
        this.state.data.kpis.splice(to, 0, moved);
        const [shown] = this.state.shown.splice(from, 1);
        this.state.shown.splice(to, 0, shown);
        try {
            localStorage.setItem(ORDER_KEY, JSON.stringify(this.state.data.kpis.map((k) => k.key)));
        } catch (e) {
            // sin almacenamiento: el orden vale solo para esta sesion
        }
    }

    moneyExtra(value) {
        const number = new Intl.NumberFormat("es-UY", { maximumFractionDigits: 0 }).format(value || 0);
        return `${this.state.extra ? this.state.extra.symbol : ""} ${number}`.trim();
    }

    get attentionCount() {
        const a = this.state.extra && this.state.extra.attention;
        return a ? a.late.length + a.waiting.length + a.quotes.length + a.low_stock.length : 0;
    }

    openPartList() {
        this.action.doAction("taller.action_taller_inventario_ui");
    }

    async refresh() {
        this.state.barsReady = false;
        await this.load();
        setTimeout(() => {
            this.state.barsReady = true;
        }, 80);
        this.countUp();
    }

    async silentRefresh() {
        const previous = {};
        for (const kpi of this.state.data.kpis) {
            previous[kpi.key] = kpi.value;
        }
        const data = await this.orm.call("service.order", "get_dashboard_data", []);
        for (const kpi of data.kpis) {
            kpi.changed = previous[kpi.key] !== undefined && previous[kpi.key] !== kpi.value;
        }
        this.applyOrder(data);
        this.state.data = data;
        this.state.shown = data.kpis.map((kpi) => kpi.value);
        setTimeout(() => {
            for (const kpi of this.state.data.kpis) {
                kpi.changed = false;
            }
        }, 1600);
    }

    get trendChart() {
        const trend = this.state.data.trend;
        const width = 520;
        const height = 190;
        const left = 34;
        const right = 14;
        const top = 14;
        const bottom = 28;
        const max = Math.max(1, ...trend.received, ...trend.delivered);
        const step = (width - left - right) / (trend.labels.length - 1);
        const x = (i) => Math.round((left + i * step) * 10) / 10;
        const y = (v) => Math.round((top + (height - top - bottom) * (1 - v / max)) * 10) / 10;
        const line = (arr) => arr.map((v, i) => `${x(i)},${y(v)}`).join(" ");
        const area = (arr) => `${x(0)},${y(0)} ${line(arr)} ${x(arr.length - 1)},${y(0)}`;
        const dots = (arr, label) =>
            arr.map((v, i) => ({ x: x(i), y: y(v), tip: `${trend.labels[i]}: ${v} ${label}` }));
        return {
            labels: trend.labels.map((text, i) => ({ text, x: x(i) })),
            grid: [0, 0.5, 1].map((f) => ({ y: y(max * f), label: Math.round(max * f) })),
            received: { line: line(trend.received), area: area(trend.received), dots: dots(trend.received, "recibidas") },
            delivered: { line: line(trend.delivered), area: area(trend.delivered), dots: dots(trend.delivered, "entregadas") },
            axisEnd: width - right,
            axisStart: left,
            labelY: height - 8,
        };
    }

    get incomeChart() {
        const income = this.state.data.income;
        if (!income) {
            return null;
        }
        const width = 520;
        const height = 190;
        const left = 10;
        const right = 10;
        const top = 22;
        const bottom = 28;
        const max = Math.max(1, ...income.values);
        const slot = (width - left - right) / income.values.length;
        const barWidth = slot * 0.56;
        const compact = new Intl.NumberFormat("es-UY", { notation: "compact", maximumFractionDigits: 1 });
        const full = new Intl.NumberFormat("es-UY", { maximumFractionDigits: 0 });
        return {
            baseline: height - bottom,
            labelY: height - 8,
            bars: income.values.map((value, i) => {
                const h = Math.round((height - top - bottom) * (value / max) * 10) / 10;
                return {
                    x: Math.round((left + i * slot + (slot - barWidth) / 2) * 10) / 10,
                    y: height - bottom - h,
                    w: Math.round(barWidth * 10) / 10,
                    h: h,
                    cx: Math.round((left + i * slot + slot / 2) * 10) / 10,
                    label: income.labels[i],
                    text: value ? compact.format(value) : "",
                    tip: `${income.labels[i]}: ${income.symbol} ${full.format(value)}`,
                };
            }),
        };
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
        this.action.doAction({ type: "ir.actions.client", tag: "taller.ficha", params: { id } });
    }

    newOrder() {
        this.action.doAction("taller.action_taller_counter");
    }

    goTo(xmlid) {
        this.action.doAction(xmlid);
    }
}

TallerDashboard.template = "taller.Dashboard";

registry.category("actions").add("taller.dashboard", TallerDashboard);