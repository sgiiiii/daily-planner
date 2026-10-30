/* Экран «Календарь»: день, неделя, месяц. Задачи и встречи в одних данных. */

import { api } from "../api.js";
import { icon } from "../icons.js";
import { emptyState } from "../components.js";
import { errorState, loadingRows, openModal } from "../ui.js";
import { openEventForm } from "../event-dialog.js";
import {
  addDaysIso,
  esc,
  fmtDateFull,
  isToday,
  isWeekend,
  monthLabel,
  parseIso,
  relativeDay,
  startOfWeekIso,
  todayIso,
  weekdayShortUpper,
} from "../util.js";

const KIND_LABEL = { meeting: "Встреча", study: "Учёба", personal: "Личное" };
const DETAIL_LIMIT = 3;

function rangeFor(mode, anchor) {
  if (mode === "day") return { from: anchor, to: anchor };
  if (mode === "week") {
    const from = startOfWeekIso(anchor);
    return { from, to: addDaysIso(from, 6) };
  }
  const first = parseIso(anchor);
  first.setDate(1);
  const from = startOfWeekIso(`${first.getFullYear()}-${String(first.getMonth() + 1).padStart(2, "0")}-01`);
  return { from, to: addDaysIso(from, 41) };
}

function groupByDate(data) {
  const map = new Map();
  const ensure = (date) => {
    if (!map.has(date)) map.set(date, { events: [], tasks: [] });
    return map.get(date);
  };
  data.events.forEach((event) => ensure(event.date).events.push(event));
  data.tasks.forEach((task) => ensure(task.date).tasks.push(task));
  return map;
}

function sortItems(bucket) {
  const time = (item) => item.start || item.time || "99:99";
  const events = [...bucket.events].sort((a, b) => time(a).localeCompare(time(b)));
  const tasks = [...bucket.tasks].sort((a, b) => time(a).localeCompare(time(b)));
  return [...events, ...tasks];
}

function eventPill(event) {
  return `
    <button class="calendar-pill calendar-pill--${esc(event.kind)}" type="button"
      data-event-id="${event.id}" title="${esc(event.title)}">
      <b>${esc(event.start)}${event.end ? "–" + esc(event.end) : ""}</b>
      <span class="pill-title">${esc(event.title)}</span>
    </button>
  `;
}

function taskPill(task) {
  return `
    <button class="calendar-pill calendar-pill--task ${task.done ? "calendar-pill--done" : ""}" type="button"
      data-task-id="${task.id}" title="${esc(task.title)}">
      ${task.time ? `<b>${esc(task.time)}</b>` : ""}
      <span class="pill-title">${esc(task.title)}</span>
    </button>
  `;
}

function agendaRow(item, kind) {
  if (kind === "event") {
    return `
      <button class="agenda-row" type="button" data-event-id="${item.id}">
        <span class="agenda-row__time">${esc(item.start)}${item.end ? "<br>" + esc(item.end) : ""}</span>
        <span>
          <span class="agenda-row__title">${esc(item.title)}</span>
          <span class="agenda-row__meta">
            <span class="badge badge--soft">${KIND_LABEL[item.kind] || "Событие"}</span>
          </span>
        </span>
      </button>`;
  }
  return `
    <button class="agenda-row agenda-row--task" type="button" data-task-id="${item.id}">
      <span class="agenda-row__time">${item.time ? esc(item.time) : "—"}</span>
      <span>
        <span class="agenda-row__title">${esc(item.title)}</span>
        <span class="agenda-row__meta">
          <span class="sphere sphere--${esc(item.sphere)}"></span>
          ${item.done ? '<span class="badge badge--neutral">выполнена</span>' : ""}
          ${item.overdue ? '<span class="badge badge--urgent">просрочена</span>' : ""}
        </span>
      </span>
    </button>`;
}

