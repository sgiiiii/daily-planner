/* Диалог события календаря (встречи, учёбы, личных дел со временем). */

import { api } from "./api.js";
import { busy, openModal, toast } from "./ui.js";
import { esc, todayIso } from "./util.js";

const KINDS = [
  { value: "meeting", label: "Встреча" },
  { value: "study", label: "Учёба" },
  { value: "personal", label: "Личное" },
];

export function openEventForm(app, { event = null, defaults = {}, onSaved = null } = {}) {
  const isEdit = Boolean(event);
  const base = {
    title: event?.title ?? "",
    date: event?.date ?? defaults.date ?? todayIso(),
    start: event?.start ?? defaults.start ?? "10:00",
    end: event?.end ?? "",
    kind: event?.kind ?? "meeting",
  };

  return new Promise((resolve) => {
    let saved = false;
    const modal = openModal({
      title: isEdit ? "Изменить событие" : "Новое событие",
      subtitle: "Встречи и дела со временем появятся в календаре",
      size: "md",
      content: `
        <div class="form-grid">
          <div class="field field--wide">
            <label class="field__label" for="event-title">Название</label>
            <input class="input" id="event-title" type="text" maxlength="200"
              placeholder="Например: созвон с командой" value="${esc(base.title)}">
            <div class="field__error" data-error="title"></div>
          </div>
          <div class="field field--wide">
            <label class="field__label" for="event-date">Дата</label>
            <input class="input" id="event-date" type="date" value="${esc(base.date)}">
            <div class="field__error" data-error="date"></div>
          </div>
          <div class="field">
            <label class="field__label" for="event-start">Начало</label>
            <input class="input" id="event-start" type="time" value="${esc(base.start)}">
            <div class="field__error" data-error="start"></div>
          </div>
          <div class="field">
            <label class="field__label" for="event-end">Окончание <span class="muted">(необязательно)</span></label>
            <input class="input" id="event-end" type="time" value="${esc(base.end)}">
            <div class="field__error" data-error="end"></div>
          </div>
          <div class="field field--wide">
            <label class="field__label" for="event-kind">Тип</label>
            <select class="select" id="event-kind">
              ${KINDS.map(
                (kind) => `<option value="${kind.value}"${kind.value === base.kind ? " selected" : ""}>${kind.label}</option>`
              ).join("")}
            </select>
          </div>
        </div>
      `,
      footer: `
        <button class="btn btn--secondary" type="button" data-cancel>Отмена</button>
        <button class="btn btn--primary" type="button" data-save>${isEdit ? "Сохранить" : "Добавить событие"}</button>
      `,
      onClose: () => {
        if (!saved) resolve(null);
      },
    });

    const error = (name, message) => {
      const holder = modal.$(`[data-error="${name}"]`);
      if (holder) holder.textContent = message || "";
    };

    const save = async () => {
      modal.$$("[data-error]").forEach((node) => (node.textContent = ""));
      const payload = {
        title: modal.$("#event-title").value.trim(),
        date: modal.$("#event-date").value,
        start: modal.$("#event-start").value,
        end: modal.$("#event-end").value || null,
        kind: modal.$("#event-kind").value,
      };
      if (!payload.title) return error("title", "Введите название");
      if (!payload.date) return error("date", "Выберите дату");
      if (!payload.start) return error("start", "Укажите время начала");
      if (payload.end && payload.end <= payload.start) return error("end", "Окончание должно быть позже начала");

      const button = modal.$("[data-save]");
      busy(button, true, "Сохраняем…");
      try {
        const response = isEdit
          ? await api.events.update(event.id, payload)
          : await api.events.create(payload);
        saved = true;
        modal.close();
        toast(isEdit ? "Событие обновлено" : "Событие добавлено");
        onSaved?.(response.event);
        resolve(response.event);
      } catch (exception) {
        busy(button, false);
        toast(exception.message, { duration: 5000 });
      }
    };

    modal.$("[data-save]")?.addEventListener("click", save);
    modal.$("[data-cancel]")?.addEventListener("click", () => modal.close());
    modal.$("#event-title")?.addEventListener("keydown", (event_) => {
      if (event_.key === "Enter") {
        event_.preventDefault();
        save();
      }
    });
    window.setTimeout(() => modal.$("#event-title")?.focus(), 40);
  });
}
