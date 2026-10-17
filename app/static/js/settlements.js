// Settlement list ("who pays whom") with one-click "settle up".
import { api } from "./api.js";
import { confirmButton, el, money, today, toast, mount } from "./ui.js";

/** Record a payment from -> to as a "Settlement" expense, which zeroes that debt. */
export function recordPayment(s) {
    return api.addExpense({
        date: today(),
        description: `${s.from_name} paid ${s.to_name}`,
        category: "Settlement",
        cost: s.amount,
        shares: [
            { user_id: s.from_user_id, share: -s.amount },
            { user_id: s.to_user_id, share: s.amount },
        ],
    });
}

/**
 * @param {HTMLElement} container
 * @param {Array} settlements  all settlements from the API
 * @param {{viewerId: number|null, canSettle: boolean, onSettled?: Function}} opts
 *   viewerId: show only this user's settlements, worded as "you"; null = everyone's.
 */
export function renderSettlements(container, settlements, { viewerId = null, canSettle = true, onSettled } = {}) {
    const rows = viewerId == null
        ? settlements
        : settlements.filter(s => s.from_user_id === viewerId || s.to_user_id === viewerId);

    if (rows.length === 0) {
        mount(container, el("p", { class: "muted empty" }, "All settled up. 🎉"));
        return;
    }

    mount(container, el("ul", { class: "settlements" }, rows.map(s => {
        const youPay = s.from_user_id === viewerId;
        const youGet = s.to_user_id === viewerId;
        const text = youPay ? ["You pay ", el("strong", {}, s.to_name)]
            : youGet ? [el("strong", {}, s.from_name), " pays you"]
            : [el("strong", {}, s.from_name), " → ", el("strong", {}, s.to_name)];

        const action = canSettle && confirmButton(
            youGet ? "Got it" : "Mark paid",
            "Confirm?",
            async () => {
                try {
                    await recordPayment(s);
                    toast(`Recorded ${money(s.amount)} payment`);
                    onSettled?.();
                } catch (err) {
                    toast(err.message, "error");
                }
            },
            { class: "outline small", title: `Record that ${s.from_name} paid ${s.to_name} ${money(s.amount)}` },
        );

        return el("li", { class: youPay ? "neg" : youGet ? "pos" : "" },
            el("span", { class: "who" }, text),
            el("span", { class: "amount" }, money(s.amount)),
            action,
        );
    })));
}
