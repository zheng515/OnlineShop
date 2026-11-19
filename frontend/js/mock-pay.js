/* The mock payment provider's page (FR84): shows the payment and lets the user pick the outcome.
   It does not need the shop's login, just like a real provider's page. */

(function () {
  const content = document.getElementById("mockpay-content");
  const reference = queryParam("session") || "";
  let session = null;
  let timer = null;

  function minutesSeconds(seconds) {
    const m = Math.floor(seconds / 60);
    const s = String(seconds % 60).padStart(2, "0");
    return `${m}:${s}`;
  }

  function showError(message, returnUrl) {
    clearInterval(timer);
    content.innerHTML = `
      <div class="alert alert-error">${escapeHtml(message)}</div>
      ${returnUrl ? `<a class="btn btn-block" href="${escapeHtml(returnUrl)}">Return to ${escapeHtml(session.merchant)}</a>` : ""}`;
  }

  function render() {
    content.innerHTML = `
      <p class="muted">Pay <strong>${escapeHtml(session.merchant)}</strong></p>
      <div class="mockpay-amount">${formatPrice(session.amount)} <span class="muted">${escapeHtml(session.currency)}</span></div>
      <dl class="detail-list mb-lg">
        <dt>Order</dt><dd>${escapeHtml(session.order_number)}</dd>
        <dt>Time left</dt><dd id="mockpay-time">${minutesSeconds(session.seconds_left)}</dd>
        <dt>Card</dt><dd>Test card ···· 4242</dd>
      </dl>
      <div id="mockpay-message" class="hidden" role="alert"></div>
      <button type="button" class="btn btn-lg btn-block" data-outcome="succeed">Pay ${formatPrice(session.amount)}</button>
      <button type="button" class="btn btn-secondary btn-block mt-sm" data-outcome="fail">Simulate a declined payment</button>
      <button type="button" class="btn btn-ghost btn-block mt-sm" data-outcome="cancel">Cancel and return to ${escapeHtml(session.merchant)}</button>`;
    content.addEventListener("click", onChoose);
    timer = setInterval(() => {
      session.seconds_left = Math.max(0, session.seconds_left - 1);
      const label = document.getElementById("mockpay-time");
      if (label) label.textContent = minutesSeconds(session.seconds_left);
      if (session.seconds_left === 0) showError("This payment session has expired.", session.return_url);
    }, 1000);
  }

  async function onChoose(e) {
    const button = e.target.closest("[data-outcome]");
    if (!button) return;
    content.querySelectorAll("button").forEach((b) => (b.disabled = true));
    try {
      const result = await api(`/api/mock-provider/sessions/${encodeURIComponent(reference)}/complete`, {
        method: "POST",
        json: { outcome: button.dataset.outcome },
        redirectOn401: false,
      });
      window.location.replace(result.redirect_url);
    } catch (err) {
      showError(err.message, session.return_url);
    }
  }

  (async function load() {
    try {
      session = await api(`/api/mock-provider/sessions/${encodeURIComponent(reference)}`, { redirectOn401: false });
    } catch (err) {
      content.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
      return;
    }
    document.title = `MockPay · Pay ${session.merchant}`;
    if (session.status !== "open") showError("This payment session is already finished.", session.return_url);
    else if (session.seconds_left <= 0) showError("This payment session has expired.", session.return_url);
    else render();
  })();
})();
