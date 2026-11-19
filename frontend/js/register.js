/* Registration (FR89). The server checks everything again; this only gives quick feedback. */

(function () {
  if (Auth.user) {
    window.location.replace(HOME_PAGES[Auth.user.role] || "/shop.html");
    return;
  }
  const message = document.getElementById("message");
  const el = (id) => document.getElementById(id);

  el("form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const body = {
      username: el("username").value.trim(),
      email: el("email").value.trim(),
      display_name: el("display-name").value.trim(),
      password: el("password").value,
      password_confirm: el("password-confirm").value,
    };
    const problems = [];
    if (!/^[A-Za-z0-9_.-]{3,32}$/.test(body.username)) problems.push("Username must be 3-32 characters: letters, digits, '.', '_' or '-'.");
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(body.email)) problems.push("Please enter a valid email address.");
    if (!body.display_name) problems.push("Display name is required.");
    if (body.password.length < 8 || !/[A-Za-z]/.test(body.password) || !/\d/.test(body.password)) {
      problems.push("Password must be 8 to 128 characters long and contain at least one letter and one digit.");
    }
    if (body.password !== body.password_confirm) problems.push("The two passwords do not match.");
    if (problems.length) {
      showAlert(message, problems);
      return;
    }
    el("submit-btn").disabled = true;
    try {
      const result = await api("/api/account/register", { method: "POST", json: body, redirectOn401: false });
      el("form").remove();
      showAlert(message, [result.message, `Open the link in the email we sent to ${body.email.toLowerCase()} to finish.`], "success",
        "Check your email");
    } catch (err) {
      showAlert(message, err.errors);
      el("submit-btn").disabled = false;
    }
  });
})();
