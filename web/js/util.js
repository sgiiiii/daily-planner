/* Утилиты: даты, склонения, экранирование, константы предметной области. */

export const SPHERES = {
  work: { label: "Работа", className: "work" },
  study: { label: "Учёба", className: "study" },
  personal: { label: "Личное", className: "personal" },
};

export const PRIORITIES = {
  urgent: { label: "Срочно", rank: 4, tone: "urgent" },
  high: { label: "Высокий", rank: 3, tone: "high" },
  normal: { label: "Обычный", rank: 2, tone: "neutral" },
  low: { label: "Низкий", rank: 1, tone: "neutral" },
};

const MONTHS = [
  "января", "февраля", "марта", "апреля", "мая", "июня",
  "июля", "августа", "сентября", "октября", "ноября", "декабря",
];

const MONTHS_NOM = [
  "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
  "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
];

const WEEKDAYS = [
  "воскресенье", "понедельник", "вторник", "среда",
  "четверг", "пятница", "суббота",
];

const WEEKDAYS_SHORT = ["вс", "пн", "вт", "ср", "чт", "пт", "сб"];

export function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[char]));
}

export function plural(count, forms) {
  const n = Math.abs(count) % 100;
  const n1 = n % 10;
  if (n > 10 && n < 20) return forms[2];
  if (n1 > 1 && n1 < 5) return forms[1];
  if (n1 === 1) return forms[0];
  return forms[2];
}

export function tasksWord(n) {
  return plural(n, ["задача", "задачи", "задач"]);
}

export function meetingsWord(n) {
  return plural(n, ["встреча", "встречи", "встреч"]);
}

export function parseIso(iso) {
  if (iso instanceof Date) return iso;
  const [year, month, day] = String(iso).split("-").map(Number);
  return new Date(year, (month || 1) - 1, day || 1);
}

export function isoDate(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function todayIso() {
  return isoDate(new Date());
}

export function addDaysIso(iso, days) {
  const date = parseIso(iso);
  date.setDate(date.getDate() + days);
  return isoDate(date);
}

export function startOfWeekIso(iso) {
  const date = parseIso(iso);
  const offset = (date.getDay() + 6) % 7;
  date.setDate(date.getDate() - offset);
  return isoDate(date);
}

export function fmtDate(iso) {
  const date = parseIso(iso);
  return `${date.getDate()} ${MONTHS[date.getMonth()]}`;
}

export function fmtDateFull(iso) {
  const date = parseIso(iso);
  return `${WEEKDAYS[date.getDay()]}, ${date.getDate()} ${MONTHS[date.getMonth()]}`;
}

export function fmtDateNumeric(iso) {
  const date = parseIso(iso);
  return `${String(date.getDate()).padStart(2, "0")}.${String(date.getMonth() + 1).padStart(2, "0")}.${date.getFullYear()}`;
}

export function weekdayShort(iso) {
  return WEEKDAYS_SHORT[parseIso(iso).getDay()];
}

export function weekdayShortUpper(iso) {
  return weekdayShort(iso).toUpperCase();
}

export function monthLabel(iso) {
  const date = parseIso(iso);
  return `${MONTHS_NOM[date.getMonth()]} ${date.getFullYear()}`;
}

export function relativeDay(iso) {
  const today = todayIso();
  if (iso === today) return "Сегодня";
  if (iso === addDaysIso(today, 1)) return "Завтра";
  if (iso === addDaysIso(today, -1)) return "Вчера";
  return fmtDate(iso);
}

export function isToday(iso) {
  return iso === todayIso();
}

export function isWeekend(iso) {
  const day = parseIso(iso).getDay();
  return day === 0 || day === 6;
}

export function greeting() {
  const hour = new Date().getHours();
  if (hour < 5) return "Доброй ночи";
  if (hour < 12) return "Доброе утро";
  if (hour < 18) return "Добрый день";
  return "Добрый вечер";
}

export function initials(name) {
  const parts = String(name || "").trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "?";
  if (parts.length === 1) return parts[0].slice(0, 1).toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
}

export function timeNow() {
  const now = new Date();
  return `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
}

export function sphereLabel(sphere) {
  return SPHERES[sphere]?.label ?? "Без сферы";
}

export function priorityLabel(priority) {
  return PRIORITIES[priority]?.label ?? "Обычный";
}

export function sortByTime(items, getTime) {
  return [...items].sort((a, b) => {
    const left = getTime(a) || "99:99";
    const right = getTime(b) || "99:99";
    return left.localeCompare(right);
  });
}

export function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}
