/* Checkout page for both cart checkout and Buy Now (FR26-FR31, FR34). */

(function () {
  if (!requireRole("customer")) return;
  renderHeader();

  const content = document.getElementById("checkout-content");
  const message = document.getElementById("checkout-message");
  const backLinkEl = document.getElementById("back-link");
  const request = OrderSummary.requestFromUrl();

  if (!request) {
    content.innerHTML = "";
    showAlert(message, "The checkout request is incomplete. Please select your items again.");
    backLinkEl.href = "/shop.html";
    backLinkEl.innerHTML = "&larr; Back to products";
    return;
  }

  const back = OrderSummary.backLink(request);
  backLinkEl.href = back.href;
  backLinkEl.innerHTML = `&larr; ${back.label}`;
  document.getElementById("steps").innerHTML = `
    <span class="step">${request.source === "cart" ? "Cart" : "Product"}</span><span class="sep">›</span>
    <span class="step current">Checkout</span><span class="sep">›</span>
    <span class="step">Payment</span>`;

  function render(summary) {
    OrderSummary.issuesAlert(message, summary);
    if (summary.empty) {
      content.innerHTML = `<div class="card"><div class="empty-state"><div class="icon">🛒</div>
        <p>There is nothing to check out.</p><a class="btn" href="/shop.html">Browse products</a></div></div>`;
      return;
    }
    content.innerHTML = `
      <div class="layout-with-aside">
        <div class="card">${OrderSummary.itemsTable(summary)}</div>
        <aside class="card card-body summary-box">
          <h2>Order Summary</h2>
          ${OrderSummary.totals(summary)}
          <button type="button" class="btn btn-lg btn-block" id="continue-btn" ${summary.valid ? "" : "disabled"}>
            Continue to Payment
          </button>
          <a class="btn btn-secondary btn-block" style="margin-top: 0.5rem" href="${back.href}">${back.label}</a>
          <p class="field-hint">Prices reflect the current product prices.</p>
        </aside>
      </div>`;
    document.getElementById("continue-btn").addEventListener("click", continueToPayment);
  }

  async function load() {
    try {
      const summary = await OrderSummary.fetch(request);
      render(summary);
      return summary;
    } catch (err) {
      content.innerHTML = "";
      showAlert(message, err.errors);
      return null;
    }
  }

  async function continueToPayment(e) {
    e.target.disabled = true;
    // Revalidate stock against current data before letting the customer continue (FR29).
    const summary = await load();
    if (summary && summary.valid) {
      window.location.href = `/payment.html?${OrderSummary.queryString(request)}`;
    } else if (summary) {
      toast("Your order changed. Please review the highlighted items.", "error");
    }
  }

  load();
})();