export default {
  name: "calendar",

  async mount(root, app) {
    const state = {
      mode: window.matchMedia("(max-width: 720px)").matches ? "day" : "week",
      anchor: todayIso(),
    };

    const draw = async () => {
      root.innerHTML = `<div class="loading">${loadingRows(3)}</div>`;

      const range = rangeFor(state.mode, state.anchor);
      let data;
      try {
        data = await api.calendar(range.from, range.to);
      } catch (error) {
        root.innerHTML = errorState(error.message);
        root.querySelector("[data-retry]")?.addEventListener("click", draw);
        return;
      }

      const grouped = groupByDate(data);
      const bucket = (date) => grouped.get(date) || { events: [], tasks: [] };

      const label =
        state.mode === "day"
          ? fmtDateFull(state.anchor)
          : state.mode === "week"
          ? `${relativeDay(range.from)} — ${relativeDay(range.to)}`
          : monthLabel(state.anchor);

      const segmented = ["day", "week", "month"]
        .map(
          (mode) =>
            `<button class="segmented__item" type="button" data-mode="${mode}"
               aria-pressed="${state.mode === mode}">${
              { day: "День", week: "Неделя", month: "Месяц" }[mode]
            }</button>`
        )
        .join("");

      let body = "";
      if (state.mode === "week") {
        const days = Array.from({ length: 7 }, (_, index) => addDaysIso(range.from, index));
        body = `<div class="calendar-week">${days
          .map((date) => {
            const items = sortItems(bucket(date));
            const visible = items.slice(0, DETAIL_LIMIT);
            const hidden = items.length - visible.length;
            return `
              <section class="calendar-day ${isToday(date) ? "calendar-day--today" : ""} ${
              isWeekend(date) ? "calendar-day--weekend" : ""
            }">
                <header class="calendar-day__head">
                  <span class="calendar-day__dow">${weekdayShortUpper(date)}</span>
                  <button type="button" class="calendar-day__num" data-open-day="${date}"
                    aria-label="Открыть день ${esc(date)}">${parseIso(date).getDate()}</button>
                </header>
                <div class="calendar-day__items">
                  ${visible
                    .map((item) => (item.start !== undefined ? eventPill(item) : taskPill(item)))
                    .join("")}
                  ${
                    !items.length
                      ? `<button class="calendar-pill calendar-pill--task" type="button" data-open-day="${date}"
                           style="border-left-color:var(--border);background:transparent;color:var(--muted)">
                           <span class="pill-title">Свободно · добавить</span>
                         </button>`
                      : ""
                  }
                </div>
                ${hidden > 0 ? `<button class="calendar-day__more" type="button" data-open-day="${date}">Ещё ${hidden}</button>` : ""}
              </section>`;
          })
          .join("")}</div>`;
      } else if (state.mode === "month") {
        const cells = Array.from({ length: 42 }, (_, index) => addDaysIso(range.from, index));
        const month = parseIso(state.anchor).getMonth();
        body = `
          <div class="calendar-month">
            ${["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
              .map((dow) => `<div class="calendar-month__dow">${dow}</div>`)
              .join("")}
            ${cells
              .map((date) => {
                const items = sortItems(bucket(date));
                const other = parseIso(date).getMonth() !== month;
                return `
                  <button class="calendar-month__cell ${isToday(date) ? "calendar-month__cell--today" : ""} ${
                  other ? "calendar-month__cell--other" : ""
                }" type="button" data-open-day="${date}" aria-label="${esc(fmtDateFull(date))}: ${items.length}">
                    <span class="calendar-month__num">${parseIso(date).getDate()}</span>
                    ${
                      items.length
                        ? `<span class="calendar-month__count">${items.length} ${items.length === 1 ? "дело" : "дел"}</span>
                           <span class="calendar-month__dots">${items
                             .slice(0, 4)
                             .map(
                               (item) =>
                                 `<span class="calendar-month__dot ${
                                   item.start !== undefined
                                     ? item.kind === "study"
                                       ? "calendar-month__dot--study"
                                       : item.kind === "personal"
                                       ? "calendar-month__dot--personal"
                                       : ""
                                     : "calendar-month__dot--task"
                                 }"></span>`
                             )
                             .join("")}</span>`
                        : ""
                    }
                  </button>`;
              })
              .join("")}
          </div>`;
      } else {
        const items = sortItems(bucket(state.anchor));
        body = items.length
          ? `<div class="calendar-day-view">${items
              .map((item) => agendaRow(item, item.start !== undefined ? "event" : "task"))
              .join("")}</div>`
          : emptyState({
              iconName: "calendar",
              title: "На этот день ничего не запланировано",
              text: "Добавьте событие со временем или задачу — они появятся здесь.",
              action: `<div style="display:flex;gap:8px;flex-wrap:wrap;justify-content:center">
                         <button class="btn btn--secondary btn--sm" type="button" data-act="add-task">Задача</button>
                         <button class="btn btn--primary btn--sm" type="button" data-act="add-event">Событие</button>
                       </div>`,
            });
      }

      root.innerHTML = `
        <div class="page-head">
          <div class="page-head__title">
            <p class="eyebrow">Календарь</p>
            <h1>${esc(label)}</h1>
            <p class="subtitle">Задачи со временем и встречи — в одной сетке</p>
          </div>
          <div class="page-head__actions">
            <button class="btn btn--secondary" type="button" data-act="add-event">${icon("plus")}Событие</button>
            <button class="btn btn--primary btn--desktop" type="button" data-act="add-task">${icon("plus")}Задача</button>
          </div>
        </div>

        <div class="tasks-toolbar">
          <div class="date-nav">
            <button class="date-nav__btn" type="button" data-nav="-1" aria-label="Предыдущий период">${icon(
              "chevron-left",
              "ic--sm"
            )}</button>
            <button class="date-nav__btn" type="button" data-nav="today">Сегодня</button>
            <button class="date-nav__btn" type="button" data-nav="1" aria-label="Следующий период">${icon(
              "chevron-right",
              "ic--sm"
            )}</button>
          </div>
          <div class="segmented" role="group" aria-label="Вид календаря">${segmented}</div>
        </div>

        ${body}
      `;

      const step = { day: 1, week: 7, month: 0 };
      root.querySelectorAll("[data-nav]").forEach((button) =>
        button.addEventListener("click", () => {
          const action = button.dataset.nav;
          if (action === "today") {
            state.anchor = todayIso();
          } else if (state.mode === "month") {
            const date = parseIso(state.anchor);
            date.setDate(1);
            date.setMonth(date.getMonth() + Number(action));
            state.anchor = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-01`;
          } else {
            state.anchor = addDaysIso(state.anchor, Number(action) * step[state.mode]);
          }
          draw();
        })
      );

      root.querySelectorAll("[data-mode]").forEach((button) =>
        button.addEventListener("click", () => {
          state.mode = button.dataset.mode;
          draw();
        })
      );

      root.querySelectorAll("[data-act='add-event']").forEach((button) =>
        button.addEventListener("click", () =>
          app.openEventForm({ date: state.anchor }, draw)
        )
      );
      root.querySelectorAll("[data-act='add-task']").forEach((button) =>
        button.addEventListener("click", () =>
          app.openTaskForm({ date: state.anchor }, draw)
        )
      );

      root.querySelectorAll("[data-open-day]").forEach((button) =>
        button.addEventListener("click", () => {
          openDayDialog(app, button.dataset.openDay, draw);
        })
      );

      root.querySelectorAll("[data-task-id]").forEach((button) =>
        button.addEventListener("click", () =>
          app.openTaskDetail(Number(button.dataset.taskId), draw)
        )
      );

      root.querySelectorAll("[data-event-id]").forEach((button) =>
        button.addEventListener("click", () => {
          const event = data.events.find((item) => String(item.id) === button.dataset.eventId);
          if (event) app.openEventForm({ event }, draw);
        })
      );
    };

    await draw();
  },
};

