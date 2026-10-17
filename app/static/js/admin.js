// Admin: manage users and app settings.
import { api } from "./api.js";
import { boot, showFatal } from "./layout.js";
import { $, confirmButton, el, setCurrency, showMessage, toast, mount } from "./ui.js";

const CURRENCIES = ["EUR", "USD", "GBP", "CHF", "SEK", "NOK", "DKK", "PLN", "CZK", "HUF"];

let me;

async function start() {
    ({ me } = await boot({ admin: true }));
    const usersBox = el("div");
    const settingsBox = el("div");
    mount($("#page"),
        el("h1", {}, "Admin"),
        el("section", {}, el("h2", {}, "Flatmates & admins"), usersBox, addUserForm(() => loadUsers(usersBox))),
        el("section", {}, el("h2", {}, "Settings"), settingsBox),
    );
    await Promise.all([loadUsers(usersBox), loadSettings(settingsBox)]);
}

async function loadUsers(box) {
    const users = await api.getUsers();
    mount(box, el("ul", { class: "user-list" }, users.map(u => userRow(u, () => loadUsers(box)))));
}

function userRow(user, reload) {
    const isMe = user.id === me.id;
    const act = (label, confirmLabel, payload, attrs = {}) => confirmButton(label, confirmLabel, async () => {
        try {
            await (payload === "delete" ? api.deleteUser(user.id) : api.updateUser(user.id, payload));
            toast(`${user.name} updated`);
            await reload();
        } catch (err) {
            toast(err.message, "error");
        }
    }, { class: "outline secondary small", ...attrs });

    return el("li", { class: user.is_active ? "" : "inactive" },
        el("div", { class: "user-main" },
            user.is_admin ? el("strong", {}, user.name) : el("a", { href: `/users/${user.id}` }, el("strong", {}, user.name)),
            isMe && el("small", { class: "badge" }, "you"),
            user.is_admin && el("small", { class: "badge accent" }, "admin"),
            !user.is_active && el("small", { class: "badge" }, "inactive"),
            user.must_change_password && el("small", { class: "badge", title: "Has not set their own password yet" }, "temp password"),
        ),
        el("div", { class: "user-actions" },
            el("a", { href: `/users/${user.id}/settings`, role: "button", class: "outline secondary small" }, isMe ? "Account" : "Reset password"),
            !isMe && act(user.is_admin ? "Revoke admin" : "Make admin", "Confirm?", { is_admin: !user.is_admin }),
            !isMe && act(user.is_active ? "Deactivate" : "Activate", "Confirm?", { is_active: !user.is_active }),
            !isMe && act("Delete", "Sure?", "delete", {
                title: "Only possible for users without expenses — deactivate otherwise",
            }),
        ),
    );
}

function randomPassword() {
    const alphabet = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789";
    const bytes = crypto.getRandomValues(new Uint8Array(12));
    return Array.from(bytes, b => alphabet[b % alphabet.length]).join("");
}

function addUserForm(reload) {
    const name = el("input", { placeholder: "Name", autocomplete: "off", required: true, maxlength: "50", "aria-label": "Name" });
    const password = el("input", { placeholder: "Temporary password", autocomplete: "off", required: true, minlength: "8", "aria-label": "Temporary password" });
    const msg = el("p", { hidden: true });
    const submit = el("button", { type: "submit" }, "Add");
    return el("article", { class: "add-user" },
        el("h3", {}, "Add flatmate"),
        el("form", {
            onsubmit: async (e) => {
                e.preventDefault();
                submit.disabled = true;
                try {
                    const user = await api.createUser({ name: name.value.trim(), password: password.value });
                    showMessage(msg, `Added ${user.name}. Temporary password: ${password.value} (they choose their own at first login)`, "success");
                    name.value = "";
                    password.value = "";
                    await reload();
                } catch (err) {
                    showMessage(msg, err.status === 409 ? "That name is taken." : err.message);
                } finally {
                    submit.disabled = false;
                }
            },
        },
            el("div", { class: "grid" },
                name,
                el("div", { role: "group" }, password,
                    el("button", { type: "button", class: "secondary", onclick: () => { password.value = randomPassword(); } }, "Generate"))),
            submit,
            msg,
        ),
    );
}

async function loadSettings(box) {
    const settings = await api.getSettings();
    const msg = el("p", { hidden: true });

    async function save(patch) {
        try {
            const updated = await api.updateSettings(patch);
            setCurrency(updated.currency);
            toast("Settings saved");
            await loadSettings(box);
        } catch (err) {
            showMessage(msg, err.message);
        }
    }

    const mode = (value, label, hint) => el("label", { class: "radio-card" },
        el("input", { type: "radio", name: "mode", value, checked: settings.settlement_mode === value, onchange: () => save({ settlement_mode: value }) }),
        el("span", {}, el("strong", {}, label), el("small", { class: "muted" }, hint)));

    const currencies = CURRENCIES.includes(settings.currency) ? CURRENCIES : [settings.currency, ...CURRENCIES];
    mount(box, el("article", {},
        el("fieldset", {},
            el("legend", {}, "Settlement mode"),
            mode("simplified", "Simplified", "Fewest transfers: everyone settles their net balance."),
            mode("full", "Full", "Pay back each person you owe, pair by pair."),
        ),
        el("label", {}, "Currency",
            el("select", { onchange: (e) => save({ currency: e.target.value }) },
                currencies.map(c => el("option", { value: c, selected: c === settings.currency }, c)))),
        el("small", { class: "muted" }, "Used for new expenses and for showing amounts."),
        msg,
    ));
}

start().catch(showFatal);
