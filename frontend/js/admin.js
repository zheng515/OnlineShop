/* Product Management page (FR7-FR14). */

(function () {
  if (!requireRole("admin")) return;
  renderHeader("products");

  const ALLOWED_TYPES = ["image/jpeg", "image/png", "image/gif", "image/webp"];
  const MAX_IMAGE_BYTES = 5 * 1024 * 1024;

  const rows = document.getElementById("product-rows");
  const listMessage = document.getElementById("list-message");
  const searchForm = document.getElementById("search-form");
  const searchInput = document.getElementById("search-input");
  const clearSearchBtn = document.getElementById("clear-search");

  const formModal = document.getElementById("form-modal");
  const form = document.getElementById("product-form");
  const formError = document.getElementById("form-error");
  const imageInput = document.getElementById("image-input");
  const imagePreview = document.getElementById("image-preview");
  const nameInput = document.getElementById("name-input");
  const priceInput = document.getElementById("price-input");
  const sizeGrid = document.getElementById("size-stock-grid");
  const saveBtn = document.getElementById("save-btn");

  const detailModal = document.getElementById("detail-modal");
  const deleteModal = document.getElementById("delete-modal");

  let products = [];
  let currentQuery = "";
  let editing = null; // product being edited, or null when adding
  let detailProduct = null;
  let deleting = null;

  document.querySelectorAll(".currency").forEach((el) => (el.textContent = CURRENCY));

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
    if (e.key === "Escape") document.querySelectorAll(".modal-backdrop").forEach(closeModal);
  });

  // ---------- List & search ----------
  function stockCell(product, size) {
    const entry = product.sizes.find((s) => s.size === size);
    if (!entry) return `<td class="stock-cell stock-na" title="Size not offered">—</td>`;
    const cls = entry.stock === 0 ? "stock-zero" : "";
    return `<td class="stock-cell ${cls}">${entry.stock}</td>`;
  }

  function renderList() {
    if (!products.length) {
      rows.innerHTML = `<tr><td colspan="8"><div class="empty-state">
        <div class="icon">📦</div>
        ${currentQuery ? `<p>No products match “${escapeHtml(currentQuery)}”.</p>` : "<p>No products yet. Add your first product.</p>"}
      </div></td></tr>`;
      return;
    }
    rows.innerHTML = products
      .map(
        (p) => `
        <tr>
          <td>${productImage(p.image_url, p.name)}</td>
          <td class="item-name">${escapeHtml(p.name)}</td>
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
    try {
      const data = await api(`/api/admin/products?q=${encodeURIComponent(currentQuery)}`);
      products = data.products;
      clearAlert(listMessage);
      if (currentQuery) {
        showAlert(
          listMessage,
          products.length
            ? `Found ${products.length} product(s) matching “${currentQuery}”.`
            : `No products found matching “${currentQuery}”. Try a different keyword.`,
          products.length ? "info" : "warning"
        );
      }
      renderList();
    } catch (err) {
      rows.innerHTML = "";
      showAlert(listMessage, err.errors);
    }
  }

  searchForm.addEventListener("submit", (e) => {
    e.preventDefault();
    currentQuery = searchInput.value.trim();
    clearSearchBtn.classList.toggle("hidden", !currentQuery);
    loadProducts();
  });
  clearSearchBtn.addEventListener("click", () => {
    searchInput.value = "";
    currentQuery = "";
    clearSearchBtn.classList.add("hidden");
    loadProducts();
  });

  rows.addEventListener("click", async (e) => {
    const button = e.target.closest("button[data-action]");
    if (!button) return;
    const id = Number(button.dataset.id);
    const action = button.dataset.action;
    if (action === "view") return showDetails(id);
    if (action === "edit") return openEdit(id);
    if (action === "delete") return askDelete(products.find((p) => p.id === id));
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
    document.getElementById("detail-body").innerHTML = `
      <img class="detail-image" src="${escapeHtml(p.image_url)}" alt="${escapeHtml(p.name)}">
      <dl class="detail-list">
        <dt>Name</dt><dd>${escapeHtml(p.name)}</dd>
        <dt>Price</dt><dd>${formatPrice(p.price)}</dd>
        <dt>Available sizes</dt><dd>${p.sizes.map((s) => s.size).join(", ") || "—"}</dd>
        <dt>Stock by size</dt><dd>${sizes}</dd>
        <dt>Total stock</dt><dd>${p.total_stock}</dd>
        <dt>Last updated</dt><dd>${new Date(p.updated_at).toLocaleString()}</dd>
      </dl>`;
    openModal(detailModal);
  }
  document.getElementById("detail-edit-btn").addEventListener("click", () => {
    closeModal(detailModal);
    if (detailProduct) openEdit(detailProduct.id);
  });

  // ---------- Add / edit form (FR8, FR10, FR13, FR14) ----------
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

  function setPreview(url) {
    imagePreview.innerHTML = url ? `<img src="${escapeHtml(url)}" alt="Preview">` : "No image";
  }

  function validateImageFile(file) {
    // Some systems report no type; the server checks the file contents in that case.
    if (file.type && !ALLOWED_TYPES.includes(file.type)) return "Unsupported image format. Please upload a JPEG, PNG, GIF or WEBP image.";
    if (file.size === 0) return "The selected image file is empty.";
    if (file.size > MAX_IMAGE_BYTES) return "The image is too large. The maximum size is 5 MB.";
    return null;
  }

  imageInput.addEventListener("change", () => {
    clearAlert(formError);
    const file = imageInput.files[0];
    if (!file) {
      setPreview(editing ? editing.image_url : null);
      return;
    }
    const problem = validateImageFile(file);
    if (problem) {
      showAlert(formError, problem);
      imageInput.value = "";
      setPreview(editing ? editing.image_url : null);
      return;
    }
    setPreview(URL.createObjectURL(file));
  });

  function openForm(product) {
    editing = product;
    form.reset();
    clearAlert(formError);
    document.getElementById("form-title").textContent = product ? "Edit Product" : "Add Product";
    document.getElementById("image-hint").textContent = product
      ? "Choose a file only if you want to replace the current image. JPEG, PNG, GIF or WEBP, up to 5 MB."
      : "JPEG, PNG, GIF or WEBP, up to 5 MB.";
    nameInput.value = product ? product.name : "";
    priceInput.value = product ? Number(product.price).toFixed(2) : "";
    const stock = {};
    (product ? product.sizes : []).forEach((s) => (stock[s.size] = s.stock));
    buildSizeGrid(stock);
    setPreview(product ? product.image_url : null);
    openModal(formModal);
    nameInput.focus();
  }

  async function openEdit(id) {
    const p = await fetchProduct(id);
    if (p) openForm(p);
  }
  document.getElementById("add-btn").addEventListener("click", () => openForm(null));

  /** Client-side mirror of the server rules in FR13; the server re-validates everything. */
  function collectForm() {
    const errors = [];
    const name = nameInput.value.trim();
    if (!name) errors.push("Product name is required.");

    const priceText = priceInput.value.trim();
    if (!/^\d+(\.\d{1,2})?$/.test(priceText) || Number(priceText) <= 0) {
      errors.push("Price must be a number greater than zero with at most two decimal places.");
    }

    const stock = {};
    sizeGrid.querySelectorAll("[data-size]").forEach((box) => {
      if (!box.checked) return;
      const size = box.dataset.size;
      const raw = sizeGrid.querySelector(`[data-stock="${size}"]`).value.trim();
      if (!/^\d+$/.test(raw)) {
        errors.push(`Stock for size ${size} must be a non-negative whole number.`);
      } else {
        stock[size] = Number(raw);
      }
    });
    const anyChecked = sizeGrid.querySelector("[data-size]:checked");
    if (!anyChecked) errors.push("At least one size must be available.");

    const file = imageInput.files[0];
    if (!file && !editing) errors.push("Product image is required.");
    if (file) {
      const problem = validateImageFile(file);
      if (problem) errors.push(problem);
    }
    return { errors, name, price: priceText, stock, file };
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    clearAlert(formError);
    const { errors, name, price, stock, file } = collectForm();
    if (errors.length) {
      showAlert(formError, errors);
      return;
    }

    const data = new FormData();
    data.append("name", name);
    data.append("price", price);
    data.append("stock", JSON.stringify(stock));
    if (file) data.append("image", file);

    saveBtn.disabled = true;
    try {
      const saved = editing
        ? await api(`/api/admin/products/${editing.id}`, { method: "PUT", form: data })
        : await api("/api/admin/products", { method: "POST", form: data });
      closeModal(formModal);
      toast(editing ? `“${saved.name}” has been updated.` : `“${saved.name}” has been added.`, "success");
      loadProducts();
    } catch (err) {
      showAlert(formError, err.errors);
      if (err.status === 404) loadProducts();
    } finally {
      saveBtn.disabled = false;
    }
  });

  // ---------- Delete (FR11) ----------
  function askDelete(product) {
    if (!product) return;
    deleting = product;
    document.getElementById("delete-text").innerHTML =
      `Are you sure you want to delete <strong>${escapeHtml(product.name)}</strong>?`;
    openModal(deleteModal);
  }
  document.getElementById("confirm-delete-btn").addEventListener("click", async (e) => {
    if (!deleting) return;
    e.target.disabled = true;
    try {
      const result = await api(`/api/admin/products/${deleting.id}`, { method: "DELETE" });
      toast(result.message, "success");
    } catch (err) {
      toast(err.message, "error");
    } finally {
      e.target.disabled = false;
      deleting = null;
      closeModal(deleteModal);
      loadProducts();
    }
  });

  loadProducts();
})();
