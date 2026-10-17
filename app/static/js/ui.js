// Small DOM and formatting helpers shared by all pages.
// Always build DOM with el()/textContent — never innerHTML with data.

export function el(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs)) {
        if (value == null || value === false) continue;
        if (key === "class") node.className = value;
        else if (key === "dataset") Object.assign(node.dataset, value);
        else if (key.startsWith("on") && typeof value === "function") node.addEventListener(key.slice(2), value);
        else if (key in node && typeof value !== "string") node[key] = value;
        else node.setAttribute(key, value === true ? "" : value);
    }
    for (const child of children.flat()) {
        if (child == null || child === false) continue;
        node.append(child instanceof Node ? child : String(child));
    }
    return node;
}

export const $ = (selector, root = document) => root.querySelector(selector);

/** Replace a container's children, skipping null/false like el() does. */
export function mount(target, ...children) {
    target.replaceChildren(...children.flat().filter(c => c != null && c !== false));
}

// --- money -----------------------------------------------------------------

let currencyFormat = new Intl.NumberFormat(undefined, { style: "currency", currency: "EUR" });

export function setCurrency(code) {
    try {
        currencyFormat = new Intl.NumberFormat(undefined, { style: "currency", currency: code });
    } catch { /* keep previous */ }
}

export function money(amount) {
    return currencyFormat.format(Math.abs(amount) < 0.005 ? 0 : amount);
}

export function signedMoney(amount) {
    if (Math.abs(amount) < 0.005) return money(0);
    return (amount > 0 ? "+" : "−") + money(Math.abs(amount));
}

/** Parse "12,50" or "12.5" -> 12.5; NaN when invalid. */
export function parseAmount(text) {
    const cleaned = String(text ?? "").trim().replace(/\s/g, "").replace(",", ".");
    if (!/^\d*\.?\d*$/.test(cleaned) || cleaned === "" || cleaned === ".") return NaN;
    return Math.round(parseFloat(cleaned) * 100) / 100;
}

export const toCents = (amount) => Math.round(amount * 100);

/** Split cents equally; earlier entries get the leftover cents. */
export function splitEqually(totalCents, count) {
    const base = Math.floor(totalCents / count);
    const extra = totalCents - base * count;
    return Array.from({ length: count }, (_, i) => base + (i < extra ? 1 : 0));
}

// --- dates -----------------------------------------------------------------

export function today() {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function formatDate(isoDate) {
    const [y, m, d] = isoDate.split("-").map(Number);
    return new Date(y, m - 1, d).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

// --- misc ------------------------------------------------------------------

/** Only allow same-site relative paths as redirect targets. */
export function safeNext(value, fallback = "/") {
    if (!value || !value.startsWith("/") || value.startsWith("//") || value.startsWith("/\\")) return fallback;
    return value;
}

export const isSettlement = (expense) => (expense.category || "").toLowerCase() === "settlement";

/**
 * Two-step button: first click asks to confirm, second click runs the action.
 * Resets after a few seconds.
 */
export function confirmButton(label, confirmLabel, onConfirm, attrs = {}) {
    let armed = false;
    let timer;
    const btn = el("button", { type: "button", ...attrs }, label);
    btn.addEventListener("click", async () => {
        if (!armed) {
            armed = true;
            btn.textContent = confirmLabel;
            btn.classList.add("armed");
            timer = setTimeout(reset, 4000);
            return;
        }
        clearTimeout(timer);
        btn.disabled = true;
        try {
            await onConfirm();
        } finally {
            btn.disabled = false;
            reset();
        }
    });
    function reset() {
        armed = false;
        btn.textContent = label;
        btn.classList.remove("armed");
    }
    return btn;
}

/** Show a message in a container; kind = "error" | "success" | "". */
export function showMessage(target, text, kind = "error") {
    target.textContent = text || "";
    target.className = `message ${kind}`.trim();
    target.hidden = !text;
}

let toastTimer;
export function toast(text, kind = "success") {
    let node = $("#toast");
    if (!node) {
        node = el("div", { id: "toast", role: "status", "aria-live": "polite" });
        document.body.append(node);
    }
    node.textContent = text;
    node.className = `show ${kind}`;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { node.className = ""; }, 3000);
}
