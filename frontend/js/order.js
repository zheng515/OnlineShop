/* Customer order detail and order confirmation (FR41, FR45, FR48). */

(function () {
  if (!requireRole("customer")) return;
  renderHeader("orders");

  const content = document.getElementById("order-content");
  const message = document.getElementById("order-message");
  const orderId = parsePositiveInt(queryParam("id") || "");

  function render(order) {
    document.title = `Order ${order.number} · OnlineShop`;
    content.innerHTML = `
      <div class="page-head">
        <h1>Order ${escapeHtml(order.number)}</h1>
        <div class="order-actions" id="order-actions">${OrderView.actionButtons(order)}</div>
      </div>
      <div class="layout-with-aside">
        <div class="card">${OrderView.items(order)}</div>
        <aside class="card card-body">
          ${OrderView.meta(order)}
          <h2>Status history</h2>
          ${OrderView.history(order)}
        </aside>
      </div>`;
    document.getElementById("order-actions").addEventListener("click", (e) => {
      const button = e.target.closest("[data-action]");
      if (button) cancel(order, button);
    });
  }

  async function cancel(order, button) {
    if (!(await OrderView.confirmAction(order, "cancelled"))) return;
    button.disabled = true;
    try {
      const updated = await api(`/api/orders/${order.id}/cancel`, { method: "POST" });
      toast(updated.message, "success");
      clearAlert(message);
      render(updated);
    } catch (err) {
      showAlert(message, err.errors);
      load();
    }
  }

  async function load() {
    if (!orderId) {
      content.innerHTML = "";
      showAlert(message, "No order was selected.");
      return;
    }
    try {
      render(await api(`/api/orders/${orderId}`));
    } catch (err) {
      content.innerHTML = `<div class="card"><div class="empty-state"><div class="icon">😕</div>
        <p>${escapeHtml(err.message)}</p><a class="btn" href="/orders.html">Back to My Orders</a></div></div>`;
    }
  }

  if (queryParam("placed")) {
    showAlert(
      message,
      ["Your order has been placed. No payment has been charged.", "You can follow its status here or under My Orders."],
      "success",
      "Thank you for your order!"
    );
    refreshCartCount();
    // Drop the flag so reloading the page does not show the confirmation again.
    history.replaceState(null, "", `/order.html?id=${orderId}`);
  }
  load();
})();
