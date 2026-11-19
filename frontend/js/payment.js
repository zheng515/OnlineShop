/* Payment page: order summary, total and Place Order (FR32, FR41-FR43). Payment processing is out of scope. */

(function () {
  if (!requireRole("customer")) return;
  renderHeader();

  const content = document.getElementById("payment-content");
  const message = document.getElementById("payment-message");
  const backLinkEl = document.getElementById("back-link");
  const request = OrderSummary.requestFromUrl();
  // One id per visit: clicking Place Order again, or retrying after a network error, reuses it (FR43).
  const requestId = newRequestId();
  let shownSummary = null;

  if (!request) {
    content.innerHTML = "";
    showAlert(message, "The checkout request is incomplete. Please select your items again.");
    backLinkEl.href = "/shop.html";
    backLinkEl.innerHTML = "&larr; Back to products";
    return;
  }

  const checkoutUrl = `/checkout.html?${OrderSummary.queryString(request)}`;
  backLinkEl.href = checkoutUrl;
  document.getElementById("steps").innerHTML = `
    <span class="step">${request.source === "cart" ? "Cart" : "Product"}</span><span class="sep">›</span>
    <span class="step">Checkout</span><span class="sep">›</span>
    <span class="step current">Payment</span>`;

  function render(summary) {
    shownSummary = summary;
    if (!summary.valid) {
      OrderSummary.issuesAlert(message, summary);
      content.innerHTML = `<div class="card"><div class="empty-state">
        <p>Your order can no longer be placed as it is. Please review it on the checkout page.</p>
        <a class="btn" href="${checkoutUrl}">Back to Checkout</a></div></div>`;
      return;
    }
    content.innerHTML = `
      <div class="layout-with-aside">
        <div>
          <div class="card" style="margin-bottom: 1.25rem">${OrderSummary.itemsTable(summary)}</div>
          <div class="card card-body">
            <h2>Payment Method</h2>
            <div class="payment-placeholder">
              <div class="payment-methods">
                <div>💳 Card</div><div>🏦 Bank transfer</div><div>📱 Mobile wallet</div>
              </div>
              <p><strong>Online payment is not available in this version.</strong></p>
              <p>No payment will be taken. When you place the order, the items are set aside for you
                 and the order appears under My Orders.</p>
            </div>
          </div>
        </div>
        <aside class="card card-body summary-box">
          <h2>Amount Payable</h2>
          ${OrderSummary.totals(summary)}
          <button type="button" class="btn btn-lg btn-block" id="place-order-btn">
            Place Order · ${formatPrice(summary.total)}
          </button>
          <a class="btn btn-secondary btn-block" style="margin-top: 0.5rem" href="${checkoutUrl}">Back to Checkout</a>
        </aside>
      </div>`;
    document.getElementById("place-order-btn").addEventListener("click", placeOrder);
  }

  async function placeOrder(e) {
    const button = e.currentTarget;
    button.disabled = true;
    try {
      const order = await api("/api/orders", {
        method: "POST",
        json: { ...request, expected_total: shownSummary.total, request_id: requestId },
      });
      window.location.replace(`/order.html?id=${order.id}&placed=1`);
    } catch (err) {
      if (err.data.summary) {
        // Stock or prices changed: show the current summary so the customer can decide again (FR29, FR42).
        render(err.data.summary);
        if (err.data.summary.valid) showAlert(message, err.errors, "warning");
        return;
      }
      if (err.status === 0) {
        showAlert(message, `${err.message} You can click Place Order again — the order will not be placed twice.`);
      } else {
        showAlert(message, err.errors);
      }
      button.disabled = false;
    }
  }

  (async function load() {
    try {
      render(await OrderSummary.fetch(request));
    } catch (err) {
      content.innerHTML = "";
      showAlert(message, err.errors);
    }
  })();
})();
