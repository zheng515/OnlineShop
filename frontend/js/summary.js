/* Order summary shared by the Checkout and Payment pages, for cart and Buy Now alike (FR28). */

const OrderSummary = {
  /** Read the checkout request (cart or Buy Now) from the page URL. Returns null if malformed. */
  requestFromUrl() {
    const source = queryParam("source") || "cart";
    if (source === "cart") return { source: "cart" };
    if (source !== "buy_now") return null;
    const productId = parsePositiveInt(queryParam("product_id") || "");
    const quantity = parsePositiveInt(queryParam("quantity") || "");
    const size = queryParam("size");
    if (!productId || !quantity || !SIZES.includes(size)) return null;
    return { source: "buy_now", product_id: productId, size, quantity };
  },

  queryString(request) {
    return new URLSearchParams(request).toString();
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
    return `
      <div class="row"><span class="muted">Items</span><span>${summary.item_count}</span></div>
      <div class="row total"><span>Total payable</span><span>${formatPrice(summary.total)}</span></div>`;
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
