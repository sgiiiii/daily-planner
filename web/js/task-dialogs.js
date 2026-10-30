/* Диалоги задачи: создание/редактирование и карточка задачи. */

import { api } from "./api.js";
import { icon } from "./icons.js";
import { busy, confirmDialog, modalEpochNow, openModal, toast } from "./ui.js";
import { esc, fmtDateFull, priorityLabel, SPHERES, todayIso } from "./util.js";
import { priorityBadge, sphereTag } from "./components.js";

const PRIORITY_OPTIONS = ["urgent", "high", "normal", "low"];

function fieldError(modal, name, message) {
  const holder = modal.$(`[data-error="${name}"]`);
  if (holder) holder.textContent = message || "";
}

function clearErrors(modal) {
  modal.$$("[data-error]").forEach((node) => {
    node.textContent = "";
  });
  modal.$$("[data-field]").forEach((node) => node.removeAttribute("aria-invalid"));
}

/**
 * Форма задачи. Возвращает промис, который разрешается сохранённой задачей
 * или null, если пользователь закрыл окно.
 */
export function openTaskForm(app, { task = null, defaults = {}, onSaved = null } = {}) {
  const isEdit = Boolean(task);
  const base = {
    title: task?.title ?? "",
    date: task?.date ?? defaults.date ?? todayIso(),
    time: task?.time ?? defaults.time ?? "",
    sphere: task?.sphere ?? defaults.sphere ?? "work",
    priority: task?.priority ?? defaults.priority ?? "normal",
    note: task?.note ?? "",
  };

  return new Promise((resolve) => {
    let saved = false;
    const modal = openModal({
      title: isEdit ? "Изменить задачу" : "Новая задача",
      subtitle: isEdit ? "Обновите название, срок или приоритет" : "Название обязательно, остальное — по желанию",
      size: "md",
      content: `
        <div class="form-grid">
          <div class="field field--wide">
            <label class="field__label" for="task-title">Что нужно сделать</label>
            <input class="input" id="task-title" data-field="title" type="text" maxlength="200"
              placeholder="Например: подготовить отчёт по проекту" value="${esc(base.title)}" autocomplete="off">
            <div class="field__error" data-error="title"></div>
          </div>

          <div class="field field--wide">
            <span class="field__label">Срок</span>
            <div class="chips" role="group" aria-label="Быстрый выбор срока">
              <button class="chip" type="button" data-quick="0">Сегодня</button>
              <button class="chip" type="button" data-quick="1">Завтра</button>
              <button class="chip" type="button" data-quick="7">Через неделю</button>
            </div>
            <input class="input" id="task-date" data-field="date" type="date" value="${esc(base.date)}"
              style="margin-top:8px" aria-label="Срок задачи">
            <div class="field__error" data-error="date"></div>
          </div>

          <div class="field">
            <label class="field__label" for="task-time">Время <span class="muted">(необязательно)</span></label>
            <input class="input" id="task-time" data-field="time" type="time" value="${esc(base.time)}">
            <div class="field__error" data-error="time"></div>
          </div>

          <div class="field">
            <label class="field__label" for="task-priority">Приоритет</label>
            <select class="select" id="task-priority" data-field="priority">
              ${PRIORITY_OPTIONS.map(
                (value) => `<option value="${value}"${value === base.priority ? " selected" : ""}>${priorityLabel(value)}</option>`
              ).join("")}
            </select>
          </div>

          <div class="field field--wide">
            <span class="field__label">Сфера</span>
            <div class="chips" role="group" aria-label="Сфера задачи">
              ${Object.entries(SPHERES)
                .map(
                  ([value, info]) => `<button class="chip" type="button" data-sphere="${value}"
                    aria-pressed="${value === base.sphere}">${esc(info.label)}</button>`
                )
                .join("")}
            </div>
          </div>

          <div class="field field--wide">
            <label class="field__label" for="task-note">Заметка <span class="muted">(необязательно)</span></label>
            <textarea class="textarea" id="task-note" data-field="note" maxlength="1000"
              placeholder="Детали, ссылки, номер заявки">${esc(base.note)}</textarea>
          </div>
        </div>
      `,
      footer: `
        <button class="btn btn--secondary" type="button" data-cancel>Отмена</button>
        <button class="btn btn--primary" type="button" data-save>${isEdit ? "Сохранить" : "Добавить задачу"}</button>
      `,
      onClose: () => {
        if (!saved) resolve(null);
      },
    });

    let sphere = base.sphere;
    const dateInput = modal.$("#task-date");
    const titleInput = modal.$("#task-title");

    modal.$$("[data-quick]").forEach((chip) => {
      chip.addEventListener("click", () => {
        const target = new Date();
        target.setDate(target.getDate() + Number(chip.dataset.quick));
        dateInput.value = `${target.getFullYear()}-${String(target.getMonth() + 1).padStart(2, "0")}-${String(target.getDate()).padStart(2, "0")}`;
        dateInput.dispatchEvent(new Event("change"));
      });
    });

    dateInput.addEventListener("change", () => {
      modal.$$("[data-quick]").forEach((chip) => chip.setAttribute("aria-pressed", "false"));
    });

    modal.$$("[data-sphere]").forEach((chip) => {
      chip.addEventListener("click", () => {
        sphere = chip.dataset.sphere;
        modal.$$("[data-sphere]").forEach((node) =>
          node.setAttribute("aria-pressed", String(node.dataset.sphere === sphere))
        );
      });
    });

    const save = async () => {
      clearErrors(modal);
      const button = modal.$("[data-save]");
      const payload = {
        title: titleInput.value.trim(),
        date: dateInput.value,
        time: modal.$("#task-time").value || null,
        sphere,
        priority: modal.$("#task-priority").value,
        note: modal.$("#task-note").value.trim(),
      };

      if (!payload.title) {
        fieldError(modal, "title", "Введите название задачи");
        titleInput.setAttribute("aria-invalid", "true");
        titleInput.focus();
        return;
      }
      if (!payload.date) {
        fieldError(modal, "date", "Выберите дату");
        return;
      }
      if (!isEdit && payload.date < todayIso()) {
        fieldError(modal, "date", "Срок не может быть раньше сегодняшнего дня");
        return;
      }
      if (payload.note.length > 1000) {
        fieldError(modal, "note", "Заметка длиннее 1000 символов");
        return;
      }

      busy(button, true, isEdit ? "Сохраняем…" : "Добавляем…");
      try {
        const response = isEdit
          ? await api.tasks.update(task.id, payload)
          : await api.tasks.create(payload);
        saved = true;
        modal.close();
        toast(isEdit ? "Задача обновлена" : "Задача добавлена");
        onSaved?.(response.task);
        resolve(response.task);
      } catch (error) {
        busy(button, false);
        if (error.fields) {
          Object.entries(error.fields).forEach(([name, code]) => {
            const text =
              name === "title"
                ? "Проверьте название"
                : name === "date"
                ? "Проверьте дату"
                : name === "time"
                ? "Время в формате ЧЧ:ММ"
                : "Проверьте значение";
            fieldError(modal, name, text);
          });
        }
        toast(error.message, { duration: 5000 });
      }
    };

    modal.$("[data-save]")?.addEventListener("click", save);
    modal.$("[data-cancel]")?.addEventListener("click", () => modal.close());
    titleInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        save();
      }
    });
    window.setTimeout(() => titleInput.focus(), 40);
  });
}

