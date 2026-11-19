/* Order details shared by the customer order page and the admin Order Management page (FR45, FR47). */

const OrderView = {
  ACTION_LABELS: { shipped: "Mark as Shipped", completed: "Mark as Completed", cancelled: "Cancel Order" },

  meta(order, { showCustomer = false } = {}) {
    return `
      <dl class="order-meta">
        <div><dt>Order number</dt><dd>${escapeHtml(order.number)}</dd></div>
        <div><dt>Placed on</dt><dd>${formatDateTime(order.created_at)}</dd></div>
        <div><dt>Status</dt><dd>${statusBadge(order)}</dd></div>
        <div><dt>Source</dt><dd>${order.source === "cart" ? "Shopping cart" : "Buy Now"}</dd></div>
        ${
          showCustomer
            ? `<div><dt>Customer</dt><dd>${escapeHtml(order.customer.display_name)}
                 <span class="muted">(${escapeHtml(order.customer.username)})</span></dd></div>`
            : ""
        }
        <div><dt>Total</dt><dd>${formatPrice(order.total)}</dd></div>
      </dl>`;
  },

  items(order) {
    return `
      <div class="table-wrap">
        <table class="table">
          <thead>
            <tr><th>Image</th><th>Product</th><th>Unit price</th><th class="stock-cell">Qty</th><th class="text-right">Subtotal</th></tr>
          </thead>
          <tbody>
            ${order.items
              .map(
                (item) => `
              <tr>
                <td>${productImage(item.image_url, item.name)}</td>
                <td><div class="item-name">${escapeHtml(item.name)}</div><div class="item-size">Size: ${escapeHtml(item.size)}</div></td>
                <td class="nowrap">${formatPrice(item.unit_price)}</td>
                <td class="stock-cell">${item.quantity}</td>
                <td class="nowrap text-right"><strong>${formatPrice(item.subtotal)}</strong></td>
              </tr>`
              )
              .join("")}
          </tbody>
        </table>
      </div>`;
  },

  history(order) {
    const who = (event) => (event.actor_role === "admin" ? `administrator ${event.actor_name}` : event.actor_name);
    return `
      <ul class="timeline">
        ${order.history
          .map(
            (event) => `
          <li><strong>${escapeHtml(event.status_label)}</strong> by ${escapeHtml(who(event))}
            <div class="when">${formatDateTime(event.created_at)}</div></li>`
          )
          .join("")}
      </ul>`;
  },

  actionButtons(order) {
    return order.allowed_actions
      .map(
        (action) =>
          `<button type="button" class="btn ${action === "cancelled" ? "btn-danger" : ""}" data-action="${action}">
             ${this.ACTION_LABELS[action]}</button>`
      )
      .join("");
  },

  /** Ask before cancelling (FR48); other status changes need no confirmation. */
  confirmAction(order, action) {
    if (action !== "cancelled") return Promise.resolve(true);
    return confirmDialog({
      title: `Cancel order ${order.number}?`,
      message: "The items will be returned to stock. This cannot be undone.",
      confirmLabel: "Cancel Order",
      cancelLabel: "Keep Order",
      danger: true,
    });
  },
};
