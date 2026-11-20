/* Address form and address display shared by the Account and Checkout pages (FR100-FR102). */

const AddressForm = {
  FIELDS: [
    { key: "full_name", label: "Full name", max: 100, autocomplete: "name" },
    { key: "phone", label: "Phone number", max: 20, autocomplete: "tel", type: "tel" },
    { key: "line1", label: "Address line 1", max: 100, autocomplete: "address-line1" },
    { key: "line2", label: "Address line 2 (optional)", max: 100, autocomplete: "address-line2" },
    { key: "city", label: "City", max: 60, autocomplete: "address-level2" },
    { key: "region", label: "State, province or region (optional)", max: 60, autocomplete: "address-level1" },
    { key: "postal_code", label: "Postal code", max: 12, autocomplete: "postal-code" },
  ],

  /** Form fields for `address` (empty for a new one). `countries` are the delivery countries (FR102). */
  fields(address, countries, { showDefault = true } = {}) {
    const value = (key) => escapeHtml((address && address[key]) || "");
    const inputs = this.FIELDS.map(
      (f) => `
      <div class="field">
        <label for="addr-${f.key}">${f.label}</label>
        <input type="${f.type || "text"}" id="addr-${f.key}" name="${f.key}" maxlength="${f.max}"
               autocomplete="shipping ${f.autocomplete}" value="${value(f.key)}">
      </div>`
    ).join("");
    const current = (address && address.country) || (countries.length === 1 ? countries[0] : "");
    // An address whose country is no longer delivered to keeps it as an option, so editing shows it (FR102).
    const options = countries.includes(current) || !current ? countries : [current, ...countries];
    const country =
      countries.length === 1 && options.length === 1
        ? `<div class="field"><label>Country</label><p class="static-value">${escapeHtml(countries[0])}</p>
             <input type="hidden" name="country" value="${escapeHtml(countries[0])}"></div>`
        : `<div class="field"><label for="addr-country">Country</label>
             <select id="addr-country" name="country" autocomplete="shipping country-name">
               ${current ? "" : '<option value="">Choose a country</option>'}
               ${options.map((c) => `<option ${c === current ? "selected" : ""}>${escapeHtml(c)}</option>`).join("")}
             </select></div>`;
    const makeDefault =
      showDefault && !(address && address.is_default)
        ? `<label class="check-row"><input type="checkbox" name="make_default"> Use as my default address</label>`
        : "";
    return `<div class="address-fields">${inputs}${country}</div>${makeDefault}`;
  },

  /** The values of a form built with fields(). */
  read(form) {
    const data = {};
    this.FIELDS.forEach((f) => (data[f.key] = form.elements[f.key].value));
    data.country = form.elements.country.value;
    data.make_default = Boolean(form.elements.make_default && form.elements.make_default.checked);
    return data;
  },

  /** The address as printed on a parcel, with the phone number. */
  lines(address) {
    return `${address.lines.map(escapeHtml).join("<br>")}${
      address.phone ? `<br><span class="muted">${escapeHtml(address.phone)}</span>` : ""
    }`;
  },
};
