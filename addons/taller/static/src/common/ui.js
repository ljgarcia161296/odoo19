/** @odoo-module **/

const DEVICE_ICONS = {
    phone: "fa-mobile",
    tablet: "fa-tablet",
    computer: "fa-laptop",
    other: "fa-wrench",
};
const AVATAR_COLORS = ["#0f4c5c", "#3b7dd8", "#7a5af8", "#2e8b57", "#d9822b", "#c2415c", "#5b7083"];

export function deviceIcon(type) {
    return DEVICE_ICONS[type] || DEVICE_ICONS.other;
}

export function initials(name) {
    const parts = (name || "?").trim().split(/\s+/).slice(0, 2);
    return parts.map((p) => p.charAt(0)).join("") || "?";
}

export function avatarColor(name) {
    let hash = 0;
    for (const ch of name || "") {
        hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
    }
    return AVATAR_COLORS[hash % AVATAR_COLORS.length];
}
