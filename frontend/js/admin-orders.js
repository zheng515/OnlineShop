/* Order Management page (FR47-FR49, FR82, FR83). */

(function () {
  if (!requireRole("admin")) return;
  renderHeader("orders");

  const rows = document.getElementById("order-rows");
  const listMessage = document.getElementById("list-message");
  const statusFilter = document.getElementById("status-filter");
  const searchInput = document.getElementById("search-input");
  const clearBtn = document.getElementById("clear-search");
  const modal = document.getElementById("detail-modal");
  const detailMessage = document.getElementById("detail-message");
  const detailActions = document.getElementById("detail-actions");

  let query = "";
  let current = null; // order shown in the modal

  function renderList(orders) {
    if (!orders.length) {
      const filtered = query || statusFilter.value;
      rows.innerHTML = `<tr><td colspan="7"><div class="empty-state"><div class="icon">🧾</div>
        <p>${filtered ? "No orders match your filters." : "No orders have been placed yet."}</p></div></td></tr>`;
      return;
    }
    rows.innerHTML = orders
      .map(
        (o) => `
        <tr class="clickable" data-id="${o.id}">
          <td class="item-name">${escapeHtml(o.number)}</td>
          <td>${escapeHtml(o.customer.display_name)} <span class="muted">(${escapeHtml(o.customer.username)})</span></td>
          <td class="nowrap hide-sm">${formatDateTime(o.created_at)}</td>
          <td>${statusBadge(o)}</td>
          <td class="stock-cell hide-sm">${o.item_count}</td>
          <td class="nowrap text-right"><strong>${formatPrice(o.total)}</strong></td>
          <td class="text-right hide-sm"><button type="button" class="btn btn-secondary btn-sm">View</button></td>
        </tr>`
      )
      .join("");
  }

  async function loadList() {
    const params = new URLSearchParams({ q: query });
    if (statusFilter.value) params.set("status", statusFilter.value);
    try {
      const data = await api(`/api/admin/orders?${params}`);
      if (query || statusFilter.value) {
        showAlert(
          listMessage,
          data.count ? `${data.count} order(s) found.` : "No orders found. Try a different keyword or status.",
          data.count ? "info" : "warning"
        );
      } else {
        clearAlert(listMessage);
      }
      renderList(data.orders);
    } catch (err) {
      rows.innerHTML = "";
      showAlert(listMessage, err.errors);
    }
  }

  document.getElementById("filter-form").addEventListener("submit", (e) => {
    e.preventDefault();
    query = searchInput.value.trim();
    clearBtn.classList.toggle("hidden", !query);
    loadList();
  });
  statusFilter.addEventListener("change", loadList);
  clearBtn.addEventListener("click", () => {
    searchInput.value = "";
    query = "";
    clearBtn.classList.add("hidden");
    loadList();
  });

  rows.addEventListener("click", (e) => {
    const row = e.target.closest("tr[data-id]");
    if (row) openOrder(Number(row.dataset.id));
  });

  // ---------- Detail modal ----------
  function renderDetail(order) {
    current = order;
    document.getElementById("detail-title").textContent = `Order ${order.number}`;
    document.getElementById("detail-body").innerHTML = `
      ${OrderView.meta(order, { showCustomer: true })}
      <div class="card mb-lg">${OrderView.items(order)}</div>
      <h2>Payments and refunds</h2>
      ${OrderView.payments(order)}
      <h2 class="mt-md">Status history</h2>
      ${OrderView.history(order)}`;
    detailActions.innerHTML =
      OrderView.actionButtons(order) +
      (order.can_retry_refund ? '<button type="button" class="btn btn-secondary" data-action="retry-refund">Retry refund</button>' : "");
  }

  async function openOrder(id) {
    clearAlert(detailMessage);
    try {
      renderDetail(await api(`/api/admin/orders/${id}`));
      modal.classList.remove("hidden");
    } catch (err) {
      toast(err.message, "error");
    }
  }

  detailActions.addEventListener("click", async (e) => {
    const button = e.target.closest("[data-action]");
    if (!button || !current) return;
    const action = button.dataset.action;
    if (!(await OrderView.confirmAction(current, action))) return;
    button.disabled = true;
    try {
      const updated =
        action === "retry-refund"
          ? await api(`/api/admin/orders/${current.id}/refunds/retry`, { method: "POST" })
          : await api(`/api/admin/orders/${current.id}/status`, { method: "POST", json: { status: action } });
      toast(updated.message, "success");
      clearAlert(detailMessage);
      renderDetail(updated);
    } catch (err) {
      showAlert(detailMessage, err.errors);
      // The order may have been changed elsewhere: show its current state.
      try {
        renderDetail(await api(`/api/admin/orders/${current.id}`));
      } catch {
        button.disabled = false;
      }
    }
    loadList();
  });

  function closeModal() {
    modal.classList.add("hidden");
    current = null;
  }
  modal.addEventListener("click", (e) => {
    if (e.target === modal || e.target.closest("[data-close]")) closeModal();
  });
  document.addEventListener("keydown", (e) => {
    // The confirmation dialog handles its own Escape.
    if (e.key === "Escape" && !document.querySelector('[role="alertdialog"]')) closeModal();
  });

  loadList();
})();
