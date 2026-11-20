/* Checkout page for both cart checkout and Buy Now, with the delivery choice (FR26-FR31, FR34, FR105, FR106). */

(function () {
  if (!requireRole("customer")) return;
  renderHeader();

  const content = document.getElementById("checkout-content");
  const message = document.getElementById("checkout-message");
  const backLinkEl = document.getElementById("back-link");
  const request = OrderSummary.requestFromUrl();
  let book = { addresses: [], countries: [], max: 10 };
  let addingAddress = false;
  let current = null; // the summary on screen

  if (!request) {
    content.innerHTML = "";
    showAlert(message, "The checkout request is incomplete. Please select your items again.");
    backLinkEl.href = "/shop.html";
    backLinkEl.innerHTML = "&larr; Back to products";
    return;
  }

  const back = OrderSummary.backLink(request);
  backLinkEl.href = back.href;
  backLinkEl.innerHTML = `&larr; ${back.label}`;
  document.getElementById("steps").innerHTML = `
    <span class="step">${request.source === "cart" ? "Cart" : "Product"}</span><span class="sep">›</span>
    <span class="step current">Checkout</span><span class="sep">›</span>
    <span class="step">Payment</span>`;

  /** Keep the choice in the URL, so Back from the Payment page returns to it (FR105). */
  function remember(summary) {
    const { address, method } = summary.delivery;
    if (address && address.deliverable) request.address_id = address.id;
    if (method) request.shipping_method_id = method.id;
    history.replaceState(null, "", `/checkout.html?${OrderSummary.queryString(request)}`);
  }

  function addressSection(summary) {
    const chosen = summary.delivery.address;
    const options = book.addresses
      .map(
        (a) => `
        <label class="choice ${a.deliverable ? "" : "disabled"}">
          <input type="radio" name="address" value="${a.id}" ${chosen && chosen.id === a.id ? "checked" : ""}
                 ${a.deliverable ? "" : "disabled"}>
          <span>${AddressForm.lines(a)}
            ${a.is_default ? '<span class="status-tag tag-primary">Default</span>' : ""}
            ${a.deliverable ? "" : '<span class="item-issue">We no longer deliver to this country.</span>'}</span>
        </label>`
      )
      .join("");
    const showForm = addingAddress || !book.addresses.length;
    const canAdd = book.addresses.length < book.max;
    return `
      <section class="card card-body mb-lg" id="address-section">
        <h2>Delivery address</h2>
        <div class="choices" id="address-choices">${options}</div>
        ${
          showForm && canAdd
            ? `<form id="new-address-form" class="address-form" novalidate>
                 <h3>${book.addresses.length ? "New address" : "Where should we deliver your order?"}</h3>
                 <div id="new-address-message" class="hidden" role="alert"></div>
                 ${AddressForm.fields(null, book.countries)}
                 <div class="form-actions">
                   <button type="submit" class="btn" id="save-address-btn">Save and use this address</button>
                   ${book.addresses.length ? '<button type="button" class="btn btn-secondary" id="cancel-address-btn">Cancel</button>' : ""}
                 </div>
                 <p class="field-hint">The address is saved in your address book.</p>
               </form>`
            : canAdd
              ? '<button type="button" class="btn btn-secondary btn-sm" id="add-address-btn">Add a new address</button>'
              : ""
        }
      </section>`;
  }

  function methodSection(summary) {
    const { methods, method } = summary.delivery;
    if (!methods.length) return "";
    return `
      <section class="card card-body" id="method-section">
        <h2>Delivery method</h2>
        <div class="choices" id="method-choices">
          ${methods
            .map(
              (m) => `
            <label class="choice">
              <input type="radio" name="method" value="${m.id}" ${method && method.id === m.id ? "checked" : ""}>
              <span class="choice-main"><strong>${escapeHtml(m.name)}</strong>
                ${m.description ? `<span class="muted">${escapeHtml(m.description)}</span>` : ""}</span>
              <span class="choice-price">${OrderSummary.methodFee(m)}</span>
            </label>`
            )
            .join("")}
        </div>
      </section>`;
  }

  function render(summary) {
    current = summary;
    OrderSummary.issuesAlert(message, summary);
    if (summary.empty) {
      content.innerHTML = `<div class="card"><div class="empty-state"><div class="icon">🛒</div>
        <p>There is nothing to check out.</p><a class="btn" href="/shop.html">Browse products</a></div></div>`;
      return;
    }
    // "Please add a delivery address" is what the form below is for, not an error.
    const deliveryIssues = summary.delivery_issues.filter((issue) => book.addresses.length || !issue.startsWith("Please add"));
    content.innerHTML = `
      <div class="layout-with-aside">
        <div>
          <div class="card mb-lg">${OrderSummary.itemsTable(summary)}</div>
          <div id="delivery-message" class="hidden" role="alert"></div>
          ${addressSection(summary)}
          ${methodSection(summary)}
        </div>
        <aside class="card card-body summary-box">
          <h2>Order Summary</h2>
          ${OrderSummary.totals(summary)}
          <button type="button" class="btn btn-lg btn-block" id="continue-btn" ${summary.ready ? "" : "disabled"}>
            Continue to Payment
          </button>
          <a class="btn btn-secondary btn-block mt-sm" href="${back.href}">${back.label}</a>
          <p class="field-hint">Prices reflect the current product prices and delivery fees. Prices include taxes.</p>
        </aside>
      </div>`;
    if (deliveryIssues.length) showAlert(document.getElementById("delivery-message"), deliveryIssues, "warning");
    bind();
  }

  function bind() {
    document.getElementById("continue-btn").addEventListener("click", continueToPayment);
    const choose = (key) => (e) => {
      request[key] = Number(e.target.value);
      reload(e.target);
    };
    document.getElementById("address-choices").addEventListener("change", choose("address_id"));
    const methods = document.getElementById("method-choices");
    if (methods) methods.addEventListener("change", choose("shipping_method_id"));
    const add = document.getElementById("add-address-btn");
    if (add) {
      add.addEventListener("click", () => {
        addingAddress = true;
        render(current);
        document.querySelector("#new-address-form input").focus();
      });
    }
    const form = document.getElementById("new-address-form");
    if (form) form.addEventListener("submit", saveAddress);
    const cancel = document.getElementById("cancel-address-btn");
    if (cancel) {
      cancel.addEventListener("click", () => {
        addingAddress = false;
        render(current);
      });
    }
  }

  async function saveAddress(e) {
    e.preventDefault();
    const form = e.currentTarget;
    const button = document.getElementById("save-address-btn");
    button.disabled = true;
    try {
      const result = await api("/api/account/addresses", { method: "POST", json: AddressForm.read(form) });
      book = result;
      addingAddress = false;
      request.address_id = result.address_id;
      toast("Address saved", "success");
      await load();
    } catch (err) {
      showAlert(document.getElementById("new-address-message"), err.errors, "error", "Please check the address:");
      button.disabled = false;
    }
  }

  /** Reload the summary after a change, keeping keyboard focus on the option that was chosen. */
  async function reload(input) {
    await load();
    const again = input && document.querySelector(`input[name="${input.name}"][value="${input.value}"]`);
    if (again) again.focus();
  }

  async function load() {
    try {
      const summary = await OrderSummary.fetch(request);
      render(summary);
      if (!summary.empty) remember(summary);
      return summary;
    } catch (err) {
      content.innerHTML = "";
      showAlert(message, err.errors);
      return null;
    }
  }

  async function continueToPayment(e) {
    e.target.disabled = true;
    // Revalidate stock and the delivery choice against current data before continuing (FR29, FR105).
    const summary = await load();
    if (summary && summary.ready) {
      window.location.href = `/payment.html?${OrderSummary.queryString(request)}`;
    } else if (summary) {
      toast("Your order changed. Please review the highlighted items.", "error");
    }
  }

  (async function init() {
    try {
      book = await api("/api/account/addresses");
    } catch {
      /* The summary below still loads and reports what is missing. */
    }
    load();
  })();
})();
