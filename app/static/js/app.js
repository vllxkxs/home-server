// Home: login form, or the dashboard (balance, settle up, recent expenses).
import { api } from "./api.js";
import { boot, showFatal } from "./layout.js";
import { expenseList } from "./expense-list.js";
import { renderSettlements } from "./settlements.js";
import { $, el, isSettlement, money, safeNext, showMessage, signedMoney, today, mount } from "./ui.js";

const next = safeNext(new URLSearchParams(window.location.search).get("next"));

async function start() {
    try {
        await api.getMe();
    } catch (err) {
        if (err.status === 401) return showLogin();
        return showFatal(err);
    }
    try {
        const ctx = await boot();
        await renderDashboard(ctx);
    } catch (err) {
        showFatal(err);
    }
}

function showLogin() {
    $("#login").hidden = false;
    const form = $("#login-form");
    const error = $("#login-error");
    const password = $("#login-password");
    const toggle = $("#toggle-password");

    toggle.addEventListener("click", () => {
        const show = password.type === "password";
        password.type = show ? "text" : "password";
        toggle.textContent = show ? "Hide" : "Show";
        toggle.setAttribute("aria-label", show ? "Hide password" : "Show password");
    });

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        showMessage(error, "");
        const submit = $("#login-submit");
        submit.disabled = true;
        submit.setAttribute("aria-busy", "true");
        try {
            const user = await api.login({ name: $("#login-name").value.trim(), password: password.value });
            window.location.href = user.must_change_password ? `/users/${user.id}/settings?first=1` : next;
        } catch (err) {
            showMessage(error, err.status === 401 ? "Wrong name or password." : err.message);
            password.select();
        } finally {
            submit.disabled = false;
            submit.removeAttribute("aria-busy");
        }
    });
}

async function renderDashboard({ me }) {
    const root = $("#dashboard");
    root.hidden = false;

    const [balances, settlements, expenses, users] = await Promise.all([
        api.getBalances(), api.getSettlements(), api.getExpenses(), api.getUsers(),
    ]);
    const nameOf = Object.fromEntries(users.map(u => [u.id, u.name]));
    const settlementsBox = el("div");
    const reload = () => renderDashboard({ me });

    mount(root,
        me.is_admin ? adminHero(balances, expenses) : personalHero(balances, me),
        el("section", {},
            el("h2", {}, me.is_admin ? "Who pays whom" : "Settle up"),
            settlementsBox),
        el("section", {},
            el("div", { class: "section-head" },
                el("h2", {}, "Recent"),
                el("a", { href: "/expenses" }, "All expenses →")),
            expenseList(expenses.slice(0, 6), { nameOf, perspectiveId: me.is_admin ? null : me.id })),
    );
    renderSettlements(settlementsBox, settlements, {
        viewerId: me.is_admin ? null : me.id,
        onSettled: reload,
    });
}

function personalHero(balances, me) {
    const mine = balances.find(b => b.user_id === me.id)?.balance ?? 0;
    const settled = Math.abs(mine) < 0.005;
    return el("article", { class: `hero ${settled ? "" : mine > 0 ? "pos" : "neg"}` },
        el("p", { class: "hero-label" }, settled ? "You're all square" : mine > 0 ? "You are owed" : "You owe"),
        el("p", { class: "hero-amount" }, money(Math.abs(mine))),
        el("a", { href: "/expenses/new", role: "button", class: "hero-action" }, "+ Add expense"),
    );
}

function adminHero(balances, expenses) {
    const month = today().slice(0, 7);
    const spent = expenses
        .filter(e => e.date.startsWith(month) && !isSettlement(e))
        .reduce((sum, e) => sum + e.cost, 0);
    return el("article", { class: "hero" },
        el("p", { class: "hero-label" }, "Spent this month"),
        el("p", { class: "hero-amount" }, money(spent)),
        balances.length
            ? el("ul", { class: "balance-chips" }, balances.map(b =>
                el("li", {},
                    el("a", { href: `/users/${b.user_id}` }, b.name),
                    el("span", { class: Math.abs(b.balance) < 0.005 ? "muted" : b.balance > 0 ? "pos" : "neg" },
                        signedMoney(b.balance)))))
            : el("p", { class: "muted" }, "No flatmates yet. Add some in Admin."),
    );
}

start();
