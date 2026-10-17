// Expense form shared by "add" and "edit".
// Builds signed shares: payers negative, consumers positive, both summing to the cost.
import { el, money, parseAmount, showMessage, splitEqually, toCents, today, mount } from "./ui.js";

const sumCents = (values) => values.reduce((a, b) => a + b, 0);

/** Derive form state from an existing expense. */
function stateFromExpense(expense, people) {
    const order = people.map(p => p.id);
    const paid = {};
    const consumed = {};
    for (const s of expense.shares) {
        const bucket = s.share < 0 ? paid : consumed;
        bucket[s.user_id] = (bucket[s.user_id] ?? 0) + toCents(Math.abs(s.share));
    }
    const payerIds = Object.keys(paid).map(Number);
    const selected = order.filter(id => consumed[id]);
    const costCents = toCents(expense.cost);
    const equalSplit = splitEqually(costCents, selected.length).sort((a, b) => a - b);
    const actual = selected.map(id => consumed[id]).sort((a, b) => a - b);
    const isEqual = equalSplit.length === actual.length && equalSplit.every((v, i) => v === actual[i]);

    return {
        payMode: payerIds.length > 1 ? "multi" : "single",
        payerId: payerIds[0] ?? order[0],
        paid: Object.fromEntries(payerIds.map(id => [id, (paid[id] / 100).toFixed(2)])),
        splitMode: isEqual ? "equal" : "custom",
        selected: new Set(selected),
        custom: Object.fromEntries(selected.map(id => [id, (consumed[id] / 100).toFixed(2)])),
    };
}

/**
 * @param {HTMLElement} root
 * @param {{
 *   people: Array<{id:number, name:string, inactive?:boolean}>,
 *   me: {id:number},
 *   categories: string[],     // most used first
 *   expense?: object|null,    // edit mode when given
 *   submitLabel: string,
 *   onSubmit: (payload) => Promise<void>,
 *   onCancel?: () => void,
 * }} opts
 */
