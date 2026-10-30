/* Точка входа: тема, маршрутизация, каркас приложения, общие действия. */

import { api, onUnauthorized } from "./api.js";
import { icon, mountIcons } from "./icons.js";
import { toast, clearToasts } from "./ui.js";
import { openTaskForm, openTaskDetail } from "./task-dialogs.js";
import { openEventForm } from "./event-dialog.js";
import { todayIso } from "./util.js";
import { renderAuth } from "./auth.js";
import HomeView from "./views/home.js";
import TasksView from "./views/tasks.js";
import CalendarView from "./views/calendar.js";
import ReviewView from "./views/review.js";
import ProfileView from "./views/profile.js";

const ROUTES = [
  { path: "/", view: HomeView, label: "Главная", icon: "home", mobile: true },
  { path: "/tasks", view: TasksView, label: "Задачи", icon: "tasks", mobile: true },
  { path: "/calendar", view: CalendarView, label: "Календарь", icon: "calendar", mobile: true },
  { path: "/review", view: ReviewView, label: "Итог дня", icon: "review", mobile: false },
  { path: "/profile", view: ProfileView, label: "Профиль", icon: "user", mobile: true },
];

const THEME_KEY = "planner-theme";
const appRoot = document.getElementById("app");

export const app = {
  user: null,
  config: { demoEnabled: true },
  themeMode: "system",
  state: {},

  go(path) {
    const current = window.location.pathname + window.location.search;
    clearToasts();
    if (current === path) {
      renderRoute();
      return;
    }
    window.history.pushState({}, "", path);
    renderRoute();
    window.scrollTo(0, 0);
  },

  async refresh({ keepScroll = true } = {}) {
    const y = window.scrollY;
    await renderRoute();
    if (keepScroll) window.scrollTo(0, y);
  },

  setUser(user) {
    this.user = user;
    if (user?.theme) {
      this.themeMode = user.theme;
    }
    applyTheme();
    updateHeader();
  },

  setTheme(mode) {
    this.themeMode = mode;
    window.localStorage.setItem(THEME_KEY, mode);
    applyTheme();
    if (this.user?.id) {
      api.updateMe({ theme: mode }).catch(() => {});
    }
  },

  openTaskForm(options = {}, onSaved) {
    return openTaskForm(app, {
      task: options.task ?? null,
      defaults: options.task ? {} : options,
      onSaved,
    });
  },

  openTaskDetail(taskId, onChanged) {
    return openTaskDetail(app, taskId, onChanged);
  },

  openEventForm(options = {}, onSaved) {
    return openEventForm(app, {
      event: options.event ?? null,
      defaults: options,
      onSaved,
    });
  },

  async signOut() {
    try {
      await api.logout();
    } catch {
      /* сессии уже нет */
    }
    this.user = null;
    renderAuth(app);
  },
};

