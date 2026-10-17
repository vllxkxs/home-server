// Expense rows shared by the home page, the expenses page and profiles.
import { el, formatDate, isSettlement, money } from "./ui.js";

/** Net effect of an expense for one user: >0 they get money back, <0 they owe. */
export function netFor(expense, userId) {
    return -expense.shares.filter(s => s.user_id === userId).reduce((sum, s) => sum + s.share, 0);
}

/** What the user consumed (their positive shares). */
export function consumedBy(expense, userId) {
    return expense.shares.filter(s => s.user_id === userId && s.share > 0).reduce((sum, s) => sum + s.share, 0);
}

export function payerNames(expense, nameOf) {
    const ids = [...new Set(expense.shares.filter(s => s.share < 0).map(s => s.user_id))];
    return ids.map(id => nameOf[id] ?? `User ${id}`).join(", ");
}

/**
 * @param {Array} expenses
 * @param {{nameOf: Object, perspectiveId?: number|null, next?: string}} opts
 */
export function expenseList(expenses, { nameOf, perspectiveId = null, next = null }) {
    if (expenses.length === 0) return el("p", { class: "muted empty" }, "No expenses yet.");

    return el("ul", { class: "expense-list" }, expenses.map(e => {
        const settlement = isSettlement(e);
        const href = `/expenses/${e.id}` + (next ? `?next=${encodeURIComponent(next)}` : "");

        let side = null;
        if (perspectiveId != null) {
            const net = netFor(e, perspectiveId);
            side = Math.abs(net) < 0.005
                ? el("small", { class: "muted" }, "even")
                : el("small", { class: net > 0 ? "pos" : "neg" }, `${net > 0 ? "you get" : "you owe"} ${money(Math.abs(net))}`);
        }

        return el("li", {},
            el("a", { href, class: settlement ? "row settlement" : "row" },
                el("span", { class: "main" },
                    el("span", { class: "title" }, e.description),
                    el("span", { class: "sub" },
                        settlement ? "Payment" : e.category, " · ", formatDate(e.date),
                        settlement ? null : ` · paid by ${payerNames(e, nameOf)}`),
                ),
                el("span", { class: "side" },
                    el("span", { class: "amount" }, money(e.cost)),
                    side,
                ),
            ),
        );
    }));
}