export function createExpenseForm(root, { people, me, categories, expense = null, submitLabel, onSubmit, onCancel }) {
    const ids = people.map(p => p.id);
    const nameOf = Object.fromEntries(people.map(p => [p.id, p.inactive ? `${p.name} (inactive)` : p.name]));
    const state = expense ? stateFromExpense(expense, people) : {
        payMode: "single",
        payerId: ids.includes(me.id) ? me.id : ids[0],
        paid: {},
        splitMode: "equal",
        selected: new Set(people.filter(p => !p.inactive).map(p => p.id)),
        custom: {},
    };

    // --- static fields -------------------------------------------------------
    const amount = el("input", {
        class: "amount-input", type: "text", inputmode: "decimal", autocomplete: "off",
        placeholder: "0.00", "aria-label": "Amount", required: true,
        value: expense ? expense.cost.toFixed(2) : "",
    });
    const description = el("input", {
        type: "text", placeholder: "What was it?", "aria-label": "Description", required: true,
        maxlength: "200", value: expense?.description ?? "",
    });
    const category = el("input", {
        type: "text", placeholder: "Category", "aria-label": "Category", list: "category-options",
        required: true, maxlength: "200", value: expense?.category ?? "",
    });
    const categoryChips = el("div", { class: "chips" }, categories.slice(0, 8).map(c =>
        el("button", { type: "button", class: "chip", onclick: () => { category.value = c; syncCategoryChips(); } }, c)));
    const date = el("input", { type: "date", "aria-label": "Date", required: true, value: expense?.date ?? today() });
    const comment = el("input", {
        type: "text", placeholder: "Comment (optional)", "aria-label": "Comment", maxlength: "1000",
        value: expense?.comment ?? "",
    });

    const paySection = el("div", { class: "field-group" });
    const splitSection = el("div", { class: "field-group" });
    const summary = el("p", { class: "summary muted", "aria-live": "polite" });
    const error = el("p", { class: "message error", hidden: true });
    const submit = el("button", { type: "submit" }, submitLabel);

    function syncCategoryChips() {
        for (const chip of categoryChips.children) {
            chip.classList.toggle("selected", chip.textContent === category.value.trim());
        }
    }
    category.addEventListener("input", syncCategoryChips);

    // --- dynamic sections ------------------------------------------------------
    function chip(label, selected, onclick, extra = {}) {
        return el("button", {
            type: "button", class: selected ? "chip selected" : "chip", "aria-pressed": String(selected), onclick, ...extra,
        }, label);
    }

    function amountInput(value, onInput, label) {
        return el("input", {
            type: "text", inputmode: "decimal", class: "small-amount", placeholder: "0.00",
            "aria-label": label, value: value ?? "", oninput: (e) => { onInput(e.target.value); updateSummary(); },
        });
    }

    function renderPay() {
        const header = el("div", { class: "group-head" },
            el("span", { class: "group-label" }, "Paid by"),
            el("button", {
                type: "button", class: "link-button",
                onclick: () => {
                    state.payMode = state.payMode === "single" ? "multi" : "single";
                    if (state.payMode === "multi" && !Object.values(state.paid).some(Boolean) && state.payerId != null) {
                        state.paid[state.payerId] = amount.value;
                    }
                    render();
                },
            }, state.payMode === "single" ? "Several people paid?" : "Just one person"),
        );
        const body = state.payMode === "single"
            ? el("div", { class: "chips" }, people.map(p =>
                chip(nameOf[p.id], state.payerId === p.id, () => { state.payerId = p.id; render(); })))
            : el("div", { class: "amount-rows" }, people.map(p => el("label", { class: "amount-row" },
                el("span", {}, nameOf[p.id]),
                amountInput(state.paid[p.id], v => { state.paid[p.id] = v; }, `${p.name} paid`))));
        mount(paySection, header, body);
    }

    function renderSplit() {
        const header = el("div", { class: "group-head" },
            el("span", { class: "group-label" }, "Split between"),
            el("div", { class: "segmented", "aria-label": "Split mode" },
                chip("Equally", state.splitMode === "equal", () => { state.splitMode = "equal"; render(); }),
                chip("Custom", state.splitMode === "custom", () => {
                    if (state.splitMode !== "custom") prefillCustomFromEqual();
                    state.splitMode = "custom";
                    render();
                }),
            ),
        );
        const toggles = el("div", { class: "chips" }, people.map(p =>
            chip(nameOf[p.id], state.selected.has(p.id), () => {
                if (state.selected.has(p.id)) state.selected.delete(p.id);
                else state.selected.add(p.id);
                render();
            })));
        const customRows = state.splitMode === "custom"
            ? el("div", { class: "amount-rows" }, people.filter(p => state.selected.has(p.id)).map(p =>
                el("label", { class: "amount-row" },
                    el("span", {}, nameOf[p.id]),
                    amountInput(state.custom[p.id], v => { state.custom[p.id] = v; }, `${p.name} share`))))
            : null;
        mount(splitSection, header, toggles, customRows);
    }

    /** Start custom amounts from the equal split, so users only adjust what differs. */
    function prefillCustomFromEqual() {
        const cost = parseAmount(amount.value);
        const selected = ids.filter(id => state.selected.has(id));
        if (!(cost > 0) || selected.length === 0) return;
        splitEqually(toCents(cost), selected.length).forEach((cents, i) => {
            state.custom[selected[i]] = (cents / 100).toFixed(2);
        });
    }

    function render() {
        renderPay();
        renderSplit();
        updateSummary();
    }

    // --- shares ----------------------------------------------------------------
    /** @returns {{cost:number, shares:Array}} or throws Error with a user-facing message */
    function buildShares() {
        const cost = parseAmount(amount.value);
        if (!(cost > 0)) throw new Error("Enter an amount greater than 0.");
        const costCents = toCents(cost);
        const shares = [];

        if (state.payMode === "single") {
            if (state.payerId == null) throw new Error("Choose who paid.");
            shares.push({ user_id: state.payerId, share: -cost });
        } else {
            const paid = ids.map(id => [id, parseAmount(state.paid[id] || "0")]);
            if (paid.some(([, v]) => Number.isNaN(v))) throw new Error("Check the paid amounts.");
            const total = sumCents(paid.map(([, v]) => toCents(v)));
            if (total !== costCents) {
                throw new Error(`Paid amounts add up to ${money(total / 100)}, but the total is ${money(cost)}.`);
            }
            for (const [id, v] of paid) if (v > 0) shares.push({ user_id: id, share: -v });
        }

        const selected = ids.filter(id => state.selected.has(id));
        if (selected.length === 0) throw new Error("Pick at least one person to split between.");
        if (state.splitMode === "equal") {
            splitEqually(costCents, selected.length).forEach((cents, i) => {
                if (cents > 0) shares.push({ user_id: selected[i], share: cents / 100 });
            });
        } else {
            const parts = selected.map(id => [id, parseAmount(state.custom[id] || "0")]);
            if (parts.some(([, v]) => Number.isNaN(v))) throw new Error("Check the split amounts.");
            const total = sumCents(parts.map(([, v]) => toCents(v)));
            if (total !== costCents) {
                const left = (costCents - total) / 100;
                throw new Error(left > 0 ? `${money(left)} still to assign.` : `${money(-left)} too much assigned.`);
            }
            for (const [id, v] of parts) if (v > 0) shares.push({ user_id: id, share: v });
        }
        return { cost, shares };
    }

    function updateSummary() {
        const cost = parseAmount(amount.value);
        const count = state.selected.size;
        if (!(cost > 0) || count === 0) {
            summary.textContent = "";
            return;
        }
        if (state.splitMode === "equal") {
            const cents = splitEqually(toCents(cost), count);
            summary.textContent = count === 1
                ? `${nameOf[[...state.selected][0]]} covers the full ${money(cost)}.`
                : `${money(cents[cents.length - 1] / 100)} each for ${count} people.`;
        } else {
            try {
                buildShares();
                summary.textContent = "All assigned. ✓";
            } catch (err) {
                summary.textContent = err.message;
            }
        }
    }
    amount.addEventListener("input", updateSummary);

    // --- layout ----------------------------------------------------------------
    const form = el("form", { class: "expense-form", novalidate: true },
        el("div", { class: "amount-field" }, amount),
        description,
        el("div", { class: "field-group" }, category, categoryChips),
        el("datalist", { id: "category-options" }, categories.map(c => el("option", { value: c }))),
        paySection,
        splitSection,
        summary,
        el("details", { class: "more", open: !!(expense?.comment) },
            el("summary", {}, "Date & comment"),
            el("div", { class: "grid" }, date, comment)),
        error,
        el("div", { class: "actions" },
            submit,
            onCancel && el("button", { type: "button", class: "secondary outline", onclick: onCancel }, "Cancel")),
    );

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        showMessage(error, "");
        let built;
        try {
            if (!description.value.trim()) throw new Error("Add a short description.");
            if (!category.value.trim()) throw new Error("Pick or type a category.");
            if (!date.value) throw new Error("Pick a date.");
            built = buildShares();
        } catch (err) {
            showMessage(error, err.message);
            return;
        }
        submit.disabled = true;
        submit.setAttribute("aria-busy", "true");
        try {
            await onSubmit({
                date: date.value,
                description: description.value.trim(),
                category: category.value.trim(),
                comment: comment.value.trim(),
                ...built,
            });
        } catch (err) {
            showMessage(error, err.message || "Could not save.");
        } finally {
            submit.disabled = false;
            submit.removeAttribute("aria-busy");
        }
    });

    mount(root, form);
    render();
    syncCategoryChips();
    if (!expense) amount.focus();
    return form;
}
