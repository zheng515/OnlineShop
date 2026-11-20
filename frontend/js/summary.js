/* Order summary shared by the Checkout and Payment pages, for cart and Buy Now alike (FR28, FR105, FR106). */

const OrderSummary = {
  /** Read the checkout request (cart or Buy Now) from the page URL. Returns null if malformed. */
  requestFromUrl() {
    const source = queryParam("source") || "cart";
    // The delivery choice is kept in the URL between Checkout and Payment (FR105).
    const delivery = {};
    const addressId = parsePositiveInt(queryParam("address_id") || "");
    const methodId = parsePositiveInt(queryParam("shipping_method_id") || "");
    if (addressId) delivery.address_id = addressId;
    if (methodId) delivery.shipping_method_id = methodId;
    if (source === "cart") return { source: "cart", ...delivery };
    if (source !== "buy_now") return null;
    const productId = parsePositiveInt(queryParam("product_id") || "");
    const quantity = parsePositiveInt(queryParam("quantity") || "");
    const size = queryParam("size");
    if (!productId || !quantity || !SIZES.includes(size)) return null;
    return { source: "buy_now", product_id: productId, size, quantity, ...delivery };
  },

  queryString(request) {
    const params = Object.entries(request).filter(([, value]) => value !== undefined && value !== null);
    return new URLSearchParams(params).toString();
  },

  /** Where "back" goes from checkout: the cart, or the product page with the selection kept (FR31). */
  backLink(request) {
    if (request.source === "cart") return { href: "/cart.html", label: "Back to Cart" };
    const params = new URLSearchParams({ id: request.product_id, size: request.size, quantity: request.quantity });
    return { href: `/product.html?${params}`, label: "Back to Product" };
  },

  async fetch(request) {
    return api("/api/checkout", { method: "POST", json: request });
  },

  itemsTable(summary) {
    const rows = summary.items
      .map(
        (item) => `
        <tr class="${item.status === "ok" ? "" : "has-issue"}">
          <td>${productImage(item.image_url, item.name)}</td>
          <td>
            <div class="item-name">${escapeHtml(item.name)}</div>
            <div class="item-size">Size: ${escapeHtml(item.size)}</div>
            ${item.message ? `<div class="item-issue">⚠ ${escapeHtml(item.message)}</div>` : ""}
          </td>
          <td class="nowrap">${formatPrice(item.unit_price)}</td>
          <td class="stock-cell">${item.quantity}</td>
          <td class="nowrap text-right"><strong>${formatPrice(item.subtotal)}</strong></td>
        </tr>`
      )
      .join("");
    return `
      <div class="table-wrap">
        <table class="table">
          <thead>
            <tr><th>Image</th><th>Product</th><th>Unit price</th><th class="stock-cell">Qty</th><th class="text-right">Subtotal</th></tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  },

  totals(summary) {
    const method = summary.delivery && summary.delivery.method;
    const fee = !method ? "—" : summary.shipping_fee ? formatPrice(summary.shipping_fee) : "Free";
    return `
      <div class="row"><span class="muted">Items (${summary.item_count})</span><span>${formatPrice(summary.items_total)}</span></div>
      <div class="row"><span class="muted">Delivery${method ? ` · ${escapeHtml(method.name)}` : ""}</span>
        <span id="delivery-fee">${fee}</span></div>
      <div class="row total"><span>Total payable</span><span id="total-payable">${formatPrice(summary.total)}</span></div>`;
  },

  /** A delivery method's fee for this order, with how much more buys free delivery (FR103, FR105). */
  methodFee(method) {
    if (!method.fee) return "<strong>Free</strong>";
    const free = method.amount_to_free
      ? `<span class="field-hint">Free if you add ${formatPrice(method.amount_to_free)} more</span>`
      : "";
    return `<strong>${formatPrice(method.fee)}</strong>${free}`;
  },

  /** The chosen address and method, for the Payment page (FR32). */
  deliveryBox(summary, changeHref) {
    const { address, method } = summary.delivery;
    return `
      <div class="card card-body mb-lg delivery-box">
        <div class="section-head"><h2>Delivery</h2><a href="${changeHref}" id="change-delivery">Change</a></div>
        <div class="delivery-columns">
          <div><h3>Address</h3><p id="delivery-address">${AddressForm.lines(address)}</p></div>
          <div><h3>Method</h3><p id="delivery-method">${escapeHtml(method.name)}${
            method.description ? `<br><span class="muted">${escapeHtml(method.description)}</span>` : ""
          }<br>${this.methodFee(method)}</p></div>
        </div>
      </div>`;
  },

  issuesAlert(container, summary) {
    if (summary.valid) {
      clearAlert(container);
      return;
    }
    if (summary.empty) showAlert(container, summary.issues, "error");
    else showAlert(container, summary.issues, "error", "Please fix the following before continuing:");
  },
};
