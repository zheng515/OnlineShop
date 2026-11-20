/* Delivery Methods page: add, edit, activate, deactivate and delete methods (FR103, FR104). */

(function () {
  if (!requireRole("admin")) return;
  renderHeader("shipping");

  const el = (id) => document.getElementById(id);
  const rows = el("method-rows");
  const listMessage = el("list-message");
  const modal = el("method-modal");
  const form = el("method-form");
  const formMessage = el("form-message");
  let methods = [];
  let editing = null;

  document.querySelectorAll(".currency").forEach((node) => (node.textContent = CURRENCY));

  function money(value) {
    return value === null ? "—" : formatPrice(value);
  }

  function render(data) {
    methods = data.methods;
    if (!methods.length) {
      rows.innerHTML = `<tr><td colspan="6"><div class="empty-state"><div class="icon">🚚</div>
        <p>There are no delivery methods yet.</p></div></td></tr>`;
    } else {
      rows.innerHTML = methods
        .map(
          (m) => `
          <tr data-id="${m.id}">
            <td class="item-name">${escapeHtml(m.name)}</td>
            <td class="hide-sm">${escapeHtml(m.description) || '<span class="muted">—</span>'}</td>
            <td class="nowrap text-right">${m.fee ? formatPrice(m.fee) : "Free"}</td>
            <td class="nowrap text-right">${money(m.free_over)}</td>
            <td><span class="status-tag ${m.active ? "tag-success" : ""}">${m.active ? "Active" : "Inactive"}</span></td>
            <td class="text-right"><div class="actions">
              <button type="button" class="btn btn-secondary btn-sm" data-act="edit">Edit</button>
              <button type="button" class="btn btn-secondary btn-sm" data-act="toggle">${m.active ? "Deactivate" : "Activate"}</button>
              <button type="button" class="btn btn-ghost btn-sm" data-act="delete">Delete</button>
            </div></td>
          </tr>`
        )
        .join("");
    }
    if (!data.active_count) {
      // Nothing can be ordered without an active method (FR104).
      showAlert(listMessage, "No delivery method is active, so customers cannot place orders. Add or activate a method.", "warning");
    } else if (data.message) {
      showAlert(listMessage, data.message, "success");
    } else {
      clearAlert(listMessage);
    }
  }

  async function load() {
    try {
      render(await api("/api/admin/shipping-methods"));
    } catch (err) {
      rows.innerHTML = "";
      showAlert(listMessage, err.errors);
    }
  }

  function openForm(method) {
    editing = method;
    clearAlert(formMessage);
    el("method-title").textContent = method ? `Edit ${method.name}` : "Add delivery method";
    el("name-input").value = method ? method.name : "";
    el("description-input").value = method ? method.description : "";
    el("fee-input").value = method ? method.fee.toFixed(2) : "";
    el("free-over-input").value = method && method.free_over !== null ? method.free_over.toFixed(2) : "";
    el("active-input").checked = method ? method.active : true;
    modal.classList.remove("hidden");
    el("name-input").focus();
  }

  function closeForm() {
    modal.classList.add("hidden");
    editing = null;
  }

  function payload(method) {
    return {
      name: method.name,
      description: method.description,
      fee: String(method.fee),
      free_over: method.free_over === null ? "" : String(method.free_over),
      active: method.active,
    };
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    el("save-btn").disabled = true;
    const body = {
      name: el("name-input").value,
      description: el("description-input").value,
      fee: el("fee-input").value,
      free_over: el("free-over-input").value,
      active: el("active-input").checked,
    };
    try {
      const result = editing
        ? await api(`/api/admin/shipping-methods/${editing.id}`, { method: "PUT", json: body })
        : await api("/api/admin/shipping-methods", { method: "POST", json: body });
      closeForm();
      render(result);
      toast(result.message, "success");
    } catch (err) {
      showAlert(formMessage, err.errors, "error", "Please correct the following:");
    } finally {
      el("save-btn").disabled = false;
    }
  });

  el("add-btn").addEventListener("click", () => openForm(null));

  rows.addEventListener("click", async (e) => {
    const button = e.target.closest("[data-act]");
    if (!button) return;
    const method = methods.find((m) => String(m.id) === button.closest("tr").dataset.id);
    const act = button.dataset.act;
    if (act === "edit") return openForm(method);
    if (act === "delete") {
      const confirmed = await confirmDialog({
        title: `Delete ${method.name}?`,
        message: "Customers will no longer be able to choose it. Orders already placed keep their delivery method and fee.",
        confirmLabel: "Delete",
        danger: true,
      });
      if (!confirmed) return;
    }
    button.disabled = true;
    try {
      const path = `/api/admin/shipping-methods/${method.id}`;
      const result =
        act === "delete"
          ? await api(path, { method: "DELETE" })
          : await api(path, { method: "PUT", json: { ...payload(method), active: !method.active } });
      render(result);
      toast(result.message, "success");
    } catch (err) {
      showAlert(listMessage, err.errors);
      load();
    }
  });

  modal.addEventListener("click", (e) => {
    if (e.target === modal || e.target.closest("[data-close]")) closeForm();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !document.querySelector('[role="alertdialog"]')) closeForm();
  });

  load();
})();
