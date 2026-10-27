/* Product detail page: size selection, add to cart and Buy Now (FR17-FR20, FR27, FR33). */

(function () {
  if (!requireRole("customer")) return;
  renderHeader("shop");

  const container = document.getElementById("product-detail");
  const pageMessage = document.getElementById("page-message");
  const productId = parsePositiveInt(queryParam("id") || "");

  let product = null;
  let selectedSize = null;

  // Returning from checkout restores the previous selection (FR31).
  const initialSize = queryParam("size");
  const initialQty = parsePositiveInt(queryParam("quantity") || "") || 1;

  function sizeInfo(size) {
    return product.sizes.find((s) => s.size === size) || null;
  }

  function sizeButton(size) {
    const info = sizeInfo(size);
    let note;
    let disabled = false;
    let cls = "";
    if (!info) {
      note = "Not offered";
      disabled = true;
      cls = "not-offered";
    } else if (info.stock === 0) {
      note = "Out of stock";
      disabled = true;
    } else {
      note = `${info.stock} in stock`;
    }
    if (size === selectedSize) cls += " selected";
    return `<button type="button" class="size-option ${cls}" data-size="${size}" ${disabled ? "disabled" : ""}
              aria-pressed="${size === selectedSize}">
              <strong>${size}</strong><small>${note}</small>
            </button>`;
  }

  function render(quantity) {
    const anyInStock = product.sizes.some((s) => s.stock > 0);
    container.innerHTML = `
      <div class="detail">
        <div class="card gallery"><img src="${escapeHtml(product.image_url)}" alt="${escapeHtml(product.name)}"></div>
        <div>
          <h1>${escapeHtml(product.name)}</h1>
          <div class="price">${formatPrice(product.price)}</div>

          <label>Size</label>
          <div class="size-options" id="size-options">${SIZES.map(sizeButton).join("")}</div>

          <label for="qty-input">Quantity</label>
          <div class="qty-control">
            <button type="button" id="qty-minus" aria-label="Decrease quantity">−</button>
            <input type="number" id="qty-input" min="1" step="1" value="${quantity}">
            <button type="button" id="qty-plus" aria-label="Increase quantity">+</button>
          </div>
          <div class="field-hint" id="qty-hint"></div>

          <div id="action-message" class="hidden" role="alert" style="margin-top: 1rem"></div>

          <div class="purchase-actions">
            <button type="button" class="btn btn-secondary btn-lg" id="add-cart-btn">Add to Cart</button>
            <button type="button" class="btn btn-lg" id="buy-now-btn">Buy Now</button>
          </div>
          ${anyInStock ? "" : '<div class="alert alert-warning" style="margin-top:1rem">This product is currently out of stock in all sizes.</div>'}
        </div>
      </div>`;
    bindEvents();
    updateControls();
  }

  const el = (id) => document.getElementById(id);

  function stockForSelection() {
    const info = selectedSize ? sizeInfo(selectedSize) : null;
    return info ? info.stock : 0;
  }

  function updateControls() {
    const stock = stockForSelection();
    const qty = parsePositiveInt(el("qty-input").value);
    el("qty-hint").textContent = selectedSize
      ? `${stock} available in size ${selectedSize}.`
      : "Please select a size first.";
    el("qty-minus").disabled = !qty || qty <= 1;
    el("qty-plus").disabled = !selectedSize || (qty !== null && qty >= stock);
    const canBuy = Boolean(selectedSize) && stock > 0;
    el("add-cart-btn").disabled = !canBuy;
    el("buy-now-btn").disabled = !canBuy;
  }

  function bindEvents() {
    el("size-options").addEventListener("click", (e) => {
      const button = e.target.closest(".size-option");
      if (!button || button.disabled) return;
      selectedSize = button.dataset.size;
      document.querySelectorAll(".size-option").forEach((b) => {
        const on = b.dataset.size === selectedSize;
        b.classList.toggle("selected", on);
        b.setAttribute("aria-pressed", on);
      });
      const qty = parsePositiveInt(el("qty-input").value);
      if (qty && qty > stockForSelection()) el("qty-input").value = stockForSelection();
      clearAlert(el("action-message"));
      updateControls();
    });
    el("qty-minus").addEventListener("click", () => stepQuantity(-1));
    el("qty-plus").addEventListener("click", () => stepQuantity(1));
    el("qty-input").addEventListener("input", updateControls);
    el("add-cart-btn").addEventListener("click", addToCart);
    el("buy-now-btn").addEventListener("click", buyNow);
  }

  function stepQuantity(delta) {
    const current = parsePositiveInt(el("qty-input").value) || 1;
    const max = stockForSelection() || 1;
    el("qty-input").value = Math.min(Math.max(1, current + delta), max);
    updateControls();
  }

  /** Returns the requested quantity, or null after showing why the selection is invalid. */
  function validateSelection() {
    const box = el("action-message");
    if (!selectedSize) {
      showAlert(box, "Please select a size.");
      return null;
    }
    const stock = stockForSelection();
    if (stock === 0) {
      showAlert(box, `Size ${selectedSize} is out of stock.`);
      return null;
    }
    const qty = parsePositiveInt(el("qty-input").value);
    if (qty === null) {
      showAlert(box, "Quantity must be a positive whole number.");
      return null;
    }
    if (qty > stock) {
      showAlert(box, `Only ${stock} available in size ${selectedSize}.`);
      return null;
    }
    clearAlert(box);
    return qty;
  }

  async function addToCart() {
    const quantity = validateSelection();
    if (quantity === null) return;
    const button = el("add-cart-btn");
    button.disabled = true;
    try {
      const cart = await api("/api/cart/items", {
        method: "POST",
        json: { product_id: product.id, size: selectedSize, quantity },
      });
      setCartCount(cart.item_count);
      showAlert(el("action-message"), [cart.message], "success");
      el("action-message").insertAdjacentHTML("beforeend", ' <a href="/cart.html">View cart &rarr;</a>');
      toast("Added to cart", "success");
    } catch (err) {
      // Stock may have changed since the page was loaded: refresh before explaining.
      if (err.status === 404 || err.status === 409) await load(parsePositiveInt(el("qty-input").value) || 1);
      if (el("action-message")) showAlert(el("action-message"), err.errors);
    } finally {
      if (product) updateControls();
    }
  }

  function buyNow() {
    const quantity = validateSelection();
    if (quantity === null) return;
    const params = new URLSearchParams({
      source: "buy_now",
      product_id: product.id,
      size: selectedSize,
      quantity,
    });
    window.location.href = `/checkout.html?${params}`;
  }

  async function load(quantity) {
    if (!productId) {
      container.innerHTML = "";
      showAlert(pageMessage, "No product was selected.");
      return;
    }
    try {
      product = await api(`/api/products/${productId}`);
    } catch (err) {
      product = null;
      container.innerHTML = `<div class="empty-state"><div class="icon">😕</div><p>${escapeHtml(err.message)}</p>
        <a class="btn" href="/shop.html">Browse products</a></div>`;
      return;
    }
    document.title = `${product.name} · OnlineShop`;
    const info = selectedSize ? sizeInfo(selectedSize) : null;
    if (!info || info.stock === 0) selectedSize = null;
    render(quantity);
  }

  (async function init() {
    await load(initialQty);
    if (product && initialSize) {
      const info = sizeInfo(initialSize);
      if (info && info.stock > 0) {
        selectedSize = initialSize;
        render(Math.min(initialQty, info.stock));
      }
    }
  })();
})();
