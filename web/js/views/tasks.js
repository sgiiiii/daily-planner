/* Экран «Задачи»: список на день, фильтры по сферам, просроченные. */

import { api } from "../api.js";
import { icon } from "../icons.js";
import { bindTaskList, emptyState, taskRow } from "../components.js";
import { errorState, loadingRows, toast } from "../ui.js";
import {
  addDaysIso,
  esc,
  fmtDateFull,
  plural,
  relativeDay,
  todayIso,
  tasksWord,
} from "../util.js";

const FILTERS = [
  { value: "all", label: "Все" },
  { value: "work", label: "Работа" },
  { value: "study", label: "Учёба" },
  { value: "personal", label: "Личное" },
  { value: "overdue", label: "Просроченные" },
];

export default {
  name: "tasks",

  async mount(root, app) {
    const params = new URLSearchParams(window.location.search);
    const state = {
      date: params.get("date") || todayIso(),
      filter: params.get("filter") || "all",
    };

    const applyFilter = (tasks) => {
      if (state.filter === "all" || state.filter === "overdue") return tasks;
      return tasks.filter((task) => task.sphere === state.filter);
    };

    const draw = async () => {
      root.innerHTML = `<div class="loading">${loadingRows(4)}</div>`;

      let tasks;
      let stats = { total: 0, done: 0, open: 0, percent: 0 };
      try {
        if (state.filter === "overdue") {
          tasks = (await api.tasks.list({ status: "overdue" })).tasks;
          stats = {
            total: tasks.length,
            done: 0,
            open: tasks.length,
            percent: 0,
          };
        } else {
          const data = await api.day(state.date);
          tasks = data.tasks;
          stats = data.stats;
        }
      } catch (error) {
        root.innerHTML = errorState(error.message);
        root.querySelector("[data-retry]")?.addEventListener("click", draw);
        return;
      }

      const visible = applyFilter(tasks);
      const openTasks = visible.filter((task) => !task.done);
      const doneTasks = visible.filter((task) => task.done);
      const counts = {
        all: tasks.length,
        work: tasks.filter((task) => task.sphere === "work").length,
        study: tasks.filter((task) => task.sphere === "study").length,
        personal: tasks.filter((task) => task.sphere === "personal").length,
        overdue: tasks.filter((task) => task.overdue).length,
      };

      const isOverdueMode = state.filter === "overdue";
      const heading = isOverdueMode ? "Просроченные задачи" : relativeDay(state.date);
      const subheading = isOverdueMode
        ? `${openTasks.length} ${tasksWord(openTasks.length)} ждут внимания`
        : `${fmtDateFull(state.date)} · ${stats.open} в работе, ${stats.done} ${plural(stats.done, [
            "выполнена",
            "выполнены",
            "выполнено",
          ])}`;

      root.innerHTML = `
        <div class="page-head">
          <div class="page-head__title">
            <p class="eyebrow">Задачи</p>
            <h1>${esc(heading)}</h1>
            <p class="subtitle">${esc(subheading)}</p>
          </div>
          <div class="page-head__actions">
            <button class="btn btn--primary" type="button" data-act="add">${icon("plus")}Новая задача</button>
          </div>
        </div>

        <div class="tasks-toolbar">
          ${
            isOverdueMode
              ? `<button class="btn btn--secondary btn--sm" type="button" data-act="back-to-day">${icon("chevron-left")}К задачам на сегодня</button>`
              : `<div class="date-nav" role="group" aria-label="Дата списка">
                   <button class="date-nav__btn" type="button" data-step="-1" aria-label="Предыдущий день">${icon(
                     "chevron-left",
                     "ic--sm"
                   )}</button>
                   <button class="date-nav__btn" type="button" data-today aria-pressed="${
                     state.date === todayIso()
                   }">Сегодня</button>
                   <input type="date" value="${esc(state.date)}" data-date-input aria-label="Выбранная дата">
                   <button class="date-nav__btn" type="button" data-step="1" aria-label="Следующий день">${icon(
                     "chevron-right",
                     "ic--sm"
                   )}</button>
                 </div>`
          }
          <div class="chips" role="group" aria-label="Фильтр по сфере">
            ${FILTERS.map(
              (filter) => `
              <button class="chip" type="button" data-filter="${filter.value}"
                aria-pressed="${state.filter === filter.value}">
                ${filter.label}
                <span class="count">${counts[filter.value] || 0}</span>
              </button>`
            ).join("")}
          </div>
        </div>

        ${
          openTasks.length
            ? `<section class="tasks-section">
                 <div class="tasks-section__head">
                   <h2>${isOverdueMode ? "Требуют решения" : "В работе"}</h2>
                   <span class="tasks-section__count">${openTasks.length}</span>
                 </div>
                 <ul class="task-list">${openTasks.map((task) => taskRow(task, { showDate: isOverdueMode })).join("")}</ul>
               </section>`
            : `<section class="tasks-section">
                 ${emptyState({
                   iconName: "inbox",
                   title: isOverdueMode ? "Просроченных задач нет" : "На этот день задач нет",
                   text: isOverdueMode
                     ? "Все дела идут в срок — так держать."
                     : "Добавьте задачу или перенесите её из другого дня.",
                   action: `<button class="btn btn--secondary btn--sm" type="button" data-act="add">Добавить задачу</button>`,
                 })}
               </section>`
        }

        ${
          doneTasks.length
            ? `<section class="tasks-section tasks-section--done">
                 <div class="tasks-section__head">
                   <h2>Выполнено</h2>
                   <span class="tasks-section__count">${doneTasks.length}</span>
                 </div>
                 <ul class="task-list">${doneTasks.map((task) => taskRow(task, { showDate: isOverdueMode })).join("")}</ul>
               </section>`
            : ""
        }
      `;

      bindTaskList(root, app, draw);

      root.querySelectorAll("[data-act='add']").forEach((button) =>
        button.addEventListener("click", () =>
          app.openTaskForm({ date: isOverdueMode ? todayIso() : state.date }, draw)
        )
      );

      root.querySelectorAll("[data-filter]").forEach((chip) =>
        chip.addEventListener("click", () => {
          state.filter = chip.dataset.filter;
          const url = new URL(window.location.href);
          if (state.filter === "all") url.searchParams.delete("filter");
          else url.searchParams.set("filter", state.filter);
          history.replaceState(null, "", url.pathname + url.search);
          draw();
        })
      );

      root.querySelectorAll("[data-step]").forEach((button) =>
        button.addEventListener("click", () => {
          state.date = addDaysIso(state.date, Number(button.dataset.step));
          state.filter = state.filter === "overdue" ? "all" : state.filter;
          const url = new URL(window.location.href);
          url.searchParams.set("date", state.date);
          url.searchParams.delete("filter");
          history.replaceState(null, "", url.pathname + url.search);
          draw();
        })
      );

      root.querySelector("[data-today]")?.addEventListener("click", () => {
        state.date = todayIso();
        state.filter = "all";
        history.replaceState(null, "", "/tasks");
        draw();
      });

      root.querySelector("[data-date-input]")?.addEventListener("change", (event) => {
        if (!event.target.value) return;
        state.date = event.target.value;
        state.filter = "all";
        const url = new URL(window.location.href);
        url.searchParams.set("date", state.date);
        url.searchParams.delete("filter");
        history.replaceState(null, "", url.pathname + url.search);
        draw();
      });

      root.querySelector("[data-act='back-to-day']")?.addEventListener("click", () => {
        state.filter = "all";
        state.date = todayIso();
        history.replaceState(null, "", "/tasks");
        draw();
      });
    };

    app.state.tasksRefresh = draw;
    await draw();
  },
};
