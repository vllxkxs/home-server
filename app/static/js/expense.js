// Expense details, edit and delete.
import { api } from "./api.js";
import { boot, showFatal } from "./layout.js";
import { payerNames } from "./expense-list.js";
import { createExpenseForm } from "./share-form.js";
import { $, confirmButton, el, formatDate, isSettlement, money, safeNext, signedMoney, toast, mount } from "./ui.js";

const expenseId = parseInt(window.location.pathname.split("/").pop(), 10);
const back = safeNext(new URLSearchParams(window.location.search).get("next"), "/expenses");

async function start() {
    const { me } = await boot();
    const [expense, users, categories] = await Promise.all([
        api.getExpense(expenseId), api.getUsers(), api.getCategories(),
    ]);
    const ctx = {
        me, users, categories,
        nameOf: Object.fromEntries(users.map(u => [u.id, u.name])),
        canEdit: me.is_admin || expense.shares.some(s => s.user_id === me.id && s.share < 0),
    };
    showDetails(expense, ctx);
}

function perPerson(expense) {
    const rows = {};
    for (const s of expense.shares) {
        const row = rows[s.user_id] ??= { paid: 0, consumed: 0 };
        if (s.share < 0) row.paid -= s.share;
        else row.consumed += s.share;
    }
    return rows;
}

function showDetails(expense, ctx) {
    const { me, nameOf, canEdit } = ctx;
    const rows = perPerson(expense);
    const settlement = isSettlement(expense);

    const actions = canEdit && el("div", { class: "actions" },
        el("button", { type: "button", onclick: () => showEdit(expense, ctx) }, "Edit"),
        confirmButton("Delete", "Sure?", async () => {
            try {
                await api.deleteExpense(expense.id);
                window.location.href = back;
            } catch (err) {
                toast(err.message, "error");
            }
        }, { class: "secondary outline" }),
    );

    mount($("#page"),
        el("a", { href: back, class: "back" }, "← Back"),
        el("article", { class: "detail" },
            el("header", {},
                el("p", { class: "muted" }, settlement ? "Payment" : expense.category),
                el("h1", {}, expense.description),
                el("p", { class: "detail-amount" }, money(expense.cost)),
            ),
            el("dl", { class: "meta" },
                el("dt", {}, "Date"), el("dd", {}, formatDate(expense.date)),
                el("dt", {}, "Paid by"), el("dd", {}, payerNames(expense, nameOf)),
                expense.currency && el("dt", {}, "Currency"), expense.currency && el("dd", {}, expense.currency),
                expense.comment && el("dt", {}, "Comment"), expense.comment && el("dd", {}, expense.comment),
            ),
            el("table", { class: "split-table" },
                el("thead", {}, el("tr", {},
                    el("th", {}, "Person"), el("th", { class: "num" }, "Paid"),
                    el("th", { class: "num" }, "Share"), el("th", { class: "num" }, "Net"))),
                el("tbody", {}, Object.entries(rows).map(([id, r]) => {
                    const net = r.paid - r.consumed;
                    return el("tr", { class: Number(id) === me.id ? "me" : null },
                        el("td", {}, nameOf[id] ?? `User ${id}`),
                        el("td", { class: "num" }, r.paid ? money(r.paid) : "—"),
                        el("td", { class: "num" }, r.consumed ? money(r.consumed) : "—"),
                        el("td", { class: `num ${net > 0.005 ? "pos" : net < -0.005 ? "neg" : "muted"}` }, signedMoney(net)));
                })),
            ),
            actions,
        ),
    );
}

function showEdit(expense, ctx) {
    const { me, users, categories } = ctx;
    const inExpense = new Set(expense.shares.map(s => s.user_id));
    const people = users
        .filter(u => (u.is_active && !u.is_admin) || inExpense.has(u.id))
        .map(u => ({ id: u.id, name: u.name, inactive: !u.is_active || u.is_admin }));

    const formRoot = el("div");
    mount($("#page"), el("article", { class: "form-card" }, el("h1", {}, "Edit expense"), formRoot));
    createExpenseForm(formRoot, {
        people,
        me,
        categories,
        expense,
        submitLabel: "Save changes",
        onSubmit: async (payload) => {
            await api.updateExpense(expense.id, payload);
            toast("Saved");
            showDetails(await api.getExpense(expense.id), ctx);
        },
        onCancel: () => showDetails(expense, ctx),
    });
}

start().catch(showFatal);
