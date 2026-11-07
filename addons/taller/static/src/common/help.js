/** @odoo-module **/

// Ayuda integrada: consejos por pantalla, pasos del recorrido y atajos.

export const TOUR = [
    { icon: "fa-hand-peace-o", title: "Bienvenido al taller", text: "Un recorrido de un minuto por lo más importante. Podés repetirlo cuando quieras desde el botón Ayuda del menú." },
    { icon: "fa-plus-circle", title: "Recibir un equipo", text: "En Recepción cargás cliente, equipo y problema. Se genera la orden con su etiqueta QR para pegar en el equipo." },
    { icon: "fa-th-large", title: "El tablero", text: "Cada columna es un estado. Arrastrá una tarjeta para avanzar la orden. Pasá el mouse sobre una tarjeta para ver el detalle sin abrirla." },
    { icon: "fa-file-text-o", title: "La ficha de la orden", text: "Ahí está todo: diagnóstico, repuestos, fotos, cobros, historial y WhatsApp al cliente con plantillas. Podés arrastrar fotos desde tu PC." },
    { icon: "fa-search", title: "Buscar con Ctrl+K", text: "Escribí un cliente, una orden, un serial o un comando como «caja» o «nueva orden». Es la forma más rápida de moverse." },
    { icon: "fa-money", title: "Caja, ventas y finanzas", text: "Caja diaria resume los cobros del día, Venta de mostrador cobra accesorios y Finanzas muestra el resultado y las comisiones." },
    { icon: "fa-qrcode", title: "Etiquetas QR", text: "Con «Escanear QR» abrís la orden apuntando la cámara a la etiqueta del equipo. Funciona también desde el celular." },
    { icon: "fa-paint-brush", title: "A tu gusto", text: "Elegí el color del sistema y el modo oscuro en el menú lateral. Se recuerdan en este navegador." },
];

export const SHORTCUTS = [
    ["Ctrl + K", "Buscar órdenes, clientes y comandos"],
    ["↑ ↓ Enter", "Moverse y elegir en los resultados"],
    ["Esc", "Cerrar buscador, ayuda o ventanas"],
    ["Tecla ?", "Abrir esta ayuda (fuera de un campo de texto)"],
];

const GENERIC = [
    "Usá Ctrl+K para saltar a cualquier pantalla, orden o cliente.",
    "El menú lateral se puede ocultar para ganar espacio.",
];

export const SCREEN_HELP = {
    "taller.dashboard": {
        name: "Portada",
        tips: [
            "Las tarjetas de arriba son atajos: arrastralas para ordenarlas a tu gusto.",
            "Las listas «requieren atención» muestran órdenes atrasadas o sin movimiento.",
            "Tocá cualquier número o fila para abrir el detalle.",
        ],
    },
    "taller.board": {
        name: "Tablero",
        tips: [
            "Arrastrá una tarjeta a la columna siguiente para avanzar el estado.",
            "Se puede volver atrás una orden, salvo las ya entregadas.",
            "Filtrá por técnico, solo mis órdenes o solo atrasadas desde la barra superior.",
            "Pasá el mouse sobre una tarjeta para ver problema, teléfono y serial.",
        ],
    },
    "taller.ficha": {
        name: "Ficha de la orden",
        tips: [
            "Tocá el teléfono del cliente para corregirlo en el momento.",
            "Arrastrá fotos desde tu PC a la ficha para adjuntarlas.",
            "Los botones de WhatsApp usan plantillas: elegí la que corresponda y se registra en el historial.",
            "Al cambiar estados aparece «Deshacer» por unos segundos.",
        ],
    },
    "taller.counter": {
        name: "Recepción",
        tips: [
            "Cargá el cliente (o elegí uno existente), el equipo y el problema.",
            "Agregá la foto y la firma del cliente si querés dejar constancia.",
            "Al guardar podés imprimir el comprobante y la etiqueta con QR.",
        ],
    },
    "taller.tech": {
        name: "Mi trabajo",
        tips: ["Muestra solo tus órdenes activas.", "Desde acá avanzás cada orden sin pasar por el tablero."],
    },
    "taller.caja": {
        name: "Caja diaria",
        tips: [
            "Suma cobros de órdenes y ventas de mostrador del día.",
            "Los totales se separan por forma de pago para el arqueo.",
        ],
    },
    "taller.finanzas": {
        name: "Finanzas",
        tips: [
            "Compara ingresos, gastos y resultado del período.",
            "Las comisiones por técnico se configuran acá (solo responsables).",
            "Los gastos fijos se cargan en Configuración.",
        ],
    },
    "taller.venta": {
        name: "Venta de mostrador",
        tips: [
            "Buscá el repuesto o accesorio, agregalo y cobrá.",
            "Una venta cancelada devuelve el stock.",
        ],
    },
    "taller.inventario": {
        name: "Inventario",
        tips: [
            "Ajustá el stock directamente desde la lista.",
            "Los repuestos bajo el mínimo se marcan para que los compres.",
            "Desde acá podés generar una compra sugerida.",
        ],
    },
    "taller.clientes": {
        name: "Clientes",
        tips: [
            "Buscá por nombre o teléfono.",
            "La ficha del cliente muestra sus equipos, órdenes y lo que gastó.",
            "Se pueden importar clientes desde un CSV en Configuración.",
        ],
    },
    "taller.calendar": {
        name: "Calendario",
        tips: [
            "Arrastrá una orden a otro día para reprogramar la entrega.",
            "Las órdenes atrasadas se marcan en rojo; las entregadas no se pueden mover.",
            "Hacé clic en una orden para abrir su ficha.",
        ],
    },
    "taller.compras": {
        name: "Compras",
        tips: [
            "Flujo: borrador → pedida → recibida. Al recibir, el stock sube.",
            "Podés reabrir una compra cancelada.",
        ],
    },
    "taller.garantias": {
        name: "Garantías",
        tips: [
            "«Por vencer» son las que quedan 7 días o menos.",
            "«Avisar» abre WhatsApp con un mensaje listo.",
            "«Reingreso» crea una orden sin cargo vinculada a la original.",
        ],
    },
    "taller.config": {
        name: "Datos del taller",
        tips: [
            "El logo y los datos aparecen en los PDF.",
            "Los días de garantía se aplican a las órdenes nuevas.",
            "Las condiciones extra se imprimen en el comprobante de recepción.",
        ],
    },
    "taller.panel": {
        name: "Panel de gestión",
        tips: [
            "Los gráficos de ingresos y el ranking son solo para responsables.",
            "Definí una meta mensual para ver el avance en la barra.",
            "Las alertas muestran órdenes estancadas, sin retirar, valoraciones bajas, stock bajo y clientes que no vuelven.",
        ],
    },
    "taller.mensajes": {
        name: "Mensajes pendientes",
        tips: [
            "Cada fila es un aviso listo: recibido, presupuesto, para retirar o encuesta posventa.",
            "«Enviar» abre WhatsApp con el mensaje y el enlace de seguimiento, y lo registra.",
            "«Ya avisé» lo saca de la lista sin enviar nada.",
        ],
    },
    "taller.actividad": {
        name: "Registro de actividad",
        tips: ["Muestra quién cambió qué y cuándo en las órdenes.", "Filtrá por orden, persona o texto."],
    },
    "taller.tv": {
        name: "Tablero para TV",
        tips: ["Pensado para una pantalla grande: se actualiza solo."],
    },
};

export function helpFor(tag) {
    return SCREEN_HELP[tag] || { name: "Esta pantalla", tips: GENERIC };
}