/* ------------------------------------------------------------------ тема */
function systemTheme() {
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function applyTheme() {
  const mode = app.themeMode || "system";
  const resolved = mode === "system" ? systemTheme() : mode;
  document.documentElement.dataset.theme = resolved;
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", resolved === "dark" ? "#14161A" : "#1366EC");
  const toggle = document.querySelector("[data-theme-toggle]");
  if (toggle) {
    toggle.innerHTML = icon(resolved === "dark" ? "sun" : "moon");
    toggle.setAttribute(
      "aria-label",
      resolved === "dark" ? "Переключить на светлую тему" : "Переключить на тёмную тему"
    );
  }
}

function bindSystemTheme() {
  const media = window.matchMedia?.("(prefers-color-scheme: dark)");
  media?.addEventListener?.("change", () => {
    if (app.themeMode === "system") applyTheme();
  });
}

/* ------------------------------------------------------------------ каркас */

function navLinks() {
  return ROUTES.map(
    (item) => `<a class="main-nav__link" href="${item.path}" data-nav="${item.path}">
        ${icon(item.icon)}<span>${item.label}</span>
      </a>`
  ).join("");
}

function mobileLinks() {
  return ROUTES.filter((item) => item.mobile)
    .map(
      (item) => `<a class="bottom-nav__link" href="${item.path}" data-nav="${item.path}">
        ${icon(item.icon)}<span>${item.label}</span>
      </a>`
    )
    .join("");
}

function renderShell() {
  appRoot.innerHTML = `
    <a class="skip-link" href="#main">Перейти к содержимому</a>
    <header class="app-header">
      <div class="container app-header__inner">
        <a class="brand" href="/">
          <span class="brand__mark">${icon("check")}</span>
          <span class="brand__text">Планирование дня</span>
        </a>
        <nav class="main-nav" aria-label="Основная навигация">${navLinks()}</nav>
        <div class="header-tools">
          <button class="icon-button" type="button" data-theme-toggle aria-label="Переключить тему">
            ${icon("moon")}
          </button>
          <button class="avatar" type="button" data-profile aria-label="Профиль и настройки"></button>
        </div>
      </div>
    </header>
    <main class="app-main" id="main" tabindex="-1">
      <div class="container" id="view"></div>
    </main>
    <nav class="bottom-nav" aria-label="Мобильная навигация">${mobileLinks()}</nav>
    <button class="fab" type="button" data-fab aria-label="Новая задача">${icon("plus")}</button>
  `;

  appRoot.querySelector("[data-theme-toggle]")?.addEventListener("click", () => {
    const current = document.documentElement.dataset.theme;
    app.setTheme(current === "dark" ? "light" : "dark");
  });

  appRoot.querySelector("[data-profile]")?.addEventListener("click", () => app.go("/profile"));
  appRoot.querySelector("[data-fab]")?.addEventListener("click", () =>
    app.openTaskForm({ date: todayIso() }, () => app.refresh())
  );

  bindNavClicks(appRoot);
  updateHeader();
  applyTheme();
}

function updateHeader() {
  const avatar = appRoot.querySelector("[data-profile]");
  if (!avatar) return;
  const name = app.user?.name || "";
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const label =
    parts.length >= 2
      ? (parts[0][0] + parts[1][0]).toUpperCase()
      : (parts[0]?.[0] || "?").toUpperCase();
  avatar.textContent = label;
  avatar.title = name ? `${name} — настройки` : "Настройки";
}

function updateActiveNav(pathname) {
  appRoot.querySelectorAll("[data-nav]").forEach((link) => {
    if (link.dataset.nav === pathname) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
}

function bindNavClicks(scope) {
  scope.querySelectorAll("[data-nav]").forEach((link) => {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      app.go(link.dataset.nav);
    });
  });
}

/* ---------------------------------------------------------------- роутинг */

function matchRoute(pathname) {
  return ROUTES.find((route) => route.path === pathname) || ROUTES[0];
}

async function renderRoute() {
  if (!app.user) {
    renderAuth(app);
    return;
  }
  const route = matchRoute(window.location.pathname);
  const viewHost = document.getElementById("view");
  if (!viewHost) return;
  const container = document.createElement("div");
  container.className = "view";
  viewHost.replaceChildren(container);
  updateActiveNav(route.path);
  document.title = `${route.label} — Планирование дня`;
  try {
    await route.view.mount(container, app);
  } catch (error) {
    console.error(error);
    container.innerHTML = `<div class="empty">${icon("info")}<strong>Что-то пошло не так</strong>
      <span>${error.message}</span><button class="btn btn--secondary btn--sm" type="button"
      onclick="location.reload()">Перезагрузить</button></div>`;
  }
}

/* ------------------------------------------------------------- клавиатура */

function bindShortcuts() {
  document.addEventListener("keydown", (event) => {
    if (event.defaultPrevented) return;
    if (event.key === "Escape") return;
    const target = event.target;
    const typing =
      target instanceof HTMLElement &&
      (target.matches("input, textarea, select") || target.isContentEditable);
    if (typing) return;
    if (document.getElementById("modal")?.open) return;
    if (event.metaKey || event.ctrlKey || event.altKey) return;
    if (event.key.toLowerCase() === "n" || event.key.toLowerCase() === "т") {
      if (!app.user) return;
      event.preventDefault();
      app.openTaskForm({ date: todayIso() }, () => app.refresh());
    }
  });
}

/* ------------------------------------------------------------------- старт */

async function boot() {
  mountIcons();
  bindSystemTheme();
  bindShortcuts();

  try {
    app.config = await api.config();
  } catch {
    app.config = { demoEnabled: true };
  }

  const stored = window.localStorage.getItem(THEME_KEY);
  app.themeMode = stored || "system";
  applyTheme();

  onUnauthorized(() => {
    if (app.user) {
      app.user = null;
      toast("Сессия истекла — войдите снова");
      renderAuth(app);
    }
  });

  try {
    const response = await api.me();
    app.user = response.user;
    app.themeMode = response.user.theme || app.themeMode;
    window.localStorage.setItem(THEME_KEY, app.themeMode);
    applyTheme();
    renderShell();
    await renderRoute();
  } catch (error) {
    if (error.status === 401) {
      renderAuth(app);
      return;
    }
    appRoot.innerHTML = `<div class="empty" style="margin:10vh auto;max-width:520px">
        ${icon("info")}
        <strong>Не удалось подключиться</strong>
        <span>${error.message}</span>
        <button class="btn btn--primary btn--sm" type="button" onclick="location.reload()">Повторить</button>
      </div>`;
  }
}

window.addEventListener("popstate", () => {
  if (app.user) renderRoute();
});

window.addEventListener("planner:login", (event) => {
  const logged = event.detail?.user;
  if (!logged) return;
  app.user = logged;
  app.themeMode = logged.theme || app.themeMode;
  window.localStorage.setItem(THEME_KEY, app.themeMode);
  applyTheme();
  renderShell();
  app.go("/");
});

document.addEventListener("click", (event) => {
  const link = event.target.closest('a[href^="/"]');
  if (!link || link.dataset.nav) return;
  if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
  if (link.target === "_blank" || link.hasAttribute("download")) return;
  event.preventDefault();
  app.go(link.getAttribute("href"));
});

boot();
