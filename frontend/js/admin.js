/* Product Management page (FR7-FR14, FR60-FR66). */

(function () {
  if (!requireRole("admin")) return;
  renderHeader("products");

  const ALLOWED_TYPES = ["image/jpeg", "image/png", "image/gif", "image/webp"];
  const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
  const MAX_IMAGES = 8;
  const KEYS = ["q", "category", "sort", "page"];

  const el = (id) => document.getElementById(id);
  const rows = el("product-rows");
  const listMessage = el("list-message");
  const formModal = el("form-modal");
  const formError = el("form-error");
  const imageManager = el("image-manager");
  const sizeGrid = el("size-stock-grid");

  let products = [];
  let categories = [];
  let state = readState();
  let editing = null; // product being edited, or null when adding
  let detailProduct = null;
  let formImages = []; // [{id, url}] in display order; the first is the main image
  let uploadsInProgress = 0;

  document.querySelectorAll(".currency").forEach((node) => (node.textContent = CURRENCY));

  // ---------- Modals ----------
  function openModal(modal) {
    modal.classList.remove("hidden");
  }
  function closeModal(modal) {
    modal.classList.add("hidden");
  }
  document.querySelectorAll(".modal-backdrop").forEach((modal) => {
    modal.addEventListener("click", (e) => {
      if (e.target === modal || e.target.closest("[data-close]")) closeModal(modal);
    });
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !document.querySelector('[role="alertdialog"]')) {
      document.querySelectorAll(".modal-backdrop").forEach(closeModal);
    }
  });

  // ---------- List state in the URL (FR66) ----------
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

  function update(changes) {
    state = { ...state, ...changes };
    if (!("page" in changes)) state.page = "";
    writeState(true);
    loadProducts();
  }

  // ---------- Categories ----------
  function categoryOptions(selectedId, emptyLabel) {
    return (
      `<option value="">${escapeHtml(emptyLabel)}</option>` +
      categories
        .map((c) => `<option value="${c.id}" ${String(c.id) === String(selectedId) ? "selected" : ""}>${escapeHtml(c.name)}</option>`)
        .join("")
    );
  }

  async function loadCategories() {
    try {
      categories = (await api("/api/categories")).categories;
    } catch (err) {
      toast(err.message, "error");
    }
    el("category-filter").innerHTML = categoryOptions(state.category, "All categories");
    renderCategoryRows();
  }

  function renderCategoryRows() {
    el("category-rows").innerHTML = categories.length
      ? categories
          .map(
            (c) => `
        <li data-id="${c.id}">
          <input type="text" value="${escapeHtml(c.name)}" maxlength="50" aria-label="Category name">
          <span class="count">${c.product_count} product${c.product_count === 1 ? "" : "s"}</span>
          <button type="button" class="btn btn-secondary btn-sm" data-cat-action="rename">Rename</button>
          <button type="button" class="btn btn-danger btn-sm" data-cat-action="delete">Delete</button>
        </li>`
          )
          .join("")
      : '<li class="muted">No categories yet.</li>';
  }

  el("categories-btn").addEventListener("click", () => {
    clearAlert(el("categories-message"));
    openModal(el("categories-modal"));
  });

  el("new-category-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const input = el("new-category-input");
    try {
      const created = await api("/api/admin/categories", { method: "POST", json: { name: input.value } });
      toast(created.message, "success");
      input.value = "";
      clearAlert(el("categories-message"));
      await loadCategories();
    } catch (err) {
      showAlert(el("categories-message"), err.errors);
    }
  });

  el("category-rows").addEventListener("click", async (e) => {
    const button = e.target.closest("[data-cat-action]");
    if (!button) return;
    const row = button.closest("li[data-id]");
    const category = categories.find((c) => String(c.id) === row.dataset.id);
    try {
      if (button.dataset.catAction === "rename") {
        const renamed = await api(`/api/admin/categories/${category.id}`, {
          method: "PUT",
          json: { name: row.querySelector("input").value },
        });
        toast(renamed.message, "success");
      } else {
        const confirmed = await confirmDialog({
          title: `Delete category “${category.name}”?`,
          message: category.product_count
            ? `Its ${category.product_count} product(s) will stay in the shop without a category.`
            : "This category has no products.",
          confirmLabel: "Delete",
          danger: true,
        });
        if (!confirmed) return;
        const deleted = await api(`/api/admin/categories/${category.id}`, { method: "DELETE" });
        toast(deleted.message, "success");
        if (state.category === String(category.id)) state.category = "";
      }
      clearAlert(el("categories-message"));
      await loadCategories();
      loadProducts();
    } catch (err) {
      showAlert(el("categories-message"), err.errors);
    }
  });

  // ---------- List, search, filter, sort, pages ----------
  function stockCell(product, size) {
    const entry = product.sizes.find((s) => s.size === size);
    if (!entry) return `<td class="stock-cell stock-na" title="Size not offered">—</td>`;
    return `<td class="stock-cell ${entry.stock === 0 ? "stock-zero" : ""}">${entry.stock}</td>`;
  }

  function renderList() {
    if (!products.length) {
      const filtered = state.q || state.category;
      rows.innerHTML = `<tr><td colspan="9"><div class="empty-state"><div class="icon">📦</div>
        <p>${filtered ? "No products match your search or filter." : "No products yet. Add your first product."}</p></div></td></tr>`;
      return;
    }
    rows.innerHTML = products
      .map(
        (p) => `
        <tr>
          <td>${productImage(p.image_url, p.name)}</td>
          <td class="item-name">${escapeHtml(p.name)}${p.images.length > 1 ? `<div class="item-size">${p.images.length} images</div>` : ""}</td>
          <td class="hide-sm">${p.category ? escapeHtml(p.category.name) : '<span class="muted">Uncategorised</span>'}</td>
          <td class="nowrap">${formatPrice(p.price)}</td>
          ${SIZES.map((size) => stockCell(p, size)).join("")}
          <td>
            <div class="actions">
              <button type="button" class="btn btn-secondary btn-sm" data-action="view" data-id="${p.id}">View</button>
              <button type="button" class="btn btn-secondary btn-sm" data-action="edit" data-id="${p.id}">Edit</button>
              <button type="button" class="btn btn-danger btn-sm" data-action="delete" data-id="${p.id}">Delete</button>
            </div>
          </td>
        </tr>`
      )
      .join("");
  }

  async function loadProducts() {
    el("search-input").value = state.q;
    el("clear-search").classList.toggle("hidden", !state.q);
    el("sort-select").value = state.sort || "newest";
    el("category-filter").value = state.category;
    const params = new URLSearchParams();
    KEYS.forEach((key) => state[key] && params.set(key, state[key]));
    try {
      const data = await api(`/api/admin/products?${params}`);
      if (String(data.page) !== (state.page || "1")) {
        state.page = data.page > 1 ? String(data.page) : "";
        writeState(false);
      }
      products = data.products;
      if (state.q) {
        showAlert(
          listMessage,
          data.total ? `Found ${data.total} product(s) matching “${state.q}”.` : `No products found matching “${state.q}”. Try a different keyword.`,
          data.total ? "info" : "warning"
        );
      } else {
        clearAlert(listMessage);
      }
      renderList();
      renderPagination(el("pagination"), data, (page) => update({ page: String(page) }));
    } catch (err) {
      rows.innerHTML = "";
      showAlert(listMessage, err.errors);
    }
  }

  el("search-form").addEventListener("submit", (e) => {
    e.preventDefault();
    update({ q: el("search-input").value.trim() });
  });
  el("clear-search").addEventListener("click", () => update({ q: "" }));
  el("category-filter").addEventListener("change", (e) => update({ category: e.target.value }));
  el("sort-select").addEventListener("change", (e) => update({ sort: e.target.value }));
  window.addEventListener("popstate", () => {
    state = readState();
    loadProducts();
  });

  rows.addEventListener("click", (e) => {
    const button = e.target.closest("button[data-action]");
    if (!button) return;
    const id = Number(button.dataset.id);
    const action = button.dataset.action;
    if (action === "view") showDetails(id);
    else if (action === "edit") openEdit(id);
    else askDelete(products.find((p) => p.id === id));
  });

  async function fetchProduct(id) {
    try {
      return await api(`/api/admin/products/${id}`);
    } catch (err) {
      toast(err.message, "error");
      if (err.status === 404) loadProducts();
      return null;
    }
  }

  // ---------- Details (FR9) ----------
  async function showDetails(id) {
    const p = await fetchProduct(id);
    if (!p) return;
    detailProduct = p;
    const sizes = p.sizes.length
      ? p.sizes
          .map((s) => `${s.size}: <strong class="${s.stock === 0 ? "stock-zero" : ""}">${s.stock}</strong>${s.stock === 0 ? " (out of stock)" : ""}`)
          .join("<br>")
      : "—";
    el("detail-body").innerHTML = `
      <img class="detail-image" src="${escapeHtml(p.image_url)}" alt="${escapeHtml(p.name)}">
      ${p.images.length > 1 ? `<div class="thumbs">${p.images.map((i) => `<img src="${escapeHtml(i.url)}" alt="">`).join("")}</div>` : ""}
      <dl class="detail-list">
        <dt>Name</dt><dd>${escapeHtml(p.name)}</dd>
        <dt>Price</dt><dd>${formatPrice(p.price)}</dd>
        <dt>Category</dt><dd>${p.category ? escapeHtml(p.category.name) : "Uncategorised"}</dd>
        <dt>Description</dt><dd>${p.description ? formatDescription(p.description) : '<span class="muted">None</span>'}</dd>
        <dt>Available sizes</dt><dd>${p.sizes.map((s) => s.size).join(", ") || "—"}</dd>
        <dt>Stock by size</dt><dd>${sizes}</dd>
        <dt>Total stock</dt><dd>${p.total_stock}</dd>
        <dt>Last updated</dt><dd>${formatDateTime(p.updated_at)}</dd>
      </dl>`;
    openModal(el("detail-modal"));
  }
  el("detail-edit-btn").addEventListener("click", () => {
    closeModal(el("detail-modal"));
    if (detailProduct) openEdit(detailProduct.id);
  });

  // ---------- Images in the form (FR14, FR62) ----------
  function renderImages() {
    const tiles = formImages.map(
      (image, index) => `
      <div class="image-tile" data-index="${index}">
        <img src="${escapeHtml(image.url)}" alt="Image ${index + 1}">
        ${index === 0 ? '<span class="main-badge">Main</span>' : ""}
        <div class="tile-actions">
          <button type="button" data-move="-1" aria-label="Move image left" ${index === 0 ? "disabled" : ""}>←</button>
          <button type="button" data-remove aria-label="Remove image">✕</button>
          <button type="button" data-move="1" aria-label="Move image right" ${index === formImages.length - 1 ? "disabled" : ""}>→</button>
        </div>
      </div>`
    );
    for (let i = 0; i < uploadsInProgress; i++) tiles.push('<div class="image-tile uploading">Uploading…</div>');
    imageManager.innerHTML = tiles.join("") || '<p class="muted">No images yet.</p>';
    el("image-input").disabled = formImages.length + uploadsInProgress >= MAX_IMAGES;
  }

  imageManager.addEventListener("click", (e) => {
    const tile = e.target.closest("[data-index]");
    if (!tile) return;
    const index = Number(tile.dataset.index);
    if (e.target.closest("[data-remove]")) {
      formImages.splice(index, 1);
    } else {
      const move = e.target.closest("[data-move]");
      if (!move || move.disabled) return;
      const target = index + Number(move.dataset.move);
      [formImages[index], formImages[target]] = [formImages[target], formImages[index]];
    }
    renderImages();
  });

  function imageProblem(file) {
    // Some systems report no type; the server checks the file contents in that case.
    if (file.type && !ALLOWED_TYPES.includes(file.type)) return "unsupported format (use JPEG, PNG, GIF or WEBP)";
    if (file.size === 0) return "the file is empty";
    if (file.size > MAX_IMAGE_BYTES) return "larger than 5 MB";
    return null;
  }

  el("image-input").addEventListener("change", async (e) => {
    clearAlert(formError);
    const files = Array.from(e.target.files);
    e.target.value = "";
    const room = MAX_IMAGES - formImages.length - uploadsInProgress;
    const problems = [];
    if (files.length > room) problems.push(`Only ${MAX_IMAGES} images are allowed; ${files.length - room} file(s) were skipped.`);
    const accepted = [];
    files.slice(0, Math.max(room, 0)).forEach((file) => {
      const problem = imageProblem(file);
      if (problem) problems.push(`${file.name}: ${problem}.`);
      else accepted.push(file);
    });

    uploadsInProgress += accepted.length;
    renderImages();
    // One request per image keeps each request under the server's size limit (FR14, FR57).
    for (const file of accepted) {
      const data = new FormData();
      data.append("image", file);
      try {
        formImages.push(await api("/api/admin/images", { method: "POST", form: data }));
      } catch (err) {
        problems.push(`${file.name}: ${err.message}`);
      }
      uploadsInProgress -= 1;
      renderImages();
    }
    if (problems.length) showAlert(formError, problems, "error", "Some images could not be added:");
  });

  // ---------- Add / edit form (FR8, FR10, FR13) ----------
  function buildSizeGrid(stock = {}) {
    sizeGrid.innerHTML = SIZES.map((size) => {
      const enabled = Object.prototype.hasOwnProperty.call(stock, size);
      return `
        <div class="size-stock">
          <label><input type="checkbox" data-size="${size}" ${enabled ? "checked" : ""}> ${size}</label>
          <input type="number" min="0" step="1" data-stock="${size}" aria-label="Stock for size ${size}"
                 value="${enabled ? stock[size] : ""}" placeholder="Qty" ${enabled ? "" : "disabled"}>
        </div>`;
    }).join("");
  }
  sizeGrid.addEventListener("change", (e) => {
    const size = e.target.dataset.size;
    if (!size) return;
    const qty = sizeGrid.querySelector(`[data-stock="${size}"]`);
    qty.disabled = !e.target.checked;
    if (e.target.checked) {
      if (qty.value === "") qty.value = "0";
      qty.focus();
      qty.select();
    }
  });

  el("description-input").addEventListener("input", (e) => {
    el("description-count").textContent = e.target.value.length;
  });

  function openForm(product) {
    editing = product;
    el("product-form").reset();
    clearAlert(formError);
    el("form-title").textContent = product ? "Edit Product" : "Add Product";
    el("name-input").value = product ? product.name : "";
    el("price-input").value = product ? Number(product.price).toFixed(2) : "";
    el("category-input").innerHTML = categoryOptions(product && product.category ? product.category.id : "", "Uncategorised");
    el("description-input").value = product ? product.description : "";
    el("description-count").textContent = el("description-input").value.length;
    const stock = {};
    (product ? product.sizes : []).forEach((s) => (stock[s.size] = s.stock));
    buildSizeGrid(stock);
    formImages = product ? product.images.map((image) => ({ ...image })) : [];
    uploadsInProgress = 0;
    renderImages();
    openModal(formModal);
    el("name-input").focus();
  }

  async function openEdit(id) {
    const p = await fetchProduct(id);
    if (p) openForm(p);
  }
  el("add-btn").addEventListener("click", () => openForm(null));

  /** Client-side mirror of the server rules in FR13; the server re-validates everything. */
  function collectForm() {
    const errors = [];
    const name = el("name-input").value.trim();
    if (!name) errors.push("Product name is required.");

    const price = el("price-input").value.trim();
    if (!/^\d+(\.\d{1,2})?$/.test(price) || Number(price) <= 0) {
      errors.push("Price must be a number greater than zero with at most two decimal places.");
    }

    const description = el("description-input").value.trim();
    if (description.length > 2000) errors.push("Description must be at most 2000 characters.");

    const stock = {};
    sizeGrid.querySelectorAll("[data-size]").forEach((box) => {
      if (!box.checked) return;
      const size = box.dataset.size;
      const raw = sizeGrid.querySelector(`[data-stock="${size}"]`).value.trim();
      if (!/^\d+$/.test(raw)) errors.push(`Stock for size ${size} must be a non-negative whole number.`);
      else stock[size] = Number(raw);
    });
    if (!sizeGrid.querySelector("[data-size]:checked")) errors.push("At least one size must be available.");

    if (uploadsInProgress) errors.push("Please wait until all images have finished uploading.");
    else if (!formImages.length) errors.push("At least one product image is required.");

    const categoryValue = el("category-input").value;
    return {
      errors,
      body: {
        name,
        price,
        description,
        category_id: categoryValue ? Number(categoryValue) : null,
        stock,
        image_ids: formImages.map((image) => image.id),
      },
    };
  }

  el("product-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    clearAlert(formError);
    const { errors, body } = collectForm();
    if (errors.length) {
      showAlert(formError, errors);
      return;
    }
    const saveBtn = el("save-btn");
    saveBtn.disabled = true;
    try {
      const saved = editing
        ? await api(`/api/admin/products/${editing.id}`, { method: "PUT", json: body })
        : await api("/api/admin/products", { method: "POST", json: body });
      closeModal(formModal);
      toast(editing ? `“${saved.name}” has been updated.` : `“${saved.name}” has been added.`, "success");
      loadProducts();
      loadCategories(); // product counts may have changed
    } catch (err) {
      showAlert(formError, err.errors);
      if (err.status === 404) loadProducts();
    } finally {
      saveBtn.disabled = false;
    }
  });

  // ---------- Delete (FR11) ----------
  async function askDelete(product) {
    if (!product) return;
    const confirmed = await confirmDialog({
      title: "Delete product?",
      message: `Are you sure you want to delete “${product.name}”? This action cannot be undone.`,
      confirmLabel: "Delete",
      danger: true,
    });
    if (!confirmed) return;
    try {
      const result = await api(`/api/admin/products/${product.id}`, { method: "DELETE" });
      toast(result.message, "success");
    } catch (err) {
      toast(err.message, "error");
    }
    loadProducts();
    loadCategories();
  }

  (async function init() {
    await loadCategories();
    loadProducts();
  })();
})();
