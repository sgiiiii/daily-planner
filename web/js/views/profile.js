/* Экран «Профиль»: настройки пользователя, тема, планирование, безопасность. */

import { api } from "../api.js";
import { icon } from "../icons.js";
import { busy, confirmDialog, toast } from "../ui.js";
import { addDaysIso, esc, fmtDateNumeric, initials, todayIso } from "../util.js";

const SECTIONS = [
  { id: "profile", label: "Профиль" },
  { id: "appearance", label: "Внешний вид" },
  { id: "planning", label: "Планирование" },
  { id: "security", label: "Безопасность" },
  { id: "data", label: "Данные" },
  { id: "about", label: "О приложении" },
];

const THEMES = [
  { value: "light", label: "Светлая", hint: "Всегда светлое оформление" },
  { value: "dark", label: "Тёмная", hint: "Всегда тёмное оформление" },
  { value: "system", label: "Системная", hint: "Как в операционной системе" },
];

export default {
  name: "profile",

  async mount(root, app) {
    let section = "profile";

    const draw = () => {
      const user = app.user;
      const theme = app.themeMode;

      root.innerHTML = `
        <div class="page-head">
          <div class="page-head__title">
            <p class="eyebrow">Профиль</p>
            <h1>Настройки</h1>
            <p class="subtitle">Аккаунт, тема оформления и правила планирования</p>
          </div>
        </div>

        <div class="profile">
          <nav class="profile__menu" aria-label="Разделы настроек">
            ${SECTIONS.map(
              (item) => `<button type="button" data-section="${item.id}" aria-current="${
                section === item.id
              }">${item.label}</button>`
            ).join("")}
          </nav>

          <div class="profile__content">
            ${section === "profile" ? renderProfile(user) : ""}
            ${section === "appearance" ? renderAppearance(theme, user) : ""}
            ${section === "planning" ? renderPlanning(user) : ""}
            ${section === "security" ? renderSecurity() : ""}
            ${section === "data" ? renderData(user) : ""}
            ${section === "about" ? renderAbout(app) : ""}
          </div>
        </div>
      `;

      root.querySelectorAll("[data-section]").forEach((button) =>
        button.addEventListener("click", () => {
          section = button.dataset.section;
          draw();
        })
      );

      bindProfile();
      bindAppearance();
      bindPlanning();
      bindSecurity();
      bindData();
    };

    const renderProfile = (user) => `
      <section class="card">
        <div class="profile-head" style="margin-bottom:24px">
          <div class="profile-avatar">${esc(initials(user.name))}</div>
          <div class="profile-head__text">
            <h2>${esc(user.name)}</h2>
            <span class="muted">Логин: ${esc(user.login)}</span>
            <span class="caption">В приложении с ${esc(fmtDateNumeric(user.createdAt?.slice(0, 10) || ""))}</span>
          </div>
        </div>

        <form data-name-form autocomplete="off" class="form-grid">
          <div class="field field--wide">
            <label class="field__label" for="user-name">Как к вам обращаться</label>
            <input class="input" id="user-name" name="name" type="text" maxlength="60" value="${esc(user.name)}">
            <div class="field__error" data-error="name"></div>
          </div>
          <div class="field field--wide">
            <label class="field__label" for="user-login">Логин</label>
            <input class="input" id="user-login" type="text" value="${esc(user.login)}" readonly>
            <span class="field__hint">Логин изменить нельзя: он используется для входа</span>
          </div>
          <div class="field field--wide" style="display:flex;justify-content:flex-end">
            <button class="btn btn--primary" type="submit">Сохранить имя</button>
          </div>
        </form>
      </section>
    `;

    const renderAppearance = (theme, user) => `
      <section class="card">
        <div class="card__head"><h2>Тема оформления</h2></div>
        <div class="radio-row" role="radiogroup" aria-label="Тема оформления">
          ${THEMES.map(
            (item) => `
            <button class="radio-card" type="button" role="radio" data-theme-option="${item.value}"
              aria-checked="${theme === item.value}">
              <strong>${item.label}</strong>
              <span class="caption">${item.hint}</span>
            </button>`
          ).join("")}
        </div>
        <p class="small muted" style="margin-top:16px">
          Выбор сохраняется в аккаунте и применяется на всех устройствах. Переключатель в шапке
          меняет тему одним нажатием.
        </p>
      </section>
      <section class="card">
        <div class="card__head"><h2>Доступность</h2></div>
        <ul class="about-list">
          <li>${icon("check")}Все элементы управления — не меньше 44×44 px, удобно нажимать пальцем</li>
          <li>${icon("check")}Контраст текста соответствует WCAG AA (проверено в ЛР4)</li>
          <li>${icon("check")}Полное управление с клавиатуры и видимый фокус</li>
          <li>${icon("check")}Анимации отключаются системной настройкой «уменьшить движение»</li>
        </ul>
      </section>
    `;

    const renderPlanning = (user) => `
      <section class="card">
        <div class="card__head"><h2>Ежедневный перенос</h2></div>
        <div class="settings-row">
          <div class="settings-row__text">
            <strong>Время переноса невыполненных задач</strong>
            <span>В это время планировщик перенесёт незакрытые дела на текущий день</span>
          </div>
          <div style="display:flex;gap:8px;align-items:center">
            <input class="input" type="time" style="width:130px" data-rollover-time
              value="${esc(user.rolloverTime)}" aria-label="Время переноса">
            <button class="btn btn--secondary btn--sm" type="button" data-save-rollover>Сохранить</button>
          </div>
        </div>
        <div class="settings-row">
          <div class="settings-row__text">
            <strong>Краткая сводка дня</strong>
            <span>Показывать приоритетные задачи на главном экране</span>
          </div>
          <button class="switch" type="button" role="switch" data-summary-toggle
            aria-checked="${user.summaryEnabled}" aria-label="Краткая сводка дня"></button>
        </div>
        <p class="small muted" style="margin-top:16px">
          Задачи с прошедшим сроком переносятся автоматически, сохраняя приоритет и сферу.
          Номер дня переноса отмечается значком «перенесена».
        </p>
      </section>
    `;

    const renderSecurity = () => `
      <section class="card">
        <div class="card__head"><h2>Смена пароля</h2></div>
        <form data-password-form class="form-grid" autocomplete="off">
          <div class="field field--wide">
            <label class="field__label" for="pwd-current">Текущий пароль</label>
            <input class="input" id="pwd-current" type="password" autocomplete="current-password">
            <div class="field__error" data-error="current"></div>
          </div>
          <div class="field">
            <label class="field__label" for="pwd-new">Новый пароль</label>
            <input class="input" id="pwd-new" type="password" autocomplete="new-password">
            <div class="field__error" data-error="password"></div>
          </div>
          <div class="field">
            <label class="field__label" for="pwd-repeat">Повторите пароль</label>
            <input class="input" id="pwd-repeat" type="password" autocomplete="new-password">
            <div class="field__error" data-error="repeat"></div>
          </div>
          <div class="field field--wide" style="display:flex;justify-content:flex-end">
            <button class="btn btn--primary" type="submit">Изменить пароль</button>
          </div>
        </form>
        <p class="small muted" style="margin-top:12px">
          Пароль хранится в виде PBKDF2-хэша с индивидуальной солью — в открытом виде его нет ни в базе, ни в логах.
        </p>
      </section>
    `;

    const renderData = (user) => `
      <section class="card">
        <div class="card__head"><h2>Данные аккаунта</h2></div>
        <div class="settings-row">
          <div class="settings-row__text">
            <strong>Перенести невыполненные задачи сейчас</strong>
            <span>Тот же перенос, который выполняется по расписанию</span>
          </div>
          <button class="btn btn--secondary btn--sm" type="button" data-rollover>${icon("refresh")}Выполнить перенос</button>
        </div>
        <div class="settings-row">
          <div class="settings-row__text">
            <strong>Экспорт данных</strong>
            <span>Задачи и события в формате JSON</span>
          </div>
          <button class="btn btn--secondary btn--sm" type="button" data-export>${icon("arrow-right")}Скачать</button>
        </div>
        <div class="settings-row">
          <div class="settings-row__text">
            <strong>Выйти из аккаунта</strong>
            <span>Сессия завершится на этом устройстве</span>
          </div>
          <button class="btn btn--secondary btn--sm" type="button" data-logout>${icon("logout")}Выйти</button>
        </div>
        <div class="settings-row">
          <div class="settings-row__text">
            <strong style="color:var(--error)">Удалить аккаунт</strong>
            <span>Все задачи и события будут удалены безвозвратно</span>
          </div>
          <button class="btn btn--danger btn--sm" type="button" data-delete-account>Удалить</button>
        </div>
      </section>
    `;

    const renderAbout = (application) => `
      <section class="card">
        <div class="card__head"><h2>«Планирование дня»</h2><span class="badge badge--soft">v1.0.0</span></div>
        <p class="small" style="color:var(--text-2);line-height:24px">
          Цифровой ежедневник, собранный по материалам лабораторных работ: исследование и персоны,
          вайрфреймы, UI-кит, hi-fi прототип, тёмная тема и юзабилити-тестирование.
        </p>
        <ul class="about-list" style="margin-top:16px">
          <li>${icon("check")}Единый список задач на день, фильтры по сферам и приоритетам</li>
          <li>${icon("check")}Автоматический перенос незакрытых дел с сохранением приоритета и сферы</li>
          <li>${icon("check")}Сводка дня, итоги дня и календарь встреч в одних данных</li>
          <li>${icon("check")}Светлая и тёмная темы на семантических токенах</li>
        </ul>
        <div class="settings-row" style="margin-top:8px">
          <div class="settings-row__text">
            <strong>Горячие клавиши</strong>
            <span><kbd>N</kbd> — новая задача, <kbd>Esc</kbd> — закрыть окно</span>
          </div>
        </div>
        <p class="caption" style="margin-top:16px">
          Python 3 · PostgreSQL или SQLite · нативный JavaScript без сборки
        </p>
      </section>
    `;

    function bindProfile() {
      const form = root.querySelector("[data-name-form]");
      form?.addEventListener("submit", async (event) => {
        event.preventDefault();
        const input = form.querySelector("#user-name");
        const name = input.value.trim();
        if (!name) {
          form.querySelector('[data-error="name"]').textContent = "Имя не может быть пустым";
          input.setAttribute("aria-invalid", "true");
          return;
        }
        try {
          const response = await api.updateMe({ name });
          app.setUser(response.user);
          toast("Имя сохранено");
          draw();
        } catch (error) {
          toast(error.message, { duration: 5000 });
        }
      });
    }

    function bindAppearance() {
      root.querySelectorAll("[data-theme-option]").forEach((button) =>
        button.addEventListener("click", async () => {
          const mode = button.dataset.themeOption;
          app.setTheme(mode);
          root.querySelectorAll("[data-theme-option]").forEach((node) =>
            node.setAttribute("aria-checked", String(node.dataset.themeOption === mode))
          );
          try {
            const response = await api.updateMe({ theme: mode });
            app.setUser(response.user);
          } catch (error) {
            toast(error.message, { duration: 5000 });
          }
        })
      );
    }

    function bindPlanning() {
      root.querySelector("[data-save-rollover]")?.addEventListener("click", async (event) => {
        const button = event.currentTarget;
        const time = root.querySelector("[data-rollover-time]").value;
        busy(button, true, "Сохраняем…");
        try {
          const response = await api.updateMe({ rolloverTime: time });
          app.setUser(response.user);
          toast("Время переноса сохранено");
        } catch (error) {
          toast(error.message, { duration: 5000 });
        } finally {
          busy(button, false);
        }
      });

      root.querySelector("[data-summary-toggle]")?.addEventListener("click", async (event) => {
        const button = event.currentTarget;
        const next = button.getAttribute("aria-checked") !== "true";
        button.setAttribute("aria-checked", String(next));
        try {
          const response = await api.updateMe({ summaryEnabled: next });
          app.setUser(response.user);
        } catch (error) {
          button.setAttribute("aria-checked", String(!next));
          toast(error.message, { duration: 5000 });
        }
      });
    }

    function bindSecurity() {
      const form = root.querySelector("[data-password-form]");
      form?.addEventListener("submit", async (event) => {
        event.preventDefault();
        form.querySelectorAll("[data-error]").forEach((node) => (node.textContent = ""));
        const current = form.querySelector("#pwd-current").value;
        const password = form.querySelector("#pwd-new").value;
        const repeat = form.querySelector("#pwd-repeat").value;
        if (password.length < 8) {
          form.querySelector('[data-error="password"]').textContent = "Не меньше 8 символов";
          return;
        }
        if (password !== repeat) {
          form.querySelector('[data-error="repeat"]').textContent = "Пароли не совпадают";
          return;
        }
        const button = form.querySelector("button[type='submit']");
        busy(button, true, "Сохраняем…");
        try {
          await api.changePassword({ current, password });
          form.reset();
          toast("Пароль изменён");
        } catch (error) {
          const field = Object.keys(error.fields || {})[0];
          if (field) {
            const holder = form.querySelector(`[data-error="${field === "password" ? "password" : field}"]`);
            if (holder) holder.textContent = error.message;
          } else {
            toast(error.message, { duration: 5000 });
          }
        } finally {
          busy(button, false);
        }
      });
    }

    function bindData() {
      root.querySelector("[data-rollover]")?.addEventListener("click", async (event) => {
        const button = event.currentTarget;
        busy(button, true, "Переносим…");
        try {
          const result = await api.rollover();
          toast(result.moved ? `Перенесено задач: ${result.moved}` : "Нечего переносить — все дела в срок");
        } catch (error) {
          toast(error.message, { duration: 5000 });
        } finally {
          busy(button, false);
        }
      });

      root.querySelector("[data-export]")?.addEventListener("click", async () => {
        try {
          const [tasks, events] = await Promise.all([
            api.tasks.list({ status: "all" }),
            api.events.list(addDaysIso(todayIso(), -30), addDaysIso(todayIso(), 60)).catch(() => ({ events: [] })),
          ]);
          const payload = {
            exportedAt: new Date().toISOString(),
            user: { login: app.user.login, name: app.user.name },
            tasks: tasks.tasks,
            events: events.events || [],
          };
          const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
          const url = URL.createObjectURL(blob);
          const link = document.createElement("a");
          link.href = url;
          link.download = `planner-${new Date().toISOString().slice(0, 10)}.json`;
          link.click();
          URL.revokeObjectURL(url);
          toast("Файл с данными готов");
        } catch (error) {
          toast(error.message, { duration: 5000 });
        }
      });

      root.querySelector("[data-logout]")?.addEventListener("click", async () => {
        const confirmed = await confirmDialog({
          title: "Выйти из аккаунта?",
          text: "Сессия завершится. Данные останутся в аккаунте.",
          confirmLabel: "Выйти",
        });
        if (confirmed) app.signOut();
      });

      root.querySelector("[data-delete-account]")?.addEventListener("click", async () => {
        const confirmed = await confirmDialog({
          title: "Удалить аккаунт навсегда?",
          text: "Все задачи, события и настройки будут удалены. Это действие нельзя отменить.",
          confirmLabel: "Удалить аккаунт",
          danger: true,
        });
        if (!confirmed) return;
        try {
          await api.deleteAccount();
          toast("Аккаунт удалён");
          app.signOut();
        } catch (error) {
          toast(error.message, { duration: 5000 });
        }
      });
    }

    draw();
  },
};
