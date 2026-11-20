/* Order details shared by the customer order page and the admin Order Management page (FR45, FR47, FR83, FR107, FR108). */

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
        <div><dt>Items</dt><dd>${formatPrice(order.items_total)}</dd></div>
        <div><dt>Delivery</dt><dd id="order-delivery-fee">${
          !order.delivery ? "—" : order.shipping_fee ? formatPrice(order.shipping_fee) : "Free"
        }</dd></div>
        <div><dt>Total</dt><dd>${formatPrice(order.total)}</dd></div>
      </dl>`;
  },

  /** Where and how the order is delivered, and the shipping details once shipped. */
  delivery(order) {
    const { carrier, tracking_number: tracking } = order.shipping;
    const shipped =
      carrier || tracking
        ? `<p id="shipping-details"><strong>Shipped</strong>${carrier ? ` with ${escapeHtml(carrier)}` : ""}${
            tracking ? `<br>Tracking number: <span class="ref">${escapeHtml(tracking)}</span>` : ""
          }</p>`
        : "";
    if (!order.delivery) {
      return `<h2>Delivery</h2>
        <p class="muted">No delivery details were recorded for this order: it was placed before delivery addresses
          were introduced.</p>${shipped}`;
    }
    return `<h2>Delivery</h2>
      <div id="order-delivery">
        <p>${AddressForm.lines(order.delivery.address)}</p>
        <p><span class="muted">Method:</span> ${escapeHtml(order.delivery.method)}</p>
        ${shipped}
      </div>`;
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
    const who = (event) => {
      if (event.actor_role === "admin") return ` by administrator ${event.actor_name}`;
      if (event.actor_role === "system") return ` (${event.actor_name})`;
      return ` by ${event.actor_name}`;
    };
    return `
      <ul class="timeline">
        ${order.history
          .map(
            (event) => `
          <li><strong>${escapeHtml(event.status_label)}</strong>${escapeHtml(who(event))}
            <div class="when">${formatDateTime(event.created_at)}</div></li>`
          )
          .join("")}
      </ul>`;
  },

  /** Payment attempts and refunds (FR83). */
  payments(order) {
    if (!order.payments.length && !order.refunds.length) {
      return '<p class="muted">No payments for this order.</p>';
    }
    const refunds = order.refunds
      .map(
        (r) => `
        <li><strong>Refund ${formatPrice(r.amount)}</strong> · ${escapeHtml(r.status_label)} · ${escapeHtml(r.reason)}
          <div class="when">${formatDateTime(r.updated_at)}</div>
          ${r.failure_reason ? `<div class="item-issue">⚠ ${escapeHtml(r.failure_reason)}</div>` : ""}
          ${r.reference ? `<div class="ref">${escapeHtml(r.reference)}</div>` : ""}</li>`
      )
      .join("");
    const payments = order.payments
      .map(
        (p) => `
        <li><strong>Payment ${formatPrice(p.amount)}</strong> · ${escapeHtml(p.status_label)}
          <div class="when">${p.paid_at ? `Paid ${formatDateTime(p.paid_at)}` : `Started ${formatDateTime(p.created_at)}`}</div>
          ${p.failure_reason ? `<div class="item-issue">${escapeHtml(p.failure_reason)}</div>` : ""}
          <div class="ref">${escapeHtml(p.provider)} · ${escapeHtml(p.reference)}</div></li>`
      )
      .join("");
    return `<ul class="payment-list">${refunds}${payments}</ul>`;
  },

  /** "12:34" from seconds. */
  timeLeft(seconds) {
    return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
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
    const paid = order.payments.some((p) => p.status === "succeeded");
    return confirmDialog({
      title: `Cancel order ${order.number}?`,
      message: paid
        ? `The items will be returned to stock and ${formatPrice(order.total)} will be refunded. This cannot be undone.`
        : "The items will be returned to stock. This cannot be undone.",
      confirmLabel: "Cancel Order",
      cancelLabel: "Keep Order",
      danger: true,
    });
  },
};
