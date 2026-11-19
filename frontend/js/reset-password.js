/* Choosing a new password from the reset link (FR91). */

(function () {
  const message = document.getElementById("message");
  const form = document.getElementById("form");
  const token = queryParam("token") || "";
  history.replaceState(null, "", "/reset-password.html"); // keep the token out of the history

  if (!token) {
    form.remove();
    showAlert(message, "This link is incomplete.", "warning");
    message.insertAdjacentHTML("beforeend", ' <a href="/forgot-password.html">Ask for a new link</a>');
    return;
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const password = document.getElementById("password").value;
    const confirmation = document.getElementById("password-confirm").value;
    if (password !== confirmation) {
      showAlert(message, "The two passwords do not match.");
      return;
    }
    document.getElementById("submit-btn").disabled = true;
    try {
      const result = await api("/api/account/reset-password", {
        method: "POST",
        json: { token, password, password_confirm: confirmation },
        redirectOn401: false,
      });
      Auth.clear(); // every session of the account has ended (FR91)
      form.remove();
      showAlert(message, [result.message], "success", "Password changed");
      message.insertAdjacentHTML("beforeend", '<a class="btn btn-block mt-md" href="/login.html">Log in</a>');
    } catch (err) {
      showAlert(message, err.errors);
      if (err.data.code === "invalid_token") {
        form.remove();
        message.insertAdjacentHTML("beforeend", ' <a href="/forgot-password.html">Ask for a new link</a>');
      } else {
        document.getElementById("submit-btn").disabled = false;
      }
    }
  });
})();
