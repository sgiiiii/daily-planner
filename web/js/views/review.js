/* Экран «Итог дня»: разбор выполненных и незакрытых дел с отменой действий. */

import { api } from "../api.js";
import { icon } from "../icons.js";
import { taskRow, bindTaskList, sphereTag } from "../components.js";
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

export default {
  name: "review",

  async mount(root, app) {
    const params = new URLSearchParams(window.location.search);
    const state = {
      date: params.get("date") || todayIso(),
      moved: new Map(),
      kept: new Set(),
      final: null,
    };
    const tomorrow = addDaysIso(state.date, 1);

    const draw = async () => {
      if (state.final) {
        renderFinal(state.final);
        return;
      }
      root.innerHTML = `<div class="loading">${loadingRows(3)}</div>`;

      let review;
      try {
        review = await api.review(state.date);
      } catch (error) {
        root.innerHTML = errorState(error.message);
        root.querySelector("[data-retry]")?.addEventListener("click", draw);
        return;
      }

      const { stats } = review;
      const openAll = [
        ...review.open.map((task) => ({ ...task, source: "today" })),
        ...review.overdue.map((task) => ({ ...task, source: "overdue" })),
      ];
      const pending = openAll.filter((task) => !state.moved.has(task.id));
      const movedTasks = [...state.moved.values()];
      const keptTasks = pending.filter((task) => state.kept.has(task.id));

      root.innerHTML = `
        <div class="page-head">
          <div class="page-head__title">
            <p class="eyebrow">Итог дня</p>
            <h1>${esc(fmtDateFull(state.date))}</h1>
            <p class="subtitle">Разберите незакрытые дела и решите, что перенести на завтра</p>
          </div>
          <div class="page-head__actions">
            <a class="btn btn--secondary" href="/">На главную</a>
          </div>
        </div>

        <div class="review-stats">
          <div class="card review-stat">
            <span class="review-stat__label">Выполнено</span>
            <span class="review-stat__num">${stats.done} из ${stats.total}</span>
            <div class="progress"><span class="progress__bar" style="width:${stats.percent}%"></span></div>
          </div>
          <div class="card review-stat">
            <span class="review-stat__label">Осталось разобрать</span>
            <span class="review-stat__num" style="color:${pending.length ? "var(--error)" : "var(--success)"}">${pending.length}</span>
            <span class="caption">${pending.length ? "Задачи ниже" : "Всё разобрано"}</span>
          </div>
          <div class="card review-stat">
            <span class="review-stat__label">Перенесено на завтра</span>
            <span class="review-stat__num">${movedTasks.length}</span>
            <span class="caption">${esc(relativeDay(tomorrow))}, ${esc(fmtDateFull(tomorrow))}</span>
          </div>
        </div>

        ${
          review.done.length
            ? `<section class="card" style="margin-bottom:24px">
                 <div class="card__head">
                   <h2>Сделано сегодня</h2>
                   <span class="badge badge--soft">${review.done.length}</span>
                 </div>
                 <ul class="task-list">${review.done.map((task) => taskRow(task)).join("")}</ul>
               </section>`
            : ""
        }

        <section class="card" style="margin-bottom:24px">
          <div class="card__head">
            <h2>${pending.length ? "Что делаем с остальными?" : "Все задачи разобраны"}</h2>
            <span class="badge badge--neutral">${pending.length} ${tasksWord(pending.length)}</span>
          </div>
          ${
            pending.length
              ? `<ul class="task-list">${pending
                  .map(
                    (task) => `
                    <li class="review-row ${task.source === "overdue" ? "review-row--open" : ""}" data-review-id="${task.id}">
                      <div>
                        <div class="task__title">${esc(task.title)}</div>
                        <div class="task__meta">
                          ${sphereTag(task.sphere)}
                          ${task.overdue ? '<span class="badge badge--urgent">просрочена</span>' : ""}
                          ${task.carried ? '<span class="badge badge--carried">перенесена</span>' : ""}
                          ${task.time ? `<span>${icon("clock")}${esc(task.time)}</span>` : ""}
                          ${
                            state.kept.has(task.id)
                              ? '<span class="badge badge--neutral">остаётся на сегодня</span>'
                              : ""
                          }
                        </div>
                      </div>
                      <div class="review-row__actions">
                        ${
                          state.kept.has(task.id)
                            ? `<button class="btn btn--secondary btn--sm" type="button" data-keep-undo="${task.id}">Вернуть в разбор</button>`
                            : `<button class="btn btn--secondary btn--sm" type="button" data-keep="${task.id}">Оставить</button>`
                        }
                        <button class="btn btn--primary btn--sm" type="button" data-move="${task.id}">Перенести</button>
                      </div>
                    </li>`
                  )
                  .join("")}</ul>`
              : `<div class="empty">
                   ${icon("check")}
                   <strong>Незакрытых задач нет</strong>
                   <span>Можно подвести итог дня — все дела либо выполнены, либо перенесены.</span>
                 </div>`
          }
        </section>

        ${
          movedTasks.length
            ? `<section class="card" style="margin-bottom:24px">
                 <div class="card__head">
                   <h2>На завтра</h2>
                   <a class="small" href="/tasks?date=${tomorrow}">Открыть день</a>
                 </div>
                 <ul class="task-list">${movedTasks
                   .map(
                     (task) => `
                     <li class="task">
                       <span class="check" aria-hidden="true"><span class="check__box">${icon("arrow-right")}</span></span>
                       <div class="task__body">
                         <div class="task__title">${esc(task.title)}</div>
                         <div class="task__meta"><span class="badge badge--carried">${esc(
                           relativeDay(tomorrow)
                         )}</span></div>
                       </div>
                       <div class="task__right">
                         <button class="btn btn--ghost btn--sm" type="button" data-undo-move="${task.id}">Вернуть</button>
                       </div>
                     </li>`
                   )
                   .join("")}</ul>
               </section>`
            : ""
        }

        <div class="card" style="display:flex;flex-wrap:wrap;gap:12px;justify-content:space-between;align-items:center">
          <div>
            <strong style="display:block;font-weight:500">Подвести итог дня</strong>
            <span class="small muted">Итог сохранится, а незакрытые задачи останутся в списке на сегодня</span>
          </div>
          <div style="display:flex;gap:8px;flex-wrap:wrap">
            ${
              pending.length
                ? `<button class="btn btn--secondary" type="button" data-carry-all>Перенести всё на завтра</button>`
                : ""
            }
            <button class="btn btn--primary" type="button" data-confirm>Подтвердить итог</button>
          </div>
        </div>
      `;

      bindTaskList(root, app, draw);
      bind(root);

      function bind(container) {
        container.querySelectorAll("[data-move]").forEach((button) =>
          button.addEventListener("click", async () => {
            const id = Number(button.dataset.move);
            const task = openAll.find((item) => item.id === id);
            button.disabled = true;
            try {
              await api.tasks.carry(id, tomorrow);
              state.moved.set(id, task);
              state.kept.delete(id);
              toast("Перенесено на завтра", {
                actionLabel: "Вернуть",
                onAction: async () => {
                  try {
                    await api.tasks.update(id, { date: state.date, carried: 0, carriedFrom: null });
                  } catch (error) {
                    toast(error.message);
                  }
                  state.moved.delete(id);
                  draw();
                },
                duration: 8000,
              });
              draw();
            } catch (error) {
              button.disabled = false;
              toast(error.message, { duration: 5000 });
            }
          })
        );

        container.querySelectorAll("[data-undo-move]").forEach((button) =>
          button.addEventListener("click", async () => {
            const id = Number(button.dataset.undoMove);
            button.disabled = true;
            try {
              await api.tasks.update(id, { date: state.date, carried: 0, carriedFrom: null });
              state.moved.delete(id);
              draw();
            } catch (error) {
              button.disabled = false;
              toast(error.message);
            }
          })
        );

        container.querySelectorAll("[data-keep]").forEach((button) =>
          button.addEventListener("click", () => {
            state.kept.add(Number(button.dataset.keep));
            draw();
          })
        );

        container.querySelectorAll("[data-keep-undo]").forEach((button) =>
          button.addEventListener("click", () => {
            state.kept.delete(Number(button.dataset.keepUndo));
            draw();
          })
        );

        container.querySelector("[data-carry-all]")?.addEventListener("click", async (event) => {
          const button = event.currentTarget;
          button.disabled = true;
          try {
            const result = await api.carryAll(state.date);
            toast(`Перенесено ${result.moved} ${tasksWord(result.moved)} на ${relativeDay(tomorrow).toLowerCase()}`, {
              duration: 6000,
            });
            draw();
          } catch (error) {
            button.disabled = false;
            toast(error.message, { duration: 5000 });
          }
        });

        container.querySelector("[data-confirm]")?.addEventListener("click", async (event) => {
          const button = event.currentTarget;
          button.disabled = true;
          try {
            const result = await api.confirmReview(state.date);
            state.final = {
              ...result,
              movedCount: state.moved.size,
            };
            draw();
          } catch (error) {
            button.disabled = false;
            toast(error.message, { duration: 5000 });
          }
        });
      }
    };

    function renderFinal(result) {
      const { stats } = result;
      root.innerHTML = `
        <div class="page-head">
          <div class="page-head__title">
            <p class="eyebrow">Итог дня</p>
            <h1>${esc(fmtDateFull(state.date))}</h1>
          </div>
          <div class="page-head__actions">
            <a class="btn btn--secondary" href="/">На главную</a>
          </div>
        </div>
        <div class="card">
          <div class="review-final">
            <div class="review-final__icon">${icon("check")}</div>
            <h2>Итог дня подведён</h2>
            <p class="muted">Спасибо, что довели день до конца. Вот что получилось:</p>
            <div class="review-final__numbers">
              <div class="summary-stat"><b>${stats.done} из ${stats.total}</b><span>выполнено</span></div>
              <div class="summary-stat"><b>${result.open}</b><span>осталось на сегодня</span></div>
              <div class="summary-stat"><b>${result.tomorrowTotal}</b><span>${plural(result.tomorrowTotal, [
                "задача",
                "задачи",
                "задач",
              ])} на завтра</span></div>
            </div>
            <div style="display:flex;gap:8px;flex-wrap:wrap;justify-content:center;margin-top:8px">
              <a class="btn btn--primary" href="/tasks?date=${result.tomorrow}">Открыть задачи на завтра</a>
              <a class="btn btn--secondary" href="/">Вернуться на главную</a>
            </div>
            <p class="caption" style="margin-top:8px">
              Невыполненные задачи переносятся автоматически в ${esc(app.user?.rolloverTime || "04:00")}
            </p>
          </div>
        </div>
      `;
    }

    await draw();
  },
};
