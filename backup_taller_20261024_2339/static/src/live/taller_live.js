/** @odoo-module **/

import { registry } from "@web/core/registry";

const CHANNEL = "taller";

function describe(p) {
    if (p.event === "created") {
        return { title: "Nueva orden", text: `${p.name} fue creada.`, type: "info" };
    }
    if (p.event === "status") {
        if (p.status === "done") {
            return { title: "Lista para retirar", text: `${p.name} está lista.`, type: "success" };
        }
        if (p.status === "quote") {
            return { title: "Presupuesto enviado", text: `${p.name} espera la aprobación del cliente.`, type: "info" };
        }
        if (p.old_status === "quote" && p.status === "repairing") {
            return { title: "Presupuesto aprobado", text: `${p.name} pasó a reparación.`, type: "success" };
        }
        if (p.status === "delivered") {
            return { title: "Orden entregada", text: `${p.name} fue entregada.`, type: "info" };
        }
        if (p.status === "cancel") {
            return { title: "Orden cancelada", text: `${p.name} fue cancelada.`, type: "warning" };
        }
        return { title: "Cambio de estado", text: `${p.name}: ${p.status_label}.`, type: "info" };
    }
    return null;
}

const tallerLiveService = {
    dependencies: ["bus_service", "notification", "action", "orm"],
    start(env, { bus_service, notification, action, orm }) {
        let profilePromise = null;
        const getProfile = () => {
            if (!profilePromise) {
                profilePromise = orm
                    .call("service.order", "get_live_profile", [])
                    .catch(() => ({ enabled: false }));
            }
            return profilePromise;
        };

        const openOrder = (id) => {
            action.doAction({
                type: "ir.actions.act_window",
                res_model: "service.order",
                res_id: id,
                views: [[false, "form"]],
                target: "current",
            });
        };

        let reloadTimer = null;
        const reloadCurrentList = () => {
            clearTimeout(reloadTimer);
            reloadTimer = setTimeout(() => {
                try {
                    const controller = action.currentController;
                    const props = controller && controller.props;
                    if (props && props.resModel === "service.order" &&
                        (props.type === "kanban" || props.type === "list")) {
                        action.doAction("soft_reload");
                    }
                } catch (e) {
                    // si algo cambia en la interfaz, simplemente no recarga
                }
            }, 1200);
        };

        const refreshDashboard = () => window.dispatchEvent(new Event("taller-refresh"));

        const onOrder = async (payload) => {
            const profile = await getProfile();
            if (!profile.enabled) {
                return;
            }
            refreshDashboard();
            reloadCurrentList();
            if (payload.by === profile.uid) {
                return;
            }
            const mine = !payload.user_id || payload.user_id === profile.uid;
            if (!profile.is_manager && !mine) {
                return;
            }
            const info = describe(payload);
            if (!info) {
                return;
            }
            notification.add(info.text, {
                title: info.title,
                type: info.type,
                buttons: [{ name: "Abrir", primary: true, onClick: () => openOrder(payload.id) }],
            });
        };

        const onLowStock = async (payload) => {
            const profile = await getProfile();
            if (!profile.enabled) {
                return;
            }
            refreshDashboard();
            if (!profile.is_manager) {
                return;
            }
            notification.add(`${payload.name}: quedan ${payload.stock} (mínimo ${payload.min_stock}).`, {
                title: "Stock bajo",
                type: "warning",
                sticky: true,
            });
        };

        const onRatingLow = async (payload) => {
            const profile = await getProfile();
            if (!profile.enabled || !profile.is_manager) {
                return;
            }
            refreshDashboard();
            notification.add(`El cliente valoró la orden ${payload.name} con ${payload.rating}.`, {
                title: "Valoración baja",
                type: "danger",
                sticky: true,
                buttons: [{ name: "Abrir", primary: true, onClick: () => openOrder(payload.id) }],
            });
        };

        const handlers = {
            "taller/order": onOrder,
            "taller/low_stock": onLowStock,
            "taller/rating_low": onRatingLow,
        };

        if (typeof bus_service.addChannel === "function") {
            bus_service.addChannel(CHANNEL);
        }
        if (typeof bus_service.subscribe === "function") {
            for (const [type, handler] of Object.entries(handlers)) {
                bus_service.subscribe(type, handler);
            }
        } else {
            bus_service.addEventListener("notification", ({ detail }) => {
                for (const { type, payload } of detail) {
                    if (handlers[type]) {
                        handlers[type](payload);
                    }
                }
            });
        }
        return {};
    },
};

registry.category("services").add("taller_live", tallerLiveService);
