/* Shared helpers: API access, authentication state, header, toasts, formatting. */

const CURRENCY = "$";
const SIZES = ["S", "M", "L", "XL"];
const HOME_PAGES = { admin: "/admin.html", customer: "/shop.html" };
const STORAGE_KEY = "onlineshop.session";

class ApiError extends Error {
  constructor(message, status, data) {
    super(message);
    this.status = status;
    this.data = data || {};
    this.errors = (data && data.errors) || [message];
  }
}

const Auth = {
  load() {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY)) || null;
    } catch {
      return null;
    }
  },
  save(token, user) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ token, user }));
  },
  clear() {
    localStorage.removeItem(STORAGE_KEY);
  },
  get token() {
    const session = this.load();
    return session ? session.token : null;
  },
  get user() {
    const session = this.load();
    return session ? session.user : null;
  },
};

function goToLogin() {
  Auth.clear();
  window.location.replace("/index.html");
}

/**
 * Call the backend. `json` sends a JSON body, `form` sends FormData.
 * A 401 response means the session is gone, so the user is sent to the login page
 * unless `redirectOn401` is false.
 */
async function api(path, { method = "GET", json, form, redirectOn401 = true } = {}) {
  const headers = {};
  const token = Auth.token;
  if (token) headers.Authorization = `Bearer ${token}`;
  let body;
  if (json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(json);
  } else if (form) {
    body = form;
  }

  let response;
  try {
    response = await fetch(path, { method, headers, body });
  } catch {
    throw new ApiError("Cannot reach the server. Please check your connection and try again.", 0);
  }

  let data = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }

  if (!response.ok) {
    const message = (data && data.detail) || `Request failed (${response.status}).`;
    if (response.status === 401 && redirectOn401) {
      goToLogin();
    }
    if (response.status === 403) {
      const user = Auth.user;
      if (user && HOME_PAGES[user.role]) window.location.replace(HOME_PAGES[user.role]);
    }
    throw new ApiError(message, response.status, data);
  }
  return data;
}

/** Page guard: only users with `role` may stay on this page (FR5). */
function requireRole(role) {
  const user = Auth.user;
  if (!user || !Auth.token) {
    goToLogin();
    return null;
  }
  if (user.role !== role) {
    window.location.replace(HOME_PAGES[user.role] || "/index.html");
    return null;
  }
  return user;
}

async function logout() {
  try {
    await api("/api/auth/logout", { method: "POST" });
  } catch {
    /* The session is cleared locally either way. */
  }
  goToLogin();
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function formatPrice(value) {
  if (value === null || value === undefined) return "—";
  return `${CURRENCY}${Number(value).toFixed(2)}`;
}

function toast(message, type = "info", timeout = 3500) {
  let box = document.getElementById("toasts");
  if (!box) {
    box = document.createElement("div");
    box.id = "toasts";
    box.setAttribute("aria-live", "polite");
    document.body.appendChild(box);
  }
  const el = document.createElement("div");
  el.className = `toast toast-${type}`;
  el.textContent = message;
  box.appendChild(el);
  setTimeout(() => el.remove(), timeout);
}

/** Render an alert box listing one or more messages into `container`, with an optional heading. */
function showAlert(container, messages, type = "error", title = "") {
  const list = Array.isArray(messages) ? messages : [messages];
  if (!list.length) {
    clearAlert(container);
    return;
  }
  container.className = `alert alert-${type}`;
  const heading = title ? `<strong>${escapeHtml(title)}</strong>` : "";
  container.innerHTML =
    list.length === 1 && !title
      ? escapeHtml(list[0])
      : `${heading}<ul>${list.map((m) => `<li>${escapeHtml(m)}</li>`).join("")}</ul>`;
}

function clearAlert(container) {
  container.innerHTML = "";
  container.className = "hidden";
}

function productImage(url, alt, className = "thumb") {
  if (!url) return `<div class="${className} thumb-placeholder" aria-label="No image">🚫</div>`;
  return `<img class="${className}" src="${escapeHtml(url)}" alt="${escapeHtml(alt)}" loading="lazy">`;
}

/** Build the top navigation bar for the current role. `active` names the current page. */
function renderHeader(active) {
  const user = Auth.user;
  const header = document.getElementById("site-header");
  if (!header || !user) return;

  const links =
    user.role === "admin"
      ? [{ id: "products", href: "/admin.html", label: "Product Management" }]
      : [
          { id: "shop", href: "/shop.html", label: "Products" },
          { id: "cart", href: "/cart.html", label: 'Cart <span class="badge hidden" id="cart-count">0</span>' },
        ];

  header.className = "site-header";
  header.innerHTML = `
    <div class="inner">
      <a class="brand" href="${HOME_PAGES[user.role]}"><span class="logo">OS</span>OnlineShop</a>
      <nav class="nav">
        ${links
          .map((l) => `<a href="${l.href}" class="${l.id === active ? "active" : ""}">${l.label}</a>`)
          .join("")}
      </nav>
      <div class="user-box">
        <span class="role-pill">${user.role === "admin" ? "Administrator" : "Customer"}</span>
        <span class="user-name">${escapeHtml(user.display_name)}</span>
        <button class="btn btn-secondary btn-sm" id="logout-btn" type="button">Log out</button>
      </div>
    </div>`;
  document.getElementById("logout-btn").addEventListener("click", logout);
  if (user.role === "customer") refreshCartCount();
}

function setCartCount(count) {
  const badge = document.getElementById("cart-count");
  if (!badge) return;
  badge.textContent = count;
  badge.classList.toggle("hidden", !count);
}

async function refreshCartCount() {
  try {
    const cart = await api("/api/cart");
    setCartCount(cart.item_count);
  } catch {
    /* Badge is informational only. */
  }
}

function queryParam(name) {
  return new URLSearchParams(window.location.search).get(name);
}

/** Parse a strictly positive whole number from user input; returns null when invalid. */
function parsePositiveInt(value) {
  const text = String(value).trim();
  if (!/^\d+$/.test(text)) return null;
  const n = Number(text);
  return n > 0 ? n : null;
}
