// Profile: balance, settlements, expenses (Overview) and spending chart (Stats).
import { api } from "./api.js";
import { boot, showFatal } from "./layout.js";
import { consumedBy, expenseList } from "./expense-list.js";
import { renderSettlements } from "./settlements.js";
import { $, el, isSettlement, money, mount } from "./ui.js";

const userId = parseInt(window.location.pathname.split("/")[2], 10);

const CHART_COLORS = [
    "#4f46e5", "#f59e0b", "#10b981", "#ef4444", "#06b6d4",
    "#8b5cf6", "#ec4899", "#84cc16", "#f97316", "#64748b",
];
const WINDOW = 6; // periods shown at once

async function start() {
    const { me } = await boot();
    if (!me.is_admin && me.id !== userId) {
        window.location.href = `/users/${me.id}`;
        return;
    }
    const isSelf = me.id === userId;
    const [user, balances, settlements, expenses, users] = await Promise.all([
        isSelf ? me : api.getUser(userId), api.getBalances(), api.getSettlements(),
        api.getExpenses({ userId }), api.getUsers(),
    ]);
    const nameOf = Object.fromEntries(users.map(u => [u.id, u.name]));

    const overview = el("div", { role: "tabpanel", id: "panel-overview" });
    const stats = el("div", { role: "tabpanel", id: "panel-stats", hidden: true });
    let statsRendered = false;

    const tab = (label, panel) => el("button", {
        type: "button", role: "tab", "aria-controls": panel.id,
        onclick: (e) => selectTab(e.currentTarget, panel),
    }, label);
    const tabs = [tab("Overview", overview), tab("Stats", stats)];

    function selectTab(button, panel) {
        for (const t of tabs) t.setAttribute("aria-selected", String(t === button));
        overview.hidden = panel !== overview;
        stats.hidden = panel !== stats;
        if (panel === stats && !statsRendered) {
            renderStats(stats, expenses, userId);
            statsRendered = true;
        }
    }

    mount($("#page"),
        el("div", { class: "section-head" },
            el("h1", {}, user.name, !user.is_active ? el("small", { class: "badge" }, "inactive") : null),
            (isSelf || me.is_admin) && el("a", { href: `/users/${userId}/settings`, role: "button", class: "secondary outline small" }, "Account settings")),
        el("div", { role: "tablist", class: "tabs" }, tabs),
        overview,
        stats,
    );
    selectTab(tabs[0], overview);

    // Overview
    const balance = balances.find(b => b.user_id === userId)?.balance ?? 0;
    const settled = Math.abs(balance) < 0.005;
    const who = isSelf ? "You" : user.name;
    const settlementsBox = el("div");
    mount(overview,
        el("article", { class: `hero ${settled ? "" : balance > 0 ? "pos" : "neg"}` },
            el("p", { class: "hero-label" },
                settled ? `${who} ${isSelf ? "are" : "is"} all square` : `${who} ${balance > 0 ? (isSelf ? "are owed" : "is owed") : (isSelf ? "owe" : "owes")}`),
            el("p", { class: "hero-amount" }, money(Math.abs(balance)))),
        el("section", {}, el("h2", {}, "Settle up"), settlementsBox),
        el("section", {}, el("h2", {}, "Expenses"),
            expenseList(expenses, { nameOf, perspectiveId: userId, next: `/users/${userId}` })),
    );
    renderSettlements(settlementsBox,
        settlements.filter(s => s.from_user_id === userId || s.to_user_id === userId),
        { viewerId: isSelf ? me.id : null, onSettled: () => window.location.reload() });
}

