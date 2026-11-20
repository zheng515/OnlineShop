/* Shared helpers: API access, authentication state, header, toasts, formatting. */

const CURRENCY = "$";
const SIZES = ["S", "M", "L", "XL"];
const HOME_PAGES = { admin: "/admin.html", customer: "/shop.html" };
// Only the user's name and role are kept in the browser for rendering the page; the session
// itself lives in an HttpOnly cookie that scripts cannot read (FR51).
const STORAGE_KEY = "onlineshop.user";
const CSRF_COOKIE = "shop_csrf";
const SAFE_METHODS = ["GET", "HEAD", "OPTIONS"];
// Codes for 403 responses that are not about the user's role, so no redirect is wanted.
const SECURITY_CHECK_CODES = ["csrf_failed", "origin_rejected"];

try {
  localStorage.removeItem("onlineshop.session"); // held a session token before rev. 4
} catch {
  /* Storage may be unavailable. */
}

class ApiError extends Error {
  constructor(message, status, data) {
    super(message);
    this.status = status;
    this.data = data || {};
    this.errors = (data && data.errors) || [message];
  }
}

const Auth = {
  get user() {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY)) || null;
    } catch {
      return null;
    }
  },
  save(user) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(user));
    } catch {
      /* The server still knows who is logged in; only the header display is affected. */
    }
  },
  clear() {
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      /* Nothing to clear. */
    }
  },
};

function readCookie(name) {
  const match = document.cookie.split("; ").find((part) => part.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : "";
}

const LOGIN_PAGE = "/login.html";
// Shown to visitors who are not logged in on pages open to everyone (FR88).
const GUEST = Object.freeze({ role: "guest" });

/** A shop-relative address to come back to after logging in, or null if it is not one (FR98). */
function safeNext(value) {
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.includes("\\")) return null;
  return value;
}

function loginUrl(next = window.location.pathname + window.location.search) {
  const target = safeNext(next);
  return target && target !== LOGIN_PAGE ? `${LOGIN_PAGE}?next=${encodeURIComponent(target)}` : LOGIN_PAGE;
}

/** Send the user to the login page; by default they come back here afterwards (FR5, FR98). */
function goToLogin({ comeBack = true } = {}) {
  Auth.clear();
  window.location.replace(comeBack ? loginUrl() : LOGIN_PAGE);
}

/**
 * Call the backend. `json` sends a JSON body, `form` sends FormData.
 * A 401 response means the session is gone, so the user is sent to the login page
 * unless `redirectOn401` is false.
 */
async function api(path, { method = "GET", json, form, redirectOn401 = true } = {}) {
  const headers = {};
  // Anti-forgery token for state-changing requests (FR52).
  if (!SAFE_METHODS.includes(method)) headers["X-CSRF-Token"] = readCookie(CSRF_COOKIE);
  let body;
  if (json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(json);
  } else if (form) {
    body = form;
  }

  let response;
  try {
    response = await fetch(path, { method, headers, body, credentials: "same-origin" });
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
    if (response.status === 403 && !SECURITY_CHECK_CODES.includes(data && data.code)) {
      const user = Auth.user;
      if (user && HOME_PAGES[user.role]) window.location.replace(HOME_PAGES[user.role]);
    }
    throw new ApiError(message, response.status, data);
  }
  return data;
}

/**
 * Page guard: only users with `role` may stay on this page (FR5). With `allowGuest`, visitors who
 * are not logged in may stay too and get GUEST (FR88). Returns null when the page is being left.
 */
function requireRole(role, { allowGuest = false } = {}) {
  const user = Auth.user;
  if (!user) {
    if (allowGuest) return GUEST;
    goToLogin();
    return null;
  }
  if (user.role !== role) {
    window.location.replace(HOME_PAGES[user.role] || LOGIN_PAGE);
    return null;
  }
  return user;
}

