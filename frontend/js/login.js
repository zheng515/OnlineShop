/* Login page: role selection (FR1), authentication (FR2) and redirection (FR4). */

(async function () {
  const LABELS = { admin: "Administrator", customer: "Customer" };
  const form = document.getElementById("login-form");
  const errorBox = document.getElementById("login-error");
  const submitBtn = document.getElementById("login-btn");
  const tabs = document.querySelectorAll(".role-tab");
  let role = "customer";

  // Already signed in: go straight to the role's home page.
  if (Auth.token) {
    try {
      const user = await api("/api/auth/me", { redirectOn401: false });
      window.location.replace(user.home);
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
      Auth.save(result.token, result.user);
      window.location.replace(result.user.home);
    } catch (err) {
      showAlert(errorBox, err.errors);
      document.getElementById("password").value = "";
    } finally {
      submitBtn.disabled = false;
    }
  });

  selectRole(role);
})();