function renderStats(panel, expenses, uid) {
    const own = expenses.filter(e => !isSettlement(e) && consumedBy(e, uid) > 0);
    if (own.length === 0) {
        mount(panel, el("p", { class: "muted empty" }, "No spending to show yet."));
        return;
    }

    const allCategories = [...new Set(own.map(e => e.category))].sort();
    const colorFor = Object.fromEntries(allCategories.map((c, i) => [c, CHART_COLORS[i % CHART_COLORS.length]]));
    let granularity = "month";
    let offset = 0;
    let chart = null;

    const tiles = el("div", { class: "stat-tiles" });
    const rangeLabel = el("span", { class: "range" });
    const backBtn = el("button", { type: "button", class: "secondary outline small", title: "Older", onclick: () => { offset += 1; update(); } }, "‹");
    const fwdBtn = el("button", { type: "button", class: "secondary outline small", title: "Newer", onclick: () => { offset -= 1; update(); } }, "›");
    const granBtn = el("button", {
        type: "button", class: "secondary small",
        onclick: () => {
            granularity = granularity === "month" ? "quarter" : "month";
            offset = 0;
            granBtn.textContent = granularity === "month" ? "By quarter" : "By month";
            update();
        },
    }, "By quarter");
    const canvas = el("canvas", { "aria-label": "Spending by period and category", role: "img" });

    mount(panel,
        tiles,
        el("h2", {}, "Share by category"),
        el("div", { class: "chart-controls" }, backBtn, rangeLabel, fwdBtn, granBtn),
        el("div", { class: "chart-box" }, canvas),
    );
    renderTiles(tiles, own, uid);

    const periodKey = (date) => granularity === "month"
        ? date.slice(0, 7)
        : `${date.slice(0, 4)}-Q${Math.floor((parseInt(date.slice(5, 7), 10) - 1) / 3) + 1}`;
    const periodLabel = (key) => {
        if (granularity === "quarter") return key.replace("-", " ");
        const [y, m] = key.split("-").map(Number);
        return new Date(y, m - 1, 1).toLocaleDateString(undefined, { month: "short", year: "numeric" });
    };

    function update() {
        const data = {};
        for (const e of own) {
            const key = periodKey(e.date);
            data[key] ??= {};
            data[key][e.category] = (data[key][e.category] ?? 0) + consumedBy(e, uid);
        }
        const periods = Object.keys(data).sort();
        const maxOffset = Math.max(0, periods.length - WINDOW);
        offset = Math.min(Math.max(offset, 0), maxOffset);
        const end = periods.length - offset;
        const visible = periods.slice(Math.max(0, end - WINDOW), end);
        backBtn.disabled = offset >= maxOffset;
        fwdBtn.disabled = offset <= 0;
        rangeLabel.textContent = visible.length === 1
            ? periodLabel(visible[0])
            : `${periodLabel(visible[0])} – ${periodLabel(visible[visible.length - 1])}`;

        const datasets = allCategories
            .filter(c => visible.some(p => data[p][c]))
            .map(c => ({
                label: c,
                data: visible.map(p => Math.round((data[p][c] ?? 0) * 100) / 100),
                backgroundColor: colorFor[c],
                borderRadius: 4,
            }));
        const labels = visible.map(periodLabel);

        if (chart) {
            chart.data.labels = labels;
            chart.data.datasets = datasets;
            chart.update();
            return;
        }
        const styles = getComputedStyle(document.documentElement);
        Chart.defaults.color = styles.getPropertyValue("--pico-muted-color").trim() || "#666";
        Chart.defaults.borderColor = styles.getPropertyValue("--pico-muted-border-color").trim() || "#ddd";
        chart = new Chart(canvas, {
            type: "bar",
            data: { labels, datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: { stacked: true, grid: { display: false } },
                    y: { stacked: true, beginAtZero: true, ticks: { callback: v => money(v) } },
                },
                plugins: {
                    legend: { position: "bottom" },
                    tooltip: { callbacks: { label: ctx => `${ctx.dataset.label}: ${money(ctx.parsed.y)}` } },
                },
            },
        });
    }

    update();
}

function renderTiles(container, own, uid) {
    const monthKey = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
    const now = new Date();
    const thisMonth = monthKey(now);
    const lastMonth = monthKey(new Date(now.getFullYear(), now.getMonth() - 1, 15));
    const byMonth = {};
    const byCategory = {};
    for (const e of own) {
        const share = consumedBy(e, uid);
        byMonth[e.date.slice(0, 7)] = (byMonth[e.date.slice(0, 7)] ?? 0) + share;
        byCategory[e.category] = (byCategory[e.category] ?? 0) + share;
    }
    const months = Object.values(byMonth);
    const average = months.reduce((a, b) => a + b, 0) / months.length;
    const [topCategory, topAmount] = Object.entries(byCategory).sort((a, b) => b[1] - a[1])[0];

    const tile = (label, value, sub) => el("div", { class: "tile" },
        el("span", { class: "tile-label" }, label),
        el("span", { class: "tile-value" }, value),
        sub && el("span", { class: "tile-sub muted" }, sub));
    mount(container,
        tile("This month", money(byMonth[thisMonth] ?? 0)),
        tile("Last month", money(byMonth[lastMonth] ?? 0)),
        tile("Monthly average", money(average), `${months.length} month${months.length === 1 ? "" : "s"}`),
        tile("Top category", topCategory, money(topAmount)),
    );
}

start().catch(showFatal);
