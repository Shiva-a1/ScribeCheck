const KEY = "scribe-token";

export const token = () => sessionStorage.getItem(KEY);
export const setToken = (value) => sessionStorage.setItem(KEY, value);

export function signOut() {
  sessionStorage.removeItem(KEY);
  location.href = "/";
}

export class ApiError extends Error {
  constructor(status, detail) {
    super(typeof detail === "string" ? detail : detail?.message ?? `Something went wrong (${status}).`);
    this.status = status;
    this.detail = detail;
  }
}

export async function api(path, { method = "GET", body, form } = {}) {
  const headers = { Authorization: `Bearer ${token() ?? ""}` };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const response = await fetch(path, { method, headers, body: form ?? (body === undefined ? undefined : JSON.stringify(body)) });
  if (response.status === 401) {
    signOut();
    throw new ApiError(401, "Signed out");
  }
  const isJson = response.headers.get("content-type")?.includes("application/json");
  const data = isJson ? await response.json() : await response.text();
  if (!response.ok) throw new ApiError(response.status, isJson ? data.detail : data);
  return data;
}

export function h(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === false || value == null) continue;
    if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (key === "class") node.className = value;
    else node.setAttribute(key, value === true ? "" : value);
  }
  node.append(...children.flat(Infinity).filter((c) => c != null && c !== false).map((c) => (c instanceof Node ? c : String(c))));
  return node;
}

export const marks = (value) => (value == null ? "–" : Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 }));

export function toast(message, kind = "") {
  document.querySelector(".toast")?.remove();
  const note = h("div", { class: `toast ${kind}`, role: "status" }, message);
  document.body.append(note);
  setTimeout(() => note.remove(), 4000);
}

export async function busy(button, label, task) {
  const original = button.textContent;
  button.disabled = true;
  button.textContent = label;
  try {
    return await task();
  } catch (error) {
    toast(error.message, "bad");
    throw error;
  } finally {
    button.disabled = false;
    button.textContent = original;
  }
}

export function upload(file) {
  const form = new FormData();
  form.append("file", file);
  return form;
}

export async function currentUser(role) {
  if (!token()) return void (location.href = "/");
  const user = await api("/api/me");
  const home = user.role === "student" ? "/student.html" : "/teacher.html";
  if (!location.pathname.endsWith(home)) location.href = home;
  document.querySelector("#who").textContent = user.email;
  document.querySelector("#sign-out").addEventListener("click", signOut);
  return user;
}
