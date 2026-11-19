/* Customer order history, with the time left to pay (FR46, FR86). */

(function () {
  if (!requireRole("customer")) return;
  renderHeader("orders");

  const content = document.getElementById("orders-content");
  const message = document.getElementById("orders-message");

  function render(orders) {
    if (!orders.length) {
      content.innerHTML = `
        <div class="card"><div class="empty-state">
          <div class="icon">📦</div>
          <p><strong>You have not placed any orders yet.</strong></p>
          <a class="btn" href="/shop.html">Browse products</a>
        </div></div>`;
      return;
    }
    content.innerHTML = `
      <div class="card">
        <div class="table-wrap">
          <table class="table">
            <thead>
              <tr><th>Order</th><th>Date</th><th>Status</th><th class="stock-cell">Items</th><th class="text-right">Total</th></tr>
            </thead>
            <tbody>
              ${orders
                .map(
                  (o) => `
                <tr class="clickable" data-id="${o.id}">
                  <td><a href="/order.html?id=${o.id}" class="item-name">${escapeHtml(o.number)}</a></td>
                  <td class="nowrap">${formatDateTime(o.created_at)}</td>
                  <td>${statusBadge(o)}${
                    o.status === "awaiting_payment"
                      ? `<div class="item-size">Pay within ${Math.ceil(o.seconds_left / 60)} min</div>`
                      : ""
                  }</td>
                  <td class="stock-cell">${o.item_count}</td>
                  <td class="nowrap text-right"><strong>${formatPrice(o.total)}</strong></td>
                </tr>`
                )
                .join("")}
            </tbody>
          </table>
        </div>
      </div>`;
    content.querySelector("tbody").addEventListener("click", (e) => {
      const row = e.target.closest("tr[data-id]");
      if (row && !e.target.closest("a")) window.location.href = `/order.html?id=${row.dataset.id}`;
    });
  }

  (async function load() {
    try {
      render((await api("/api/orders")).orders);
    } catch (err) {
      content.innerHTML = "";
      showAlert(message, err.errors);
    }
  })();
})();
