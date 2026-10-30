/* Общие элементы интерфейса: тосты, модальные окна, подтверждения. */

import { icon } from "./icons.js";
import { esc } from "./util.js";

/* ------------------------------------------------------------------ тосты */

function toastHost() {
  return document.getElementById("toasts");
}

export function toast(message, { actionLabel = null, onAction = null, duration = 6000 } = {}) {
  const host = toastHost();
  if (!host) return { dismiss() {} };

  const element = document.createElement("div");
  element.className = "toast";
  element.innerHTML = `<span class="toast__text">${esc(message)}</span>`;

  let timer = null;
  const dismiss = () => {
    if (!element.isConnected) return;
    element.classList.add("toast--out");
    window.setTimeout(() => element.remove(), 200);
    if (timer) window.clearTimeout(timer);
  };

  if (actionLabel) {
    const action = document.createElement("button");
    action.type = "button";
    action.className = "toast__action";
    action.textContent = actionLabel;
    action.addEventListener("click", () => {
      dismiss();
      onAction?.();
    });
    element.append(action);
  }

  host.append(element);
  // Больше трёх сообщений одновременно не показываем: старые уходят.
  while (host.children.length > 3) host.firstElementChild?.remove();
  timer = window.setTimeout(dismiss, duration);
  return { dismiss };
}

export function clearToasts() {
  const host = toastHost();
  if (host) host.replaceChildren();
}

/* ------------------------------------------------------------ модальные окна */

let modalEpoch = 0;
let backdropBound = false;

/** Номер «поколения» модальных окон: защищает от устаревших асинхронных открытий. */
export function modalEpochNow() {
  return modalEpoch;
}

/** Закрыть окно и сразу очистить содержимое, не дожидаясь события close. */
export function dismissDialog(dialog) {
  if (!dialog) return;
  if (dialog.open) dialog.close();
  if (!dialog.open) dialog.innerHTML = "";
}

export function closeModal() {
  dismissDialog(document.getElementById("modal"));
}

export function openModal({ title, subtitle = "", content = "", footer = "", size = "md", onClose = null } = {}) {
  const dialog = document.getElementById("modal");
  if (!dialog) throw new Error("Не найден контейнер модального окна");
  modalEpoch += 1;

  const width = { sm: "440px", md: "560px", lg: "760px" }[size] || "560px";
  dialog.style.width = `min(${width}, 100% - 32px)`;
  const markup = `
    <div class="modal__head">
      <div>
        <h2 id="modal-title">${esc(title)}</h2>
        ${subtitle ? `<p class="subtitle">${esc(subtitle)}</p>` : ""}
      </div>
      <button class="icon-button icon-button--plain" type="button" data-modal-close aria-label="Закрыть">
        ${icon("close")}
      </button>
    </div>
    <div class="modal__body">${content}</div>
    ${footer ? `<div class="modal__foot">${footer}</div>` : ""}
  `;

  // Если окно уже открыто, меняем содержимое на месте: вызов close() и
  // повторный showModal() приводили бы к гонке с событием close.
  dialog.innerHTML = markup;
  if (!dialog.open) {
    dialog.showModal();
  }

  dialog.querySelector("[data-modal-close]")?.addEventListener("click", () => dismissDialog(dialog));

  if (!backdropBound) {
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) dismissDialog(dialog);
    });
    dialog.addEventListener("close", () => {
      if (dialog.open) return;
      const handler = dialog._onClose;
      dialog._onClose = null;
      dialog.innerHTML = "";
      handler?.();
    });
    backdropBound = true;
  }
  dialog._onClose = onClose;

  const firstField = dialog.querySelector("input, select, textarea, button.btn--primary");
  firstField?.focus({ preventScroll: true });

  return {
    dialog,
    close: () => dismissDialog(dialog),
    $: (selector) => dialog.querySelector(selector),
    $$: (selector) => Array.from(dialog.querySelectorAll(selector)),
  };
}

export function confirmDialog({
  title,
  text,
  confirmLabel = "Подтвердить",
  cancelLabel = "Отмена",
  danger = false,
} = {}) {
  return new Promise((resolve) => {
    let settled = false;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      resolve(value);
      modal.close();
    };

    const modal = openModal({
      title,
      size: "sm",
      content: `<p class="small" style="color:var(--text-2)">${esc(text)}</p>`,
      footer: `
        <button class="btn btn--secondary" type="button" data-cancel>${esc(cancelLabel)}</button>
        <button class="btn ${danger ? "btn--danger" : "btn--primary"}" type="button" data-confirm>${esc(confirmLabel)}</button>
      `,
      onClose: () => finish(false),
    });

    modal.$("[data-cancel]")?.addEventListener("click", () => finish(false));
    modal.$("[data-confirm]")?.addEventListener("click", () => finish(true));
    window.setTimeout(() => modal.$("[data-confirm]")?.focus(), 30);
  });
}

/* ------------------------------------------------------------- состояния */

export function errorState(message, { retryLabel = "Повторить" } = {}) {
  return `
    <div class="empty">
      ${icon("info")}
      <strong>Не удалось загрузить данные</strong>
      <span>${esc(message)}</span>
      <button class="btn btn--secondary btn--sm" type="button" data-retry>${esc(retryLabel)}</button>
    </div>
  `;
}

export function loadingRows(count = 3) {
  return `<div class="loading">${Array.from(
    { length: count },
    () => '<div class="skeleton" style="height:64px"></div>'
  ).join("")}</div>`;
}

export function busy(button, isBusy, busyLabel = "Сохраняем…") {
  if (!button) return;
  if (isBusy) {
    button.dataset.label = button.textContent;
    button.textContent = busyLabel;
    button.disabled = true;
  } else {
    button.textContent = button.dataset.label || button.textContent;
    button.disabled = false;
  }
}
