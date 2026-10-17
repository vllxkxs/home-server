// Single source for all API calls.

async function request(path, options = {}) {
    const res = await fetch(path, {
        credentials: "same-origin",
        ...options,
        headers: {
            "Content-Type": "application/json",
            ...(options.headers || {}),
        },
    });

    if (!res.ok) {
        const err = new Error(await errorMessage(res));
        err.status = res.status;
        throw err;
    }
    return res.status !== 204 ? res.json() : null;
}

async function errorMessage(res) {
    const text = await res.text();
    try {
        const { detail } = JSON.parse(text);
        if (typeof detail === "string") return detail;
        // Pydantic validation errors: [{loc, msg}, ...]
        if (Array.isArray(detail)) {
            return detail.map(d => `${d.loc?.slice(1).join(".") || "input"}: ${d.msg}`).join("; ");
        }
    } catch { /* not JSON */ }
    return text || res.statusText;
}

const json = (method, body) => ({ method, body: JSON.stringify(body) });

export const api = {
    login: (payload) => request("/api/auth/login", json("POST", payload)),
    logout: () => request("/api/auth/logout", { method: "POST" }),

    getMe: () => request("/api/users/me"),
    getUsers: () => request("/api/users/"),
    getUser: (userId) => request(`/api/users/${userId}`),
    createUser: (payload) => request("/api/users/", json("POST", payload)),
    updateUser: (userId, payload) => request(`/api/users/${userId}`, json("PATCH", payload)),
    deleteUser: (userId) => request(`/api/users/${userId}`, { method: "DELETE" }),

    getExpenses: ({ userId } = {}) =>
        request(userId != null ? `/api/expenses/?user_id=${userId}` : "/api/expenses/"),
    getExpense: (expenseId) => request(`/api/expenses/${expenseId}`),
    getCategories: () => request("/api/expenses/categories"),
    addExpense: (expense) => request("/api/expenses/", json("POST", expense)),
    updateExpense: (expenseId, payload) => request(`/api/expenses/${expenseId}`, json("PATCH", payload)),
    deleteExpense: (expenseId) => request(`/api/expenses/${expenseId}`, { method: "DELETE" }),

    getBalances: () => request("/api/balances/"),
    // mode omitted -> server uses the app setting
    getSettlements: () => request("/api/balances/settlements/"),

    getSettings: () => request("/api/settings/"),
    updateSettings: (payload) => request("/api/settings/", json("PATCH", payload)),
};

export function redirectToLogin() {
    const next = window.location.pathname + window.location.search;
    window.location.href = `/?next=${encodeURIComponent(next)}`;
}
