// All expenses: search, filters, totals and CSV export.
import { api } from "./api.js";
import { boot, showFatal } from "./layout.js";
import { consumedBy, expenseList, payerNames } from "./expense-list.js";
import { $, el, isSettlement, money, mount } from "./ui.js";

const state = { q: "", category: "", month: "", person: "", payments: false };

async function start() {
    const { me } = await boot();
    const [expenses, users] = await Promise.all([api.getExpenses(), api.getUsers()]);
    const nameOf = Object.fromEntries(users.map(u => [u.id, u.name]));

    const categories = [...new Set(expenses.filter(e => !isSettlement(e)).map(e => e.category))].sort();
    const months = [...new Set(expenses.map(e => e.date.slice(0, 7)))].sort().reverse();
    const people = users.filter(u => expenses.some(e => e.shares.some(s => s.user_id === u.id)));

    const select = (key, label, options) => el("select", {
        "aria-label": label,
        onchange: (e) => { state[key] = e.target.value; update(); },
    }, el("option", { value: "" }, label), options.map(([value, text]) => el("option", { value }, text)));

    const monthLabel = (m) => {
        const [y, mo] = m.split("-").map(Number);
        return new Date(y, mo - 1, 1).toLocaleDateString(undefined, { month: "long", year: "numeric" });
    };

    const summary = el("p", { class: "muted list-summary" });
    const listBox = el("div");

    mount($("#page"),
        el("div", { class: "section-head" },
            el("h1", {}, "Expenses"),
            el("button", { type: "button", class: "secondary outline small", onclick: () => exportCsv(filtered(), nameOf, me) }, "Export CSV")),
        el("div", { class: "filters" },
            el("input", {
                type: "search", placeholder: "Search…", "aria-label": "Search",
                oninput: (e) => { state.q = e.target.value.trim().toLowerCase(); update(); },
            }),
            select("category", "All categories", categories.map(c => [c, c])),
            select("month", "All months", months.map(m => [m, monthLabel(m)])),
            me.is_admin ? select("person", "Everyone", people.map(u => [String(u.id), u.name])) : null,
            el("label", { class: "inline-check" },
                el("input", { type: "checkbox", role: "switch", onchange: (e) => { state.payments = e.target.checked; update(); } }),
                "Show payments"),
        ),
        summary,
        listBox,
    );

    function filtered() {
        return expenses.filter(e =>
            (state.payments || !isSettlement(e)) &&
            (!state.category || e.category === state.category) &&
            (!state.month || e.date.startsWith(state.month)) &&
            (!state.person || e.shares.some(s => s.user_id === Number(state.person))) &&
            (!state.q || `${e.description} ${e.category} ${e.comment ?? ""}`.toLowerCase().includes(state.q)));
    }

    function update() {
        const rows = filtered();
        const spent = rows.filter(e => !isSettlement(e)).reduce((sum, e) => sum + e.cost, 0);
        const perspective = me.is_admin ? (state.person ? Number(state.person) : null) : me.id;
        const parts = [`${rows.length} expense${rows.length === 1 ? "" : "s"}`, `${money(spent)} total`];
        if (perspective != null) {
            const share = rows.filter(e => !isSettlement(e)).reduce((sum, e) => sum + consumedBy(e, perspective), 0);
            parts.push(`${me.is_admin ? `${nameOf[perspective]}'s` : "your"} share ${money(share)}`);
        }
        summary.textContent = parts.join(" · ");
        mount(listBox, expenseList(rows, { nameOf, perspectiveId: perspective, next: "/expenses" }));
    }

    update();
}

function exportCsv(rows, nameOf, me) {
    const header = ["Date", "Description", "Category", "Amount", "Currency", "Paid by", "Shared by", "Comment"];
    if (!me.is_admin) header.push("Your share");
    const lines = [header, ...rows.map(e => {
        const consumers = [...new Set(e.shares.filter(s => s.share > 0).map(s => nameOf[s.user_id] ?? s.user_id))];
        const line = [e.date, e.description, e.category, e.cost.toFixed(2), e.currency,
            payerNames(e, nameOf), consumers.join(", "), e.comment ?? ""];
        if (!me.is_admin) line.push(consumedBy(e, me.id).toFixed(2));
        return line;
    })];
    const csv = lines.map(l => l.map(csvCell).join(",")).join("\r\n");
    const url = URL.createObjectURL(new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" }));
    const a = el("a", { href: url, download: `expenses-${new Date().toISOString().slice(0, 10)}.csv` });
    document.body.append(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
}

function csvCell(value) {
    let text = String(value ?? "");
    // Prevent spreadsheet formula injection.
    if (/^[=+\-@\t\r]/.test(text) && !/^-?\d/.test(text)) text = "'" + text;
    return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

start().catch(showFatal);
