/* Payment page: order summary, total and Place Order and Pay (FR32, FR41-FR43, FR78). */

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
  let paymentInfo = { test_mode: false, method: "card", timeout_minutes: 30 };

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
          <div class="card mb-lg">${OrderSummary.itemsTable(summary)}</div>
          <div class="card card-body">
            <h2>Payment</h2>
            ${
              paymentInfo.test_mode
                ? `<div class="alert alert-warning"><strong>Test payments.</strong> This shop uses a simulated
                   payment provider: no real money is charged.</div>`
                : ""
            }
            <p>You will be taken to our payment provider's secure page to pay with
               <strong>${escapeHtml(paymentInfo.method)}</strong>. Your card details are entered there, never in this shop.</p>
            <p class="muted">Your items are held for you for ${paymentInfo.timeout_minutes} minutes while you pay.
               If you don't pay in time, the order is cancelled automatically.</p>
          </div>
        </div>
        <aside class="card card-body summary-box">
          <h2>Amount Payable</h2>
          ${OrderSummary.totals(summary)}
          <button type="button" class="btn btn-lg btn-block" id="place-order-btn">
            Place Order and Pay · ${formatPrice(summary.total)}
          </button>
          <a class="btn btn-secondary btn-block mt-sm" href="${checkoutUrl}">Back to Checkout</a>
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
      // On to the payment provider (FR78); the order page takes over if that is not possible.
      window.location.assign(order.payment_url || `/order.html?id=${order.id}`);
    } catch (err) {
      if (err.data.summary) {
        // Stock or prices changed: show the current summary so the customer can decide again (FR29, FR42).
        render(err.data.summary);
        if (err.data.summary.valid) showAlert(message, err.errors, "warning");
        return;
      }
      if (err.status === 0) {
        showAlert(message, `${err.message} You can click the button again — the order will not be placed twice.`);
      } else {
        showAlert(message, err.errors);
      }
      button.disabled = false;
    }
  }

  (async function load() {
    try {
      paymentInfo = await api("/api/payments/info");
    } catch {
      /* Defaults above are fine for display. */
    }
    try {
      render(await OrderSummary.fetch(request));
    } catch (err) {
      content.innerHTML = "";
      showAlert(message, err.errors);
    }
  })();
})();
