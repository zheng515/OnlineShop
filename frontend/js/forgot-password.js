/* Asking for a password reset link (FR91). The answer is the same whether or not the address has an account. */

(function () {
  const message = document.getElementById("message");
  const form = document.getElementById("form");

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const email = document.getElementById("email").value.trim();
    if (!email) {
      showAlert(message, "Please enter your email address.");
      return;
    }
    document.getElementById("submit-btn").disabled = true;
    try {
      const result = await api("/api/account/forgot-password", { method: "POST", json: { email }, redirectOn401: false });
      form.remove();
      showAlert(message, [result.message, "The link works for one hour."], "success", "Check your email");
    } catch (err) {
      showAlert(message, err.errors);
      document.getElementById("submit-btn").disabled = false;
    }
  });
})();
