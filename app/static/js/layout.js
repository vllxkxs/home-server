// Page bootstrap: auth guard, settings, shared navigation.
import { api, redirectToLogin } from "./api.js";
import { el, setCurrency, mount } from "./ui.js";

// Static icon markup (no user data), 24x24 stroke icons.
const ICONS = {
    home: '<path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/>',
    list: '<path d="M8 6h13M8 12h13M8 18h13"/><circle cx="3.5" cy="6" r="1"/><circle cx="3.5" cy="12" r="1"/><circle cx="3.5" cy="18" r="1"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    user: '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 4-6 8-6s8 2 8 6"/>',
    shield: '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/>',
    logout: '<path d="M15 4h4v16h-4"/><path d="M10 8l-4 4 4 4M6 12h10"/>',
};

function icon(name) {
    const span = el("span", { class: "icon", "aria-hidden": "true" });
    span.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${ICONS[name]}</svg>`;
    return span;
}

function renderNav(me) {
    const path = window.location.pathname;
    const links = [
        { href: "/", label: "Home", icon: "home", active: path === "/" },
        { href: "/expenses", label: "Expenses", icon: "list", active: path === "/expenses" || /^\/expenses\/\d+/.test(path) },
        { href: "/expenses/new", label: "Add", icon: "plus", active: path === "/expenses/new", primary: true },
        me.is_admin
            ? { href: "/admin", label: "Admin", icon: "shield", active: path === "/admin" }
            : { href: `/users/${me.id}`, label: "Me", icon: "user", active: path.startsWith("/users/") },
    ];

    const logout = el("button", {
        type: "button", class: "nav-logout", title: "Log out",
        onclick: async () => {
            try { await api.logout(); } finally { window.location.href = "/"; }
        },
    }, icon("logout"), el("span", { class: "label" }, "Log out"));

    const account = me.is_admin
        ? el("a", { href: `/users/${me.id}/settings`, class: "nav-account", title: "Account settings" }, me.name)
        : el("a", { href: `/users/${me.id}`, class: "nav-account" }, me.name);

    const header = el("header", { class: "topbar" },
        el("div", { class: "topbar-inner" },
            el("a", { href: "/", class: "brand" }, "Flat Expenses"),
            el("nav", { class: "mainnav", "aria-label": "Main" },
                links.map(l => el("a", {
                    href: l.href,
                    class: ["navlink", l.primary && "primary", l.active && "active"].filter(Boolean).join(" "),
                    "aria-current": l.active ? "page" : null,
                }, icon(l.icon), el("span", { class: "label" }, l.label))),
            ),
            el("div", { class: "nav-right" }, account, logout),
        ),
    );
    document.body.prepend(header);
}

/**
 * Load the current user and settings, redirect when not allowed, render nav.
 * @param {{admin?: boolean, allowPasswordChange?: boolean}} opts
 */
export async function boot({ admin = false, allowPasswordChange = false } = {}) {
    let me, settings;
    try {
        [me, settings] = await Promise.all([api.getMe(), api.getSettings()]);
    } catch (err) {
        if (err.status === 401) redirectToLogin();
        throw err;
    }
    if (me.must_change_password && !allowPasswordChange) {
        window.location.href = `/users/${me.id}/settings?first=1`;
        return new Promise(() => {});
    }
    if (admin && !me.is_admin) {
        window.location.href = "/";
        return new Promise(() => {});
    }
    setCurrency(settings.currency);
    renderNav(me);
    return { me, settings };
}

/** Show a fatal error in the page body instead of a blank screen. */
export function showFatal(err) {
    if (err?.status === 401) return; // already redirecting
    console.error(err);
    const main = document.querySelector("main");
    mount(main, el("article", { class: "message error" },
        err?.status === 403 ? "You don't have access to this page." :
        err?.status === 404 ? "Not found." :
        `Something went wrong: ${err?.message || err}`));
}
