/* Главный экран: сводка дня, приоритеты, переносы, встречи. */

import { api } from "../api.js";
import { icon } from "../icons.js";
import {
  bindTaskList,
  emptyState,
  taskRow,
} from "../components.js";
import { errorState, loadingRows, toast } from "../ui.js";
import {
  esc,
  fmtDateFull,
  greeting,
  relativeDay,
  tasksWord,
  todayIso,
  meetingsWord,
} from "../util.js";

export default {
  name: "home",

  async mount(root, app) {
    const draw = async () => {
      root.innerHTML = `<div class="loading">${loadingRows(3)}</div>`;
      let data;
      try {
        data = await api.summary(todayIso());
      } catch (error) {
        root.innerHTML = errorState(error.message);
        root.querySelector("[data-retry]")?.addEventListener("click", draw);
        return;
      }

      const { stats, priorities, carried, overdue, events, nextEvent, user } = data;
      const priorityPreview = priorities.slice(0, 3);
      const remaining = priorities.length - priorityPreview.length;
      const meetings = events.length;
      const name = user?.name || app.user?.name || "друг";

      const summaryTitle =
        stats.total === 0
          ? "На сегодня задач нет"
          : stats.percent === 100
          ? "Все задачи на сегодня закрыты"
          : stats.percent >= 50
          ? "Больше половины уже сделано"
          : "День только начинается";

      root.innerHTML = `
        <div class="page-head">
          <div class="page-head__title">
            <p class="eyebrow">Сегодня · ${esc(fmtDateFull(todayIso()))}</p>
            <h1>${esc(greeting())}, ${esc(name)}</h1>
            <p class="subtitle">
              ${stats.total} ${tasksWord(stats.total)} на сегодня${
        priorities.length ? ` · ${priorities.length} в приоритете` : ""
      }${meetings ? ` · ${meetings} ${meetingsWord(meetings)}` : ""}
            </p>
          </div>
          <div class="page-head__actions">
            <a class="btn btn--secondary btn--desktop" href="/review">${icon("review")}Итог дня</a>
            <button class="btn btn--primary" type="button" data-act="add">${icon("plus")}Новая задача</button>
          </div>
        </div>

        <form class="quick-add" data-quick-add autocomplete="off">
          <label class="visually-hidden" for="quick-title">Быстро добавить задачу</label>
          <input class="input quick-add__input" id="quick-title" name="title" type="text" maxlength="200"
            placeholder="Что нужно не забыть? Нажмите Enter — задача попадёт в список на сегодня">
          <button class="btn btn--primary" type="submit">Добавить</button>
        </form>

        <div class="dash">
          <div class="stack">
            <section class="card">
              <div class="summary-card">
                <div class="ring" style="--p:${stats.percent}" role="img"
                  aria-label="Выполнено ${stats.percent}% задач">
                  <div class="ring__inner">
                    <b>${stats.done}/${stats.total}</b>
                    <span>выполнено</span>
                  </div>
                </div>
                <div class="summary-copy">
                  <h2>${esc(summaryTitle)}</h2>
                  <p class="subtitle">${
                    stats.open
                      ? `Осталось ${stats.open} ${tasksWord(stats.open)} — начните с самой срочной.`
                      : "Можно подвести итог дня и перенести незакрытые дела."
                  }</p>
                  <div class="summary-stats">
                    <div class="summary-stat"><b>${stats.open}</b><span>в работе</span></div>
                    <div class="summary-stat"><b>${carried.length}</b><span>перенесено</span></div>
                    <div class="summary-stat"><b>${meetings}</b><span>${meetingsWord(meetings)}</span></div>
                  </div>
                </div>
              </div>
            </section>

            <section class="card">
              <div class="card__head">
                <h2>Приоритетные задачи</h2>
                ${
                  remaining > 0
                    ? `<a class="small" href="/tasks">Показать все (${priorities.length})</a>`
                    : ""
                }
              </div>
              ${
                priorityPreview.length
                  ? `<ul class="task-list priority-list">${priorityPreview
                      .map((task) => taskRow(task))
                      .join("")}</ul>`
                  : emptyState({
                      iconName: "check",
                      title: stats.total ? "Приоритеты закрыты" : "Список на сегодня пуст",
                      text: stats.total
                        ? "Все приоритетные задачи выполнены. Добавьте новую или подведите итог дня."
                        : "Добавьте первую задачу — и она появится здесь и в разделе «Задачи».",
                      action: '<button class="btn btn--secondary btn--sm" type="button" data-act="add">Добавить задачу</button>',
                    })
              }
            </section>

            ${
              carried.length
                ? `<section class="card">
                    <div class="card__head">
                      <h2>Перенесено с прошлых дней</h2>
                      <span class="badge badge--carried">${carried.length}</span>
                    </div>
                    <ul class="task-list">${carried.map((task) => taskRow(task)).join("")}</ul>
                  </section>`
                : ""
            }
          </div>

          <aside class="dash__aside">
            <section class="card">
              <div class="card__head">
                <h2>${nextEvent ? "Ближайшая встреча" : "Встречи"}</h2>
                <a class="small" href="/calendar">Календарь</a>
              </div>
              ${
                nextEvent
                  ? `<div class="event-now">
                       <span class="event-now__time">${esc(nextEvent.start)}${nextEvent.end ? "–" + esc(nextEvent.end) : ""}</span>
                       <span class="event-now__title">${esc(nextEvent.title)}</span>
                       <span class="caption">${esc(relativeDay(nextEvent.date))}</span>
                     </div>`
                  : '<p class="small muted">На сегодня встреч нет — можно спокойно работать над задачами.</p>'
              }
            </section>

            <section class="card">
              <div class="card__head">
                <h2>Итог дня</h2>
                <span class="badge badge--neutral">${stats.done} из ${stats.total}</span>
              </div>
              <p class="small muted" style="margin-bottom:16px">
                Вечером просмотрите выполненные и незакрытые дела, перенесите остатки на завтра.
              </p>
              <a class="btn btn--primary btn--block" href="/review">${icon("review")}Подвести итог дня</a>
            </section>

            ${
              overdue.length
                ? `<section class="card overdue-card">
                     <div class="card__head">
                       <h3>Просрочено: ${overdue.length}</h3>
                       <a class="small" href="/tasks?filter=overdue">Показать</a>
                     </div>
                     <p class="small">Задачи, которые ждут дольше своего срока.</p>
                     <div class="overdue-list">
                       ${overdue
                         .slice(0, 3)
                         .map((task) => `<span class="small">${esc(task.title)}</span>`)
                         .join("")}
                     </div>
                   </section>`
                : ""
            }
          </aside>
        </div>
      `;

      bindTaskList(root, app, draw);

      root.querySelectorAll("[data-act='add']").forEach((button) =>
        button.addEventListener("click", () =>
          app.openTaskForm({ date: todayIso() }, draw)
        )
      );

      const quickForm = root.querySelector("[data-quick-add]");
      quickForm?.addEventListener("submit", async (event) => {
        event.preventDefault();
        const input = quickForm.querySelector("input");
        const title = input.value.trim();
        if (!title) {
          input.setAttribute("aria-invalid", "true");
          input.focus();
          return;
        }
        try {
          const created = (
            await api.tasks.create({
              title,
              date: todayIso(),
              sphere: "work",
              priority: "normal",
            })
          ).task;
          input.value = "";
          input.removeAttribute("aria-invalid");
          toast("Задача добавлена на сегодня", {
            actionLabel: "Изменить",
            onAction: () => app.openTaskForm({ task: created }, draw),
          });
          draw();
        } catch (error) {
          toast(error.message, { duration: 5000 });
        }
      });
    };

    await draw();
  },
};
