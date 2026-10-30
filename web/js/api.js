/* Клиент REST API. */

export class ApiError extends Error {
  constructor(message, { status = 0, code = "error", fields = {} } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.fields = fields;
  }
}

let unauthorizedHandler = null;

export function onUnauthorized(handler) {
  unauthorizedHandler = handler;
}

async function request(method, path, body) {
  let response;
  try {
    response = await fetch(path, {
      method,
      credentials: "same-origin",
      headers: body === undefined ? {} : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (error) {
    throw new ApiError("Сервер недоступен. Проверьте, что он запущен.", { status: 0, code: "network" });
  }

  const text = await response.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = null;
    }
  }

  if (!response.ok) {
    const error = data?.error ?? {};
    const apiError = new ApiError(
      error.message || `Ошибка запроса (${response.status})`,
      { status: response.status, code: error.code || "error", fields: error.fields || {} }
    );
    if (response.status === 401 && !path.startsWith("/api/auth/")) {
      unauthorizedHandler?.();
    }
    throw apiError;
  }
  return data ?? {};
}

function query(params) {
  const search = new URLSearchParams();
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") search.set(key, value);
  });
  const text = search.toString();
  return text ? `?${text}` : "";
}

export const api = {
  health: () => request("GET", "/api/health"),
  config: () => request("GET", "/api/config"),

  me: () => request("GET", "/api/me"),
  login: (payload) => request("POST", "/api/auth/login", payload),
  register: (payload) => request("POST", "/api/auth/register", payload),
  logout: () => request("POST", "/api/auth/logout", {}),
  updateMe: (payload) => request("PATCH", "/api/me", payload),
  changePassword: (payload) => request("POST", "/api/me/password", payload),
  deleteAccount: () => request("DELETE", "/api/me"),

  tasks: {
    list: (params) => request("GET", `/api/tasks${query(params)}`),
    create: (payload) => request("POST", "/api/tasks", payload),
    get: (id) => request("GET", `/api/tasks/${id}`),
    update: (id, payload) => request("PATCH", `/api/tasks/${id}`, payload),
    remove: (id) => request("DELETE", `/api/tasks/${id}`),
    restore: (id) => request("POST", `/api/tasks/${id}/restore`, {}),
    toggle: (id, done) => request("POST", `/api/tasks/${id}/toggle`, { done }),
    carry: (id, date) => request("POST", `/api/tasks/${id}/carry`, { date }),
  },

  day: (date) => request("GET", `/api/day${query({ date })}`),
  summary: (date) => request("GET", `/api/summary${query({ date })}`),
  review: (date) => request("GET", `/api/review${query({ date })}`),
  confirmReview: (date) => request("POST", "/api/review/confirm", { date }),
  carryAll: (date) => request("POST", "/api/review/carry-all", { date }),
  rollover: () => request("POST", "/api/rollover", {}),

  events: {
    list: (from, to) => request("GET", `/api/events${query({ from, to })}`),
    create: (payload) => request("POST", "/api/events", payload),
    update: (id, payload) => request("PATCH", `/api/events/${id}`, payload),
    remove: (id) => request("DELETE", `/api/events/${id}`),
  },

  calendar: (from, to) => request("GET", `/api/calendar${query({ from, to })}`),
};