/* ------------------------------------------------------------------ день */

function openDayDialog(app, date, onChanged) {
  let items = { events: [], tasks: [] };

  const render = () => {
    const sorted = sortItems(items);
    return sorted.length
      ? `<div class="calendar-day-view">${sorted
          .map((item) => agendaRow(item, item.start !== undefined ? "event" : "task"))
          .join("")}</div>`
      : `<p class="small muted">На этот день пока ничего не запланировано.</p>`;
  };

  const modal = openModal({
    title: fmtDateFull(date),
    subtitle: relativeDay(date),
    size: "md",
    content: `<div data-day-content>${render()}</div>`,
    footer: `
      <button class="btn btn--secondary" type="button" data-add-task>${icon("plus")}Задача</button>
      <button class="btn btn--primary" type="button" data-add-event>${icon("plus")}Событие</button>
    `,
  });

  const content = modal.$("[data-day-content]");
  const bindItems = () => {
    content.querySelectorAll("[data-task-id]").forEach((button) =>
      button.addEventListener("click", () => {
        modal.close();
        app.openTaskDetail(Number(button.dataset.taskId), () => {
          onChanged();
          openDayDialog(app, date, onChanged);
        });
      })
    );
    content.querySelectorAll("[data-event-id]").forEach((button) =>
      button.addEventListener("click", () => {
        const event = items.events.find((item) => String(item.id) === button.dataset.eventId);
        modal.close();
        if (event) app.openEventForm({ event }, () => {
          onChanged();
          openDayDialog(app, date, onChanged);
        });
      })
    );
  };

  const load = async () => {
    try {
      const data = await api.calendar(date, date);
      items = { events: data.events, tasks: data.tasks };
      content.innerHTML = render();
      bindItems();
    } catch (error) {
      content.innerHTML = `<p class="small" style="color:var(--error)">${esc(error.message)}</p>`;
    }
  };

  modal.$("[data-add-task]")?.addEventListener("click", () => {
    modal.close();
    app.openTaskForm({ date }, () => {
      onChanged();
      openDayDialog(app, date, onChanged);
    });
  });

  modal.$("[data-add-event]")?.addEventListener("click", () => {
    modal.close();
    app.openEventForm({ date }, () => {
      onChanged();
      openDayDialog(app, date, onChanged);
    });
  });

  load();
}

export { openDayDialog };
