/* Account page: display name and password (FR92). */

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

  (async function load() {
    try {
      show(await api("/api/account"));
    } catch (err) {
      showAlert(message, err.errors);
    }
  })();
})();
