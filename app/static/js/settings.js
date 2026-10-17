// Account settings: rename, change own password, or (admin) reset someone's password.
import { api } from "./api.js";
import { boot, showFatal } from "./layout.js";
import { $, el, showMessage, toast, mount } from "./ui.js";

const userId = parseInt(window.location.pathname.split("/")[2], 10);

async function start() {
    const { me } = await boot({ allowPasswordChange: true });
    if (!me.is_admin && me.id !== userId) {
        window.location.href = `/users/${me.id}/settings`;
        return;
    }
    const isSelf = me.id === userId;
    const user = isSelf ? me : await api.getUser(userId);
    const forced = isSelf && me.must_change_password;

    // --- name ----------------------------------------------------------------
    const nameInput = el("input", { value: user.name, autocomplete: "username", required: true, maxlength: "50", "aria-label": "Name" });
    const nameMsg = el("p", { hidden: true });
    const nameForm = el("form", {
        onsubmit: async (e) => {
            e.preventDefault();
            try {
                await api.updateUser(userId, { name: nameInput.value.trim() });
                showMessage(nameMsg, "Name updated.", "success");
            } catch (err) {
                showMessage(nameMsg, err.status === 409 ? "That name is taken." : err.message);
            }
        },
    }, el("div", { role: "group" }, nameInput, el("button", { type: "submit" }, "Save")), nameMsg);

    // --- password ------------------------------------------------------------
    const current = isSelf && el("input", {
        type: "password", autocomplete: "current-password", required: true,
        placeholder: forced ? "Current (temporary) password" : "Current password", "aria-label": "Current password",
    });
    const fresh = el("input", { type: "password", autocomplete: "new-password", required: true, minlength: "8", placeholder: "New password (min. 8 characters)", "aria-label": "New password" });
    const confirm = el("input", { type: "password", autocomplete: "new-password", required: true, placeholder: "Repeat new password", "aria-label": "Repeat new password" });
    const pwMsg = el("p", { hidden: true });
    const pwForm = el("form", {
        onsubmit: async (e) => {
            e.preventDefault();
            if (fresh.value.length < 8) return showMessage(pwMsg, "Use at least 8 characters.");
            if (fresh.value !== confirm.value) return showMessage(pwMsg, "Passwords don't match.");
            try {
                await api.updateUser(userId, { password: fresh.value, ...(isSelf ? { current_password: current.value } : {}) });
                pwForm.reset();
                if (forced) {
                    toast("Password set. Welcome!");
                    window.location.href = me.is_admin ? "/admin" : "/";
                    return;
                }
                showMessage(pwMsg, isSelf ? "Password changed. Other devices were logged out." :
                    `Temporary password set. ${user.name} must change it at next login.`, "success");
            } catch (err) {
                showMessage(pwMsg, err.message);
            }
        },
    }, current, fresh, confirm, el("button", { type: "submit" }, isSelf ? "Change password" : "Set temporary password"), pwMsg);

    mount($("#page"),
        !forced && el("a", { href: me.is_admin ? "/admin" : `/users/${userId}`, class: "back" }, "← Back"),
        el("h1", {}, isSelf ? "Your account" : `${user.name}'s account`),
        forced && el("article", { class: "message notice" },
            el("strong", {}, "Choose your own password. "),
            "You're using a temporary password. Set a new one to continue."),
        !forced && el("article", {}, el("h2", {}, "Name"), nameForm),
        el("article", {}, el("h2", {}, isSelf ? "Password" : "Reset password"), pwForm),
    );
    (forced ? current : nameInput).focus();
}

start().catch(showFatal);
