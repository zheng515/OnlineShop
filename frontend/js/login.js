/* Login page: role selection (FR1), authentication (FR2), redirection (FR4, FR98) and resending the
   confirmation email for unconfirmed accounts (FR90). */

(async function () {
  const LABELS = { admin: "Administrator", customer: "Customer" };
  const form = document.getElementById("login-form");
  const errorBox = document.getElementById("login-error");
  const submitBtn = document.getElementById("login-btn");
  const tabs = document.querySelectorAll(".role-tab");
  let role = "customer";
  let unverifiedEmail = null;
  const next = safeNext(queryParam("next") || "");

  /** Where to go after logging in: back to the page that sent the customer here, if any (FR98). */
  function destination(user) {
    return user.role === "customer" && next ? next : user.home;
  }

  // Already signed in: go straight to the role's home page.
  if (Auth.user) {
    try {
      const user = await api("/api/auth/me", { redirectOn401: false });
      window.location.replace(destination(user));
      return;
    } catch {
      Auth.clear();
    }
  }

  function selectRole(newRole) {
    role = newRole;
    tabs.forEach((tab) => {
      const active = tab.dataset.role === role;
      tab.classList.toggle("active", active);
      tab.setAttribute("aria-selected", active);
    });
    submitBtn.textContent = `Log in as ${LABELS[role]}`;
    clearAlert(errorBox);
    document.getElementById("username").focus();
  }

  tabs.forEach((tab) => tab.addEventListener("click", () => selectRole(tab.dataset.role)));

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearAlert(errorBox);
    const username = document.getElementById("username").value.trim();
    const password = document.getElementById("password").value;
    const missing = [];
    if (!username) missing.push("Please enter your username.");
    if (!password) missing.push("Please enter your password.");
    if (missing.length) {
      showAlert(errorBox, missing);
      return;
    }

    submitBtn.disabled = true;
    try {
      const result = await api("/api/auth/login", {
        method: "POST",
        json: { username, password, role },
        redirectOn401: false,
      });
      Auth.save(result.user);
      window.location.replace(destination(result.user));
    } catch (err) {
      showAlert(errorBox, err.errors);
      document.getElementById("password").value = "";
      unverifiedEmail = err.data.code === "email_unverified" ? err.data.email : null;
      document.getElementById("resend-box").classList.toggle("hidden", !unverifiedEmail);
    } finally {
      submitBtn.disabled = false;
    }
  });

  document.getElementById("resend-btn").addEventListener("click", async (e) => {
    e.target.disabled = true;
    try {
      const result = await api("/api/account/resend-verification", { method: "POST", json: { email: unverifiedEmail } });
      showAlert(errorBox, result.message, "success");
    } catch (err) {
      showAlert(errorBox, err.errors);
    }
  });

  selectRole(role);
  if (next) showAlert(errorBox, "Please log in or create an account to continue.", "info");
})();
