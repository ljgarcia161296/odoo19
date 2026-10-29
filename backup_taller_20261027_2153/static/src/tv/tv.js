/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, onMounted, onWillUnmount, useState, useRef } from "@odoo/owl";

class TallerTv extends Component {
    setup() {
        this.orm = useService("orm");
        this.rootRef = useRef("root");
        this.state = useState({
            data: { columns: [], late: 0, ready: 0, company: "" },
            clock: "",
            fullscreen: false,
        });
        this.reloadTimer = null;
        this.clockTimer = null;
        this.pollTimer = null;
        this.onLive = () => {
            clearTimeout(this.reloadTimer);
            this.reloadTimer = setTimeout(() => this.load(), 600);
        };
        this.onFullscreen = () => {
            this.state.fullscreen = !!document.fullscreenElement;
        };
        onWillStart(() => this.load());
        onMounted(() => {
            this.tick();
            this.clockTimer = setInterval(() => this.tick(), 1000);
            this.pollTimer = setInterval(() => this.load(), 30000);
            window.addEventListener("taller-refresh", this.onLive);
            document.addEventListener("fullscreenchange", this.onFullscreen);
        });
        onWillUnmount(() => {
            clearInterval(this.clockTimer);
            clearInterval(this.pollTimer);
            clearTimeout(this.reloadTimer);
            window.removeEventListener("taller-refresh", this.onLive);
            document.removeEventListener("fullscreenchange", this.onFullscreen);
        });
    }

    async load() {
        this.state.data = await this.orm.call("service.order", "tv_data", []);
    }

    tick() {
        const now = new Date();
        const date = now.toLocaleDateString("es-UY", { weekday: "long", day: "numeric", month: "long" });
        const time = now.toLocaleTimeString("es-UY", { hour: "2-digit", minute: "2-digit" });
        this.state.clock = `${date} · ${time}`;
    }

    toggleFullscreen() {
        if (document.fullscreenElement) {
            document.exitFullscreen();
        } else if (this.rootRef.el && this.rootRef.el.requestFullscreen) {
            this.rootRef.el.requestFullscreen();
        }
    }
}

TallerTv.template = "taller.Tv";

registry.category("actions").add("taller.tv", TallerTv);
