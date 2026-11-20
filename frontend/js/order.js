/* Customer order detail: payment, result after paying, cancellation (FR45, FR48, FR78-FR80, FR86). */

(function () {
  if (!requireRole("customer")) return;
  renderHeader("orders");

  const content = document.getElementById("order-content");
  const message = document.getElementById("order-message");
  const orderId = parsePositiveInt(queryParam("id") || "");
  const returned = queryParam("payment"); // "returned" or "cancelled" when coming back from the provider
  let countdown = null;
  let polls = 0;

  function payBox(order) {
    if (order.status !== "awaiting_payment") return "";
    return `
      <div class="card card-body mb-lg">
        <div class="pay-box">
          <div>
            <strong>Awaiting payment.</strong> Pay within
            <span class="countdown" id="countdown">${OrderView.timeLeft(order.seconds_left)}</span>
            to keep your items; after that the order is cancelled automatically.
          </div>
          <button type="button" class="btn btn-lg" id="pay-btn">Pay now · ${formatPrice(order.total)}</button>
        </div>
      </div>`;
  }

  function render(order) {
    document.title = `Order ${order.number} · OnlineShop`;
    content.innerHTML = `
      <div class="page-head">
        <h1>Order ${escapeHtml(order.number)}</h1>
        <div class="order-actions" id="order-actions">${OrderView.actionButtons(order)}</div>
      </div>
      ${payBox(order)}
      <div class="layout-with-aside">
        <div class="card">${OrderView.items(order)}</div>
        <aside class="card card-body">
          ${OrderView.meta(order)}
          ${OrderView.delivery(order)}
          <h2 class="mt-md">Payment</h2>
          ${OrderView.payments(order)}
          <h2 class="mt-md">Status history</h2>
          ${OrderView.history(order)}
        </aside>
      </div>`;
    document.getElementById("order-actions").addEventListener("click", (e) => {
      const button = e.target.closest("[data-action]");
      if (button) cancel(order, button);
    });
    const payButton = document.getElementById("pay-btn");
    if (payButton) payButton.addEventListener("click", () => payNow(payButton));
    startCountdown(order);
  }

  function startCountdown(order) {
    clearInterval(countdown);
    if (order.status !== "awaiting_payment") return;
    let seconds = order.seconds_left;
    countdown = setInterval(() => {
      seconds = Math.max(0, seconds - 1);
      const label = document.getElementById("countdown");
      if (label) label.textContent = OrderView.timeLeft(seconds);
      if (seconds === 0) {
        clearInterval(countdown);
        load(); // the server cancels the overdue order when it is opened (FR79)
      }
    }, 1000);
  }

  async function payNow(button) {
    button.disabled = true;
    try {
      const { payment_url } = await api(`/api/orders/${orderId}/pay`, { method: "POST" });
      window.location.assign(payment_url);
    } catch (err) {
      showAlert(message, err.errors);
      load();
    }
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

  /** After returning from the provider, say what happened (FR78). */
  function explainPayment(order) {
    const latest = order.payments[0];
    if (order.status === "paid") {
      showAlert(message, ["Your payment has been received."], "success", "Thank you for your order!");
    } else if (returned === "cancelled" && order.status === "awaiting_payment") {
      showAlert(message, "You left the payment page without paying. You can pay with Pay now before the time runs out.", "warning");
    } else if (latest && latest.status === "failed" && order.status === "awaiting_payment") {
      showAlert(message, [latest.failure_reason || "The payment failed.", "You can try again with Pay now."], "error", "Payment not completed");
    } else if (latest && latest.status === "pending" && order.status === "awaiting_payment" && polls < 15) {
      // The provider's confirmation has not arrived yet: check again shortly.
      showAlert(message, "We are confirming your payment with the payment provider…", "info");
      polls += 1;
      setTimeout(load, 2000);
      return;
    } else if (order.status === "cancelled") {
      clearAlert(message);
      return;
    } else {
      showAlert(message, "We have not received a confirmation of your payment yet. You can try again with Pay now.", "warning");
    }
    // Drop the flag so reloading the page does not repeat the message.
    history.replaceState(null, "", `/order.html?id=${orderId}`);
  }

  async function load() {
    if (!orderId) {
      content.innerHTML = "";
      showAlert(message, "No order was selected.");
      return;
    }
    try {
      const order = await api(`/api/orders/${orderId}`);
      render(order);
      if (returned && new URLSearchParams(window.location.search).get("payment")) explainPayment(order);
    } catch (err) {
      clearInterval(countdown);
      content.innerHTML = `<div class="card"><div class="empty-state"><div class="icon">😕</div>
        <p>${escapeHtml(err.message)}</p><a class="btn" href="/orders.html">Back to My Orders</a></div></div>`;
    }
  }

  refreshCartCount();
  load();
})();
