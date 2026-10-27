/* Shopping cart (FR21-FR26, FR30, FR34). Prices shown are always the current ones from the server. */

(function () {
  if (!requireRole("customer")) return;
  renderHeader("cart");

  const content = document.getElementById("cart-content");
  const message = document.getElementById("cart-message");
  let cart = null;

  function itemRow(item) {
    const unavailable = item.status === "unavailable";
    const maxAttr = item.available_stock > 0 ? `max="${item.available_stock}"` : "";
    const productLink = unavailable
      ? escapeHtml(item.name)
      : `<a href="/product.html?id=${item.product_id}">${escapeHtml(item.name)}</a>`;
    return `
      <tr class="${item.status === "ok" ? "" : "has-issue"}" data-id="${item.id}">
        <td>${productImage(item.image_url, item.name)}</td>
        <td>
          <div class="item-name">${productLink}</div>
          <div class="item-size">Size: ${escapeHtml(item.size)}</div>
          ${item.message ? `<div class="item-issue">⚠ ${escapeHtml(item.message)}</div>` : ""}
        </td>
        <td class="nowrap hide-sm">${formatPrice(item.unit_price)}</td>
        <td>
          <div class="qty-control">
            <button type="button" data-step="-1" aria-label="Decrease quantity" ${unavailable || item.quantity <= 1 ? "disabled" : ""}>−</button>
            <input type="number" min="1" step="1" ${maxAttr} value="${item.quantity}" aria-label="Quantity" ${unavailable ? "disabled" : ""}>
            <button type="button" data-step="1" aria-label="Increase quantity" ${unavailable || item.quantity >= item.available_stock ? "disabled" : ""}>+</button>
          </div>
        </td>
        <td class="nowrap text-right"><strong>${formatPrice(item.subtotal)}</strong></td>
        <td class="text-right"><button type="button" class="btn btn-ghost btn-sm" data-remove aria-label="Remove item">✕ Remove</button></td>
      </tr>`;
  }

  function render() {
    setCartCount(cart.item_count);
    if (cart.empty) {
      clearAlert(message);
      content.innerHTML = `
        <div class="card"><div class="empty-state">
          <div class="icon">🛒</div>
          <p><strong>Your shopping cart is empty.</strong></p>
          <p>Browse our products and add something you like.</p>
          <a class="btn" href="/shop.html">Browse products</a>
        </div></div>`;
      return;
    }

    if (cart.valid) clearAlert(message);
    else showAlert(message, cart.issues, "warning", "Some items need your attention before you can check out:");

    content.innerHTML = `
      <div class="layout-with-aside">
        <div class="card">
          <div class="table-wrap">
            <table class="table">
              <thead>
                <tr><th>Image</th><th>Product</th><th class="hide-sm">Unit price</th><th>Quantity</th><th class="text-right">Subtotal</th><th></th></tr>
              </thead>
              <tbody id="cart-rows">${cart.items.map(itemRow).join("")}</tbody>
            </table>
          </div>
        </div>
        <aside class="card card-body summary-box">
          <h2>Order Summary</h2>
          <div class="row"><span class="muted">Items</span><span>${cart.item_count}</span></div>
          <div class="row total"><span>Total</span><span>${formatPrice(cart.total)}</span></div>
          <button type="button" class="btn btn-lg btn-block" id="checkout-btn" ${cart.valid ? "" : "disabled"}>
            Proceed to Checkout
          </button>
          ${cart.valid ? "" : '<p class="field-hint">Resolve the highlighted items to continue.</p>'}
        </aside>
      </div>`;

    document.getElementById("cart-rows").addEventListener("click", onRowClick);
    document.getElementById("cart-rows").addEventListener("change", onQuantityChange);
    document.getElementById("checkout-btn").addEventListener("click", proceedToCheckout);
  }

  function itemById(id) {
    return cart.items.find((item) => String(item.id) === String(id));
  }

  async function onRowClick(e) {
    const row = e.target.closest("tr[data-id]");
    if (!row) return;
    if (e.target.closest("[data-remove]")) return removeItem(row.dataset.id);
    const stepButton = e.target.closest("[data-step]");
    if (stepButton) {
      const item = itemById(row.dataset.id);
      updateQuantity(item, item.quantity + Number(stepButton.dataset.step));
    }
  }

  function onQuantityChange(e) {
    if (e.target.type !== "number") return;
    const row = e.target.closest("tr[data-id]");
    const item = itemById(row.dataset.id);
    const quantity = parsePositiveInt(e.target.value);
    if (quantity === null) {
      toast("Quantity must be a positive whole number.", "error");
      e.target.value = item.quantity;
      return;
    }
    updateQuantity(item, quantity);
  }

  async function updateQuantity(item, quantity) {
    if (quantity < 1) return;
    if (quantity > item.available_stock) {
      toast(`Only ${item.available_stock} available in size ${item.size} of “${item.name}”.`, "error");
      render();
      return;
    }
    try {
      cart = await api(`/api/cart/items/${item.id}`, { method: "PATCH", json: { quantity } });
      render();
    } catch (err) {
      toast(err.message, "error");
      await load();
    }
  }

  async function removeItem(id) {
    const item = itemById(id);
    try {
      cart = await api(`/api/cart/items/${id}`, { method: "DELETE" });
      toast(`Removed “${item.name}” (size ${item.size}) from your cart.`, "success");
      render();
    } catch (err) {
      toast(err.message, "error");
      await load();
    }
  }

  async function proceedToCheckout() {
    // Refresh first so stock or price changes made meanwhile are caught here.
    await load();
    if (cart && cart.valid) window.location.href = "/checkout.html?source=cart";
  }

  async function load() {
    try {
      cart = await api("/api/cart");
      render();
    } catch (err) {
      content.innerHTML = "";
      showAlert(message, err.errors);
    }
  }

  load();
})();