/**
 * Карточка задачи с действиями «Выполнено», «Изменить», «Удалить».
 */
export async function openTaskDetail(app, taskId, onChanged) {
  const epoch = modalEpochNow();
  let task;
  try {
    task = (await api.tasks.get(taskId)).task;
  } catch (error) {
    toast(error.message, { duration: 5000 });
    return;
  }
  // Пока шёл запрос, пользователь мог открыть другое окно — не перезаписываем его.
  if (epoch !== modalEpochNow()) return;

  const modal = openModal({
    title: "Задача",
    size: "sm",
    content: `
      <div class="detail">
        <div class="detail__title">${esc(task.title)}</div>
        <div class="detail__row">
          ${sphereTag(task.sphere)}
          ${task.time ? `<span class="small muted">${icon("clock")} ${esc(task.time)}</span>` : ""}
          ${priorityBadge(task.priority)}
          ${task.done ? '<span class="badge badge--soft">выполнена</span>' : ""}
          ${task.carried ? `<span class="badge badge--carried">перенесена ${task.carried} ${task.carried === 1 ? "раз" : "раза"}</span>` : ""}
        </div>
        <p class="small muted">Срок: ${esc(fmtDateFull(task.date))}</p>
        ${task.note ? `<div class="detail__note">${esc(task.note)}</div>` : ""}
      </div>
    `,
    footer: `
      <div style="display:flex;gap:8px;flex-wrap:wrap;width:100%;justify-content:space-between">
        <button class="btn btn--danger btn--sm" type="button" data-delete>${icon("trash")}Удалить</button>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <button class="btn btn--secondary" type="button" data-edit>${icon("edit")}Изменить</button>
          <button class="btn btn--primary" type="button" data-toggle>
            ${icon(task.done ? "undo" : "check")}${task.done ? "Вернуть в работу" : "Выполнено"}
          </button>
        </div>
      </div>
    `,
  });

  modal.$("[data-edit]")?.addEventListener("click", async () => {
    modal.close();
    await openTaskForm(app, { task, onSaved: () => onChanged?.() });
  });

  modal.$("[data-toggle]")?.addEventListener("click", async () => {
    const next = !task.done;
    modal.close();
    try {
      await api.tasks.toggle(task.id, next);
      toast(next ? "Задача выполнена" : "Задача возвращена в работу", {
        actionLabel: "Отменить",
        onAction: async () => {
          await api.tasks.toggle(task.id, !next).catch(() => {});
          onChanged?.();
        },
      });
      onChanged?.();
    } catch (error) {
      toast(error.message, { duration: 5000 });
    }
  });

  modal.$("[data-delete]")?.addEventListener("click", async () => {
    modal.close();
    const confirmed = await confirmDialog({
      title: "Удалить задачу?",
      text: `«${task.title}» исчезнет из списка. Действие можно отменить сразу после удаления.`,
      confirmLabel: "Удалить",
      danger: true,
    });
    if (!confirmed) return;
    modal.close();
    try {
      await api.tasks.remove(task.id);
      toast("Задача удалена", {
        actionLabel: "Вернуть",
        onAction: async () => {
          await api.tasks.restore(task.id).catch(() => {});
          onChanged?.();
        },
        duration: 8000,
      });
      onChanged?.();
    } catch (error) {
      toast(error.message, { duration: 5000 });
    }
  });
}