async function logout() {
  try {
    await api("/api/auth/logout", { method: "POST", redirectOn401: false });
  } catch {
    /* The session is cleared locally either way. */
  }
  goToLogin({ comeBack: false });
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
  if (!header) return;
  if (!user) {
    renderGuestHeader(header, active);
    return;
  }

  const links =
    user.role === "admin"
      ? [
          { id: "products", href: "/admin.html", label: "Product Management" },
          { id: "orders", href: "/admin-orders.html", label: "Orders" },
          { id: "shipping", href: "/admin-shipping.html", label: "Delivery" },
        ]
      : [
          { id: "shop", href: "/shop.html", label: "Products" },
          { id: "cart", href: "/cart.html", label: 'Cart <span class="badge hidden" id="cart-count">0</span>' },
          { id: "orders", href: "/orders.html", label: "My Orders" },
          { id: "account", href: "/account.html", label: "Account" },
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

function renderGuestHeader(header, active) {
  header.className = "site-header";
  header.innerHTML = `
    <div class="inner">
      <a class="brand" href="/shop.html"><span class="logo">OS</span>OnlineShop</a>
      <nav class="nav">
        <a href="/shop.html" class="${active === "shop" ? "active" : ""}">Products</a>
      </nav>
      <div class="user-box">
        <a class="btn btn-secondary btn-sm" href="${escapeHtml(loginUrl())}">Log in</a>
        <a class="btn btn-sm" href="/register.html">Register</a>
      </div>
    </div>`;
}

function setCartCount(count) {
  const badge = document.getElementById("cart-count");
  if (!badge) return;
  badge.textContent = count;
  badge.classList.toggle("hidden", !count);
}

async function refreshCartCount() {
  try {
    const cart = await api("/api/cart", { redirectOn401: false });
    setCartCount(cart.item_count);
  } catch (err) {
    // On a page open to visitors, an expired session just turns the page into the visitor view.
    if (err.status === 401) {
      Auth.clear();
      renderHeader();
    }
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

function formatDateTime(iso) {
  return iso ? new Date(iso).toLocaleString() : "—";
}

function statusBadge(order) {
  return `<span class="status status-${escapeHtml(order.status)}">${escapeHtml(order.status_label)}</span>`;
}

/** A random id identifying one order submission, so a repeated click creates only one order (FR43). */
function newRequestId() {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

/** Show a confirmation dialog. Resolves to true when the user confirms. */
function confirmDialog({ title, message, confirmLabel = "Confirm", cancelLabel = "Cancel", danger = false }) {
  return new Promise((resolve) => {
    const backdrop = document.createElement("div");
    backdrop.className = "modal-backdrop";
    backdrop.innerHTML = `
      <div class="card modal modal-sm" role="alertdialog" aria-modal="true" aria-labelledby="confirm-title">
        <div class="modal-header"><h2 id="confirm-title">${escapeHtml(title)}</h2></div>
        <div class="modal-body"><p>${escapeHtml(message)}</p></div>
        <div class="modal-footer">
          <button type="button" class="btn btn-secondary" data-answer="no">${escapeHtml(cancelLabel)}</button>
          <button type="button" class="btn ${danger ? "btn-danger" : ""}" data-answer="yes">${escapeHtml(confirmLabel)}</button>
        </div>
      </div>`;
    function close(answer) {
      document.removeEventListener("keydown", onKey);
      backdrop.remove();
      resolve(answer);
    }
    function onKey(e) {
      if (e.key === "Escape") close(false);
    }
    backdrop.addEventListener("click", (e) => {
      const button = e.target.closest("[data-answer]");
      if (button) close(button.dataset.answer === "yes");
      else if (e.target === backdrop) close(false);
    });
    document.addEventListener("keydown", onKey);
    document.body.appendChild(backdrop);
    backdrop.querySelector('[data-answer="yes"]').focus();
  });
}

/**
 * Render pagination for a list result ({page, pages, total, page_size}) into `container` (FR63).
 * `onPage(n)` is called when the user picks a page; `noun` names the items, e.g. "products".
 */
function renderPagination(container, result, onPage, noun = "products") {
  const { page, pages, total, page_size: size } = result;
  const first = total ? (page - 1) * size + 1 : 0;
  const last = Math.min(page * size, total);
  const summary = total ? `Showing ${first}–${last} of ${total} ${noun}` : "";
  if (pages <= 1) {
    container.innerHTML = summary ? `<p class="pagination-summary">${summary}</p>` : "";
    return;
  }
  const near = [];
  for (let n = Math.max(1, page - 2); n <= Math.min(pages, page + 2); n++) near.push(n);
  const button = (n, label, aria, disabled = false) =>
    `<button type="button" class="page-btn ${n === page && label === String(n) ? "current" : ""}" data-page="${n}"
       aria-label="${aria}" ${disabled ? "disabled" : ""} ${n === page && label === String(n) ? 'aria-current="page"' : ""}>${label}</button>`;
  container.innerHTML = `
    <p class="pagination-summary">${summary}</p>
    <nav class="pagination" aria-label="Pages">
      ${button(1, "«", "First page", page === 1)}
      ${button(page - 1, "‹", "Previous page", page === 1)}
      ${near[0] > 1 ? '<span class="page-gap">…</span>' : ""}
      ${near.map((n) => button(n, String(n), `Page ${n}`)).join("")}
      ${near[near.length - 1] < pages ? '<span class="page-gap">…</span>' : ""}
      ${button(page + 1, "›", "Next page", page === pages)}
      ${button(pages, "»", "Last page", page === pages)}
    </nav>`;
  container.querySelector(".pagination").addEventListener("click", (e) => {
    const target = e.target.closest("[data-page]");
    if (target && !target.disabled) onPage(Number(target.dataset.page));
  });
}

/** Plain text with line breaks kept; markup is shown as text, never interpreted (FR61). */
function formatDescription(text) {
  return escapeHtml(text).replace(/\n/g, "<br>");
}
