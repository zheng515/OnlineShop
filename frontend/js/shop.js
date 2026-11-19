/* Product browsing: search, filters, sorting and pagination, all kept in the URL (FR15, FR16, FR63-FR66). */

(function () {
  if (!requireRole("customer")) return;
  renderHeader("shop");

  const KEYS = ["q", "category", "min_price", "max_price", "size", "in_stock", "sort", "page"];
  const SORT_LABELS = { price_asc: "Price: low to high", price_desc: "Price: high to low", name: "Name: A to Z" };
  const el = (id) => document.getElementById(id);
  const grid = el("product-grid");
  const message = el("search-message");
  let categories = [];
  let state = readState();

  document.querySelectorAll(".currency").forEach((node) => (node.textContent = CURRENCY));
  // Filters start collapsed on narrow screens so products are visible first.
  if (window.matchMedia("(max-width: 860px)").matches) {
    el("filters").open = false;
    el("filters-summary").classList.remove("hidden");
  }

  function readState() {
    const params = new URLSearchParams(window.location.search);
    return Object.fromEntries(KEYS.map((key) => [key, (params.get(key) || "").trim()]));
  }

  function writeState(push) {
    const params = new URLSearchParams();
    KEYS.forEach((key) => {
      const value = state[key];
      if (value && !(key === "sort" && value === "newest") && !(key === "page" && value === "1")) params.set(key, value);
    });
    const url = `${window.location.pathname}${params.toString() ? `?${params}` : ""}`;
    if (push) history.pushState(null, "", url);
    else history.replaceState(null, "", url);
  }

  /** Change some filters; any change other than the page goes back to page 1 (FR63). */
  function update(changes) {
    state = { ...state, ...changes };
    if (!("page" in changes)) state.page = "";
    writeState(true);
    load();
  }

  function categoryName(id) {
    const match = categories.find((c) => String(c.id) === String(id));
    return match ? match.name : "Unknown category";
  }

  function syncControls() {
    el("search-input").value = state.q;
    el("min-price").value = state.min_price;
    el("max-price").value = state.max_price;
    el("size-filter").value = state.size;
    el("in-stock-filter").checked = state.in_stock === "1";
    el("sort-select").value = SORT_LABELS[state.sort] ? state.sort : "newest";
    el("page-title").textContent = state.category ? categoryName(state.category) : "Products";
    renderCategories();
    renderActiveFilters();
  }

  function renderCategories() {
    const item = (id, name, count) => `
      <li><button type="button" data-category="${id}" class="${String(state.category) === String(id) ? "active" : ""}">
        <span>${escapeHtml(name)}</span>${count === null ? "" : `<span class="count">${count}</span>`}</button></li>`;
    el("category-list").innerHTML =
      item("", "All products", null) + categories.map((c) => item(c.id, c.name, c.product_count)).join("");
  }

  function renderActiveFilters() {
    const chips = [];
    if (state.q) chips.push(["q", `“${state.q}”`]);
    if (state.category) chips.push(["category", categoryName(state.category)]);
    if (state.min_price || state.max_price) {
      // Values come from the URL and may not be numbers.
      const money = (v) => (/^\d+(\.\d{1,2})?$/.test(v) ? formatPrice(v) : v);
      const low = state.min_price ? money(state.min_price) : "any";
      const high = state.max_price ? money(state.max_price) : "any";
      chips.push(["price", `Price ${low} – ${high}`]);
    }
    if (state.size) chips.push(["size", `Size ${state.size} in stock`]);
    if (state.in_stock === "1") chips.push(["in_stock", "In stock only"]);
    el("active-filters").innerHTML = chips.length
      ? chips
          .map(([key, label]) => `<button type="button" class="chip" data-clear="${key}" aria-label="Remove filter ${escapeHtml(label)}">${escapeHtml(label)} ✕</button>`)
          .join("") + '<button type="button" class="chip chip-clear" data-clear="all">Clear all</button>'
      : "";
  }

  function renderProducts(result) {
    if (!result.products.length) {
      const filtered = KEYS.some((key) => key !== "sort" && key !== "page" && state[key]);
      grid.innerHTML = `<div class="empty-state span-all">
        <div class="icon">🔍</div>
        <p>${filtered ? "No products match your search and filters." : "There are no products available right now."}</p>
        ${filtered ? '<button type="button" class="btn btn-secondary" data-clear="all">Show all products</button>' : ""}
      </div>`;
      return;
    }
    grid.innerHTML = result.products
      .map(
        (p) => `
        <a class="card product-card" href="/product.html?id=${p.id}">
          <div class="image">
            <img src="${escapeHtml(p.image_url)}" alt="${escapeHtml(p.name)}" loading="lazy">
            ${p.in_stock ? "" : '<span class="ribbon">Out of stock</span>'}
          </div>
          <div class="info">
            ${p.category ? `<div class="category-label">${escapeHtml(p.category.name)}</div>` : ""}
            <div class="name">${escapeHtml(p.name)}</div>
            <div class="price">${formatPrice(p.price)}</div>
          </div>
        </a>`
      )
      .join("");
  }

  async function load() {
    syncControls();
    const params = new URLSearchParams();
    KEYS.forEach((key) => state[key] && params.set(key, state[key]));
    try {
      const result = await api(`/api/products?${params}`);
      if (String(result.page) !== (state.page || "1")) {
        // The server clamped an out-of-range page; show the page actually displayed.
        state.page = result.page > 1 ? String(result.page) : "";
        writeState(false);
      }
      el("result-count").textContent = `${result.total} product${result.total === 1 ? "" : "s"}`;
      if (result.notices.length) showAlert(message, result.notices, "warning");
      else if (state.q && !result.total) showAlert(message, `No products found for “${state.q}”. Try a different keyword.`, "warning");
      else clearAlert(message);
      renderProducts(result);
      renderPagination(el("pagination"), result, (page) => {
        update({ page: String(page) });
        window.scrollTo({ top: 0, behavior: "smooth" });
      });
    } catch (err) {
      grid.innerHTML = "";
      el("pagination").innerHTML = "";
      showAlert(message, err.errors);
    }
  }

  // ---------- Controls ----------
  el("search-form").addEventListener("submit", (e) => {
    e.preventDefault();
    update({ q: el("search-input").value.trim() });
  });
  el("category-list").addEventListener("click", (e) => {
    const button = e.target.closest("[data-category]");
    if (button) update({ category: button.dataset.category });
  });
  el("price-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const low = el("min-price").value.trim();
    const high = el("max-price").value.trim();
    const valid = (v) => !v || /^\d+(\.\d{1,2})?$/.test(v);
    if (!valid(low) || !valid(high)) {
      showAlert(message, "Prices must be amounts of 0 or more with at most two decimal places.", "warning");
      return;
    }
    if (low && high && Number(low) > Number(high)) {
      showAlert(message, "The minimum price is higher than the maximum price.", "warning");
      return;
    }
    update({ min_price: low, max_price: high });
  });
  el("size-filter").addEventListener("change", (e) => update({ size: e.target.value }));
  el("in-stock-filter").addEventListener("change", (e) => update({ in_stock: e.target.checked ? "1" : "" }));
  el("sort-select").addEventListener("change", (e) => update({ sort: e.target.value }));
  document.addEventListener("click", (e) => {
    const chip = e.target.closest("[data-clear]");
    if (!chip) return;
    const key = chip.dataset.clear;
    if (key === "all") update({ q: "", category: "", min_price: "", max_price: "", size: "", in_stock: "" });
    else if (key === "price") update({ min_price: "", max_price: "" });
    else update({ [key]: "" });
  });
  window.addEventListener("popstate", () => {
    state = readState();
    load();
  });

  (async function init() {
    try {
      categories = (await api("/api/categories")).categories;
    } catch {
      categories = [];
    }
    load();
  })();
})();
