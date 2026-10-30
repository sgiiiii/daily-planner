/* Экран входа и регистрации. */

import { api } from "./api.js";
import { icon } from "./icons.js";
import { busy } from "./ui.js";

export function renderAuth(app) {
  document.title = "Вход — Планирование дня";
  const root = document.getElementById("app");
  const demoEnabled = app.config?.demoEnabled !== false;

  root.innerHTML = `
    <div class="auth">
      <aside class="auth__brand">
        <span class="brand">
          <span class="brand__mark">${icon("check")}</span>
          <span class="brand__text">Планирование дня</span>
        </span>

        <div class="auth__pitch">
          <h1>Все дела дня — в одном списке</h1>
          <p>
            Рабочие, учебные и личные задачи рядом. Видно, что горит, а что может подождать.
            Незакрытые дела ежедневник перенесёт на завтра сам.
          </p>
          <ul class="auth__features">
            <li>${icon("check")}Единый список задач с приоритетами и сферами</li>
            <li>${icon("check")}Автоматический перенос невыполненного</li>
            <li>${icon("check")}Краткая сводка дня вместо потока уведомлений</li>
            <li>${icon("check")}Светлая и тёмная темы</li>
          </ul>
        </div>

        <p class="caption" style="color:rgba(255,255,255,.72)">
          Цифровой ежедневник · учебный проект · КАИ, 2026
        </p>
      </aside>

      <div class="auth__card">
        <div class="auth__form">
          <div class="brand" style="margin-bottom:4px">
            <span class="brand__mark">${icon("check")}</span>
            <span class="brand__text">Планирование дня</span>
          </div>

          <h2 data-auth-title>Войти в ежедневник</h2>
          <p class="subtitle" data-auth-subtitle>Продолжите с того места, где остановились</p>

          <div class="auth__tabs" role="tablist" aria-label="Вход или регистрация">
            <button class="auth__tab" type="button" role="tab" data-mode="login" aria-selected="true">Вход</button>
            <button class="auth__tab" type="button" role="tab" data-mode="register" aria-selected="false">Регистрация</button>
          </div>

          <form data-auth-form novalidate autocomplete="on">
            <div class="field" data-name-field hidden style="margin-bottom:16px">
              <label class="field__label" for="auth-name">Как к вам обращаться</label>
              <input class="input" id="auth-name" name="name" type="text" maxlength="60"
                placeholder="Например, Марсель" autocomplete="name">
            </div>
            <div class="field" style="margin-bottom:16px">
              <label class="field__label" for="auth-login">Логин</label>
              <input class="input" id="auth-login" name="login" type="text" autocomplete="username"
                inputmode="latin" spellcheck="false" placeholder="demo">
            </div>
            <div class="field" style="margin-bottom:8px">
              <label class="field__label" for="auth-password">Пароль</label>
              <input class="input" id="auth-password" name="password" type="password"
                autocomplete="current-password" placeholder="Ваш пароль">
            </div>
            <p class="field__error" data-auth-error style="min-height:20px"></p>
            <button class="btn btn--primary btn--lg btn--block" type="submit" data-submit>Войти</button>
          </form>

          ${
            demoEnabled
              ? `<div class="auth__demo">
            <span>Демо-доступ: <code>demo</code> / <code>demo1234</code></span>
            <button class="btn btn--secondary btn--sm" type="button" data-demo>Войти как демо</button>
          </div>`
              : ""
          }

          <p class="auth__footer">
            Данные хранятся на сервере приложения. Пароли — только в виде PBKDF2-хэша,
            сессия — в HttpOnly-cookie.
          </p>
        </div>
      </div>
    </div>
  `;

  const form = root.querySelector("[data-auth-form]");
  const loginInput = root.querySelector("#auth-login");
  const passwordInput = root.querySelector("#auth-password");
  const nameInput = root.querySelector("#auth-name");
  const nameField = root.querySelector("[data-name-field]");
  const errorBox = root.querySelector("[data-auth-error]");
  const submit = root.querySelector("[data-submit]");
  const title = root.querySelector("[data-auth-title]");
  const subtitle = root.querySelector("[data-auth-subtitle]");
  let mode = "login";
  let busyFlag = false;

  const setMode = (next) => {
    mode = next;
    root.querySelectorAll("[data-mode]").forEach((tab) =>
      tab.setAttribute("aria-selected", String(tab.dataset.mode === mode))
    );
    nameField.hidden = mode === "login";
    title.textContent = mode === "login" ? "Войти в ежедневник" : "Создать аккаунт";
    subtitle.textContent =
      mode === "login"
        ? "Продолжите с того места, где остановились"
        : "Пара шагов — и ежедневник готов к работе";
    submit.textContent = mode === "login" ? "Войти" : "Зарегистрироваться";
    passwordInput.autocomplete = mode === "login" ? "current-password" : "new-password";
    passwordInput.placeholder = mode === "login" ? "Ваш пароль" : "Не меньше 8 символов";
    errorBox.textContent = "";
    root.querySelectorAll("[aria-invalid]").forEach((input) => input.removeAttribute("aria-invalid"));
  };

  root.querySelectorAll("[data-mode]").forEach((tab) =>
    tab.addEventListener("click", () => setMode(tab.dataset.mode))
  );

  const showError = (message, fields = {}) => {
    errorBox.textContent = message;
    if (fields.login) loginInput.setAttribute("aria-invalid", "true");
    if (fields.password) passwordInput.setAttribute("aria-invalid", "true");
    if (fields.name) nameInput.setAttribute("aria-invalid", "true");
  };

  const enter = (user) => {
    window.dispatchEvent(new CustomEvent("planner:login", { detail: { user } }));
  };

  const submitForm = async (payload) => {
    if (busyFlag) return;
    errorBox.textContent = "";
    root.querySelectorAll("[aria-invalid]").forEach((input) => input.removeAttribute("aria-invalid"));

    if (!payload.login.trim()) {
      showError("Введите логин", { login: true });
      loginInput.focus();
      return;
    }
    if (!payload.password) {
      showError("Введите пароль", { password: true });
      passwordInput.focus();
      return;
    }
    if (mode === "register" && payload.password.length < 8) {
      showError("Пароль должен быть не короче 8 символов", { password: true });
      passwordInput.focus();
      return;
    }

    busyFlag = true;
    busy(submit, true, mode === "login" ? "Входим…" : "Создаём…");
    try {
      const response =
        mode === "login" ? await api.login(payload) : await api.register(payload);
      enter(response.user);
    } catch (error) {
      showError(error.message, error.fields);
      busyFlag = false;
      busy(submit, false);
    }
  };

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    submitForm({
      login: loginInput.value,
      password: passwordInput.value,
      name: nameInput.value.trim(),
    });
  });

  root.querySelector("[data-demo]")?.addEventListener("click", () => {
    setMode("login");
    loginInput.value = "demo";
    passwordInput.value = "demo1234";
    submitForm({ login: "demo", password: "demo1234", name: "" });
  });

  window.setTimeout(() => loginInput.focus(), 60);
}
