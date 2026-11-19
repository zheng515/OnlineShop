/* Confirming an email address from the link in the email (FR90). The link only opens this page;
   confirming is a POST made by the page, so link scanners in mail systems do not use it up. */

(function () {
  const message = document.getElementById("message");
  const token = queryParam("token") || "";
  const resend = document.getElementById("resend");

  async function confirm() {
    if (!token) {
      showAlert(message, "This link is incomplete. You can ask for a new one below.", "warning");
      resend.classList.remove("hidden");
      return;
    }
    showAlert(message, "Confirming your email address…", "info");
    try {
      const result = await api("/api/account/verify-email", { method: "POST", json: { token }, redirectOn401: false });
      message.innerHTML = "";
      showAlert(message, [result.message], "success", "Thank you!");
      message.insertAdjacentHTML("beforeend", '<a class="btn btn-block mt-md" href="/login.html">Log in</a>');
    } catch (err) {
      showAlert(message, err.errors, "warning");
      resend.classList.remove("hidden");
    }
    history.replaceState(null, "", "/verify-email.html"); // keep the token out of the history
  }

  document.getElementById("form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const email = document.getElementById("email").value.trim();
    if (!email) return;
    try {
      const result = await api("/api/account/resend-verification", { method: "POST", json: { email }, redirectOn401: false });
      showAlert(message, result.message, "success");
      resend.classList.add("hidden");
    } catch (err) {
      showAlert(message, err.errors);
    }
  });

  confirm();
})();
