/* Payment page (FR32): shows the order summary and total. Payment processing is out of scope. */

(function () {
  if (!requireRole("customer")) return;
  renderHeader();

  const content = document.getElementById("payment-content");
  const message = document.getElementById("payment-message");
  const backLinkEl = document.getElementById("back-link");
  const request = OrderSummary.requestFromUrl();

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
    if (!summary.valid) {
      OrderSummary.issuesAlert(message, summary);
      content.innerHTML = `<div class="card"><div class="empty-state">
        <p>Your order can no longer be paid as it is. Please review it on the checkout page.</p>
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
              <p>Payment processing, payment confirmation and order fulfilment will be added in a future release.
                 No order has been placed and you have not been charged.</p>
            </div>
          </div>
        </div>
        <aside class="card card-body summary-box">
          <h2>Amount Payable</h2>
          ${OrderSummary.totals(summary)}
          <button type="button" class="btn btn-lg btn-block" disabled title="Payment is not available in this version">
            Pay ${formatPrice(summary.total)}
          </button>
          <a class="btn btn-secondary btn-block" style="margin-top: 0.5rem" href="${checkoutUrl}">Back to Checkout</a>
        </aside>
      </div>`;
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
