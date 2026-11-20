/* Account page: display name, password and address book (FR92, FR100). */

(function () {
  if (!requireRole("customer")) return;
  renderHeader("account");

  const message = document.getElementById("message");
  const el = (id) => document.getElementById(id);

  function show(account) {
    el("username").textContent = account.username;
    el("email").textContent = account.email || "—";
    el("display-name").value = account.display_name;
  }

  el("profile-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    el("profile-btn").disabled = true;
    try {
      const account = await api("/api/account", { method: "PATCH", json: { display_name: el("display-name").value } });
      show(account);
      Auth.save({ ...Auth.user, display_name: account.display_name });
      renderHeader("account");
      showAlert(message, account.message, "success");
    } catch (err) {
      showAlert(message, err.errors);
    } finally {
      el("profile-btn").disabled = false;
    }
  });

  el("password-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const body = {
      current_password: el("current-password").value,
      new_password: el("new-password").value,
      new_password_confirm: el("new-password-confirm").value,
    };
    if (body.new_password !== body.new_password_confirm) {
      showAlert(message, "The two new passwords do not match.");
      return;
    }
    el("password-btn").disabled = true;
    try {
      const result = await api("/api/account/password", { method: "POST", json: body });
      el("password-form").reset();
      showAlert(message, result.message, "success");
    } catch (err) {
      showAlert(message, err.errors);
    } finally {
      el("password-btn").disabled = false;
    }
  });

  // ---------- Address book (FR100-FR102) ----------
  const addressMessage = el("address-message");
  const addressForm = el("address-form");
  let book = { addresses: [], countries: [], max: 10 };
  let editing = null; // address being edited, or null for a new one

  function renderAddresses() {
    const list = el("address-list");
    el("add-address-btn").disabled = book.addresses.length >= book.max;
    if (!book.addresses.length) {
      list.innerHTML = '<p class="muted">You have no saved addresses yet. Add one to check out faster.</p>';
      return;
    }
    list.innerHTML = book.addresses
      .map(
        (a) => `
        <div class="address-card ${a.is_default ? "is-default" : ""}" data-id="${a.id}">
          <div class="address-text">
            ${a.is_default ? '<span class="status-tag tag-primary">Default</span>' : ""}
            ${a.deliverable ? "" : '<span class="status-tag">Not deliverable</span>'}
            <div>${AddressForm.lines(a)}</div>
          </div>
          <div class="address-actions">
            <button type="button" class="btn btn-secondary btn-sm" data-act="edit">Edit</button>
            ${a.is_default ? "" : '<button type="button" class="btn btn-secondary btn-sm" data-act="default">Make default</button>'}
            <button type="button" class="btn btn-ghost btn-sm" data-act="delete">Delete</button>
          </div>
        </div>`
      )
      .join("");
    if (book.addresses.length >= book.max) {
      list.insertAdjacentHTML("beforeend", `<p class="field-hint">You can keep at most ${book.max} addresses.</p>`);
    }
  }

  function openForm(address) {
    editing = address;
    el("address-form-title").textContent = address ? "Edit address" : "New address";
    el("address-form-fields").innerHTML = AddressForm.fields(address, book.countries);
    addressForm.classList.remove("hidden");
    addressForm.querySelector("input").focus();
  }

  function closeForm() {
    addressForm.classList.add("hidden");
    editing = null;
  }

  function apply(result) {
    book = result;
    renderAddresses();
    if (result.message) showAlert(addressMessage, result.message, "success");
  }

  el("add-address-btn").addEventListener("click", () => {
    clearAlert(addressMessage);
    openForm(null);
  });
  el("address-cancel-btn").addEventListener("click", closeForm);

  addressForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    el("address-save-btn").disabled = true;
    try {
      const body = AddressForm.read(addressForm);
      const result = editing
        ? await api(`/api/account/addresses/${editing.id}`, { method: "PUT", json: body })
        : await api("/api/account/addresses", { method: "POST", json: body });
      closeForm();
      apply(result);
    } catch (err) {
      showAlert(addressMessage, err.errors, "error", "Please check the address:");
    } finally {
      el("address-save-btn").disabled = false;
    }
  });

  el("address-list").addEventListener("click", async (e) => {
    const button = e.target.closest("[data-act]");
    if (!button) return;
    const address = book.addresses.find((a) => String(a.id) === button.closest("[data-id]").dataset.id);
    clearAlert(addressMessage);
    if (button.dataset.act === "edit") return openForm(address);
    if (button.dataset.act === "delete") {
      const confirmed = await confirmDialog({
        title: "Delete this address?",
        message: `${address.lines.join(", ")} will be removed from your address book. Orders already placed keep their address.`,
        confirmLabel: "Delete",
        danger: true,
      });
      if (!confirmed) return;
    }
    button.disabled = true;
    try {
      const path = `/api/account/addresses/${address.id}`;
      apply(
        button.dataset.act === "delete"
          ? await api(path, { method: "DELETE" })
          : await api(`${path}/default`, { method: "POST" })
      );
      if (editing && editing.id === address.id) closeForm();
    } catch (err) {
      showAlert(addressMessage, err.errors);
      loadAddresses();
    }
  });

  async function loadAddresses() {
    try {
      apply(await api("/api/account/addresses"));
    } catch (err) {
      el("address-list").innerHTML = "";
      showAlert(addressMessage, err.errors);
    }
  }

  (async function load() {
    try {
      show(await api("/api/account"));
    } catch (err) {
      showAlert(message, err.errors);
    }
  })();
  loadAddresses();
})();
