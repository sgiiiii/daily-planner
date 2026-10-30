/* Переиспользуемые куски разметки: строки задач, бейджи, пустые состояния. */

import { icon } from "./icons.js";
import { api } from "./api.js";
import { toast } from "./ui.js";
import { esc, fmtDate, priorityLabel, relativeDay, SPHERES, tasksWord } from "./util.js";

export function priorityBadge(priority) {
  if (priority !== "urgent" && priority !== "high") return "";
  const tone = priority === "urgent" ? "urgent" : "high";
  return `<span class="badge badge--${tone}">${esc(priorityLabel(priority))}</span>`;
}

export function sphereTag(sphere) {
  const info = SPHERES[sphere];
  if (!info) return "";
  return `<span class="sphere sphere--${info.className}">${esc(info.label)}</span>`;
}

export function checkButton(task) {
  return `
    <button class="check" type="button" role="checkbox" aria-checked="${task.done ? "true" : "false"}"
      data-act="toggle" aria-label="${task.done ? "Вернуть в работу" : "Отметить выполненной"}: ${esc(task.title)}">
      <span class="check__box">${icon("check")}</span>
    </button>
  `;
}

export function taskMeta(task) {
  const bits = [sphereTag(task.sphere)];
  if (task.time) bits.push(`<span>${icon("clock")}${esc(task.time)}</span>`);
  if (task.carried > 0) {
    const from = task.carriedFrom ? `с ${fmtDate(task.carriedFrom)}` : "";
    bits.push(`<span class="badge badge--carried">перенесена ${esc(from)}</span>`);
  }
  if (task.overdue) {
    bits.push(`<span class="badge badge--urgent">просрочена</span>`);
  }
  if (task.note) bits.push(`<span>${icon("edit")}заметка</span>`);
  return bits.filter(Boolean).join("");
}

/**
 * Строка задачи. Название — настоящая кнопка, поэтому карточку можно открыть
 * и мышью, и с клавиатуры, а рядом остаётся отдельный чекбокс.
 */
export function taskRow(task, { showPriority = true, showDate = false } = {}) {
  const classes = ["task"];
  if (task.done) classes.push("task--done");
  if (task.overdue) classes.push("task--overdue");
  const dateBit = showDate ? `<span>${esc(relativeDay(task.date))}</span>` : "";
  return `
    <li class="${classes.join(" ")}" data-task-id="${task.id}" data-priority="${esc(task.priority)}">
      ${checkButton(task)}
      <div class="task__body">
        <button class="task__title" type="button" data-act="open"
          aria-label="Открыть задачу: ${esc(task.title)}">${esc(task.title)}</button>
        <div class="task__meta">${dateBit}${taskMeta(task)}</div>
      </div>
      <div class="task__right">${showPriority ? priorityBadge(task.priority) : ""}</div>
    </li>
  `;
}

export function emptyState({ iconName = "inbox", title, text = "", action = "" } = {}) {
  return `
    <div class="empty">
      ${icon(iconName)}
      <strong>${esc(title)}</strong>
      ${text ? `<span>${esc(text)}</span>` : ""}
      ${action}
    </div>
  `;
}

export function sectionHead(title, count, extra = "") {
  return `
    <div class="tasks-section__head">
      <h2>${esc(title)} ${count !== null ? `<span class="tasks-section__count">${count}</span>` : ""}</h2>
      ${extra}
    </div>
  `;
}

export function countLabel(taskList) {
  return `${taskList.length} ${tasksWord(taskList.length)}`;
}

/**
 * Делегирование кликов по списку задач внутри root.
 * onChanged вызывается после изменения, чтобы перерисовать представление.
 */
export function bindTaskList(root, app, onChanged) {
  if (root.dataset.bound === "tasks") return;
  root.dataset.bound = "tasks";

  const handleToggle = async (button) => {
    const row = button.closest("[data-task-id]");
    if (!row) return;
    const taskId = Number(row.dataset.taskId);
    const wasDone = button.getAttribute("aria-checked") === "true";
    button.setAttribute("aria-checked", wasDone ? "false" : "true");
    try {
      await api.tasks.toggle(taskId, !wasDone);
      toast(wasDone ? "Задача возвращена в работу" : "Задача выполнена", {
        actionLabel: "Отменить",
        onAction: async () => {
          await api.tasks.toggle(taskId, wasDone).catch(() => {});
          onChanged();
        },
      });
      onChanged();
    } catch (error) {
      button.setAttribute("aria-checked", wasDone ? "true" : "false");
      toast(error.message, { duration: 5000 });
    }
  };

  root.addEventListener("click", (event) => {
    const toggle = event.target.closest('[data-act="toggle"]');
    if (toggle && root.contains(toggle)) {
      event.preventDefault();
      event.stopPropagation();
      handleToggle(toggle);
      return;
    }
    const open = event.target.closest('[data-act="open"]');
    if (open && root.contains(open)) {
      const row = open.closest("[data-task-id]");
      if (row) app.openTaskDetail(Number(row.dataset.taskId), onChanged);
      return;
    }
    if (event.target.closest("button, a, input, select, textarea")) return;
    const row = event.target.closest("[data-task-id]");
    if (row && root.contains(row)) {
      app.openTaskDetail(Number(row.dataset.taskId), onChanged);
    }
  });
}
