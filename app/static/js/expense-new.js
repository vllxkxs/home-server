// Quick add: amount, what, category, then save — sensible defaults for the rest.
import { api } from "./api.js";
import { boot, showFatal } from "./layout.js";
import { createExpenseForm } from "./share-form.js";
import { $, el, isSettlement, safeNext, mount } from "./ui.js";

/** Categories by how often they were used, most used first. */
export function categoriesByUse(expenses, allCategories) {
    const counts = {};
    for (const e of expenses) if (!isSettlement(e)) counts[e.category] = (counts[e.category] ?? 0) + 1;
    return allCategories
        .filter(c => c.toLowerCase() !== "settlement")
        .sort((a, b) => (counts[b] ?? 0) - (counts[a] ?? 0) || a.localeCompare(b));
}

async function start() {
    const { me } = await boot();
    const [users, categories, expenses] = await Promise.all([api.getUsers(), api.getCategories(), api.getExpenses()]);
    const people = users.filter(u => u.is_active && !u.is_admin);
    const next = safeNext(new URLSearchParams(window.location.search).get("next"));
    const page = $("#page");

    if (people.length === 0) {
        mount(page, el("article", { class: "message" },
            "No flatmates yet. ", me.is_admin ? el("a", { href: "/admin" }, "Add users in Admin") : "Ask the admin to add users."));
        return;
    }

    const formRoot = el("div");
    mount(page, el("article", { class: "form-card" }, el("h1", {}, "Add expense"), formRoot));
    createExpenseForm(formRoot, {
        people,
        me,
        categories: categoriesByUse(expenses, categories),
        submitLabel: "Add expense",
        onSubmit: async (payload) => {
            await api.addExpense(payload);
            window.location.href = next;
        },
        onCancel: () => { window.location.href = next; },
    });
}

start().catch(showFatal);
