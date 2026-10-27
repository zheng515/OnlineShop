/* Product browsing and search (FR15, FR16). */

(function () {
  if (!requireRole("customer")) return;
  renderHeader("shop");

  const grid = document.getElementById("product-grid");
  const message = document.getElementById("search-message");
  const searchForm = document.getElementById("search-form");
  const searchInput = document.getElementById("search-input");
  const clearBtn = document.getElementById("clear-search");

  function render(products, query) {
    if (!products.length) {
      grid.innerHTML = `<div class="empty-state" style="grid-column: 1 / -1">
        <div class="icon">🔍</div>
        <p>${query ? `No products match “${escapeHtml(query)}”.` : "There are no products available right now."}</p>
        ${query ? '<button type="button" class="btn btn-secondary" id="show-all">Show all products</button>' : ""}
      </div>`;
      const showAll = document.getElementById("show-all");
      if (showAll) showAll.addEventListener("click", () => search(""));
      return;
    }
    grid.innerHTML = products
      .map(
        (p) => `
        <a class="card product-card" href="/product.html?id=${p.id}">
          <div class="image">
            <img src="${escapeHtml(p.image_url)}" alt="${escapeHtml(p.name)}" loading="lazy">
            ${p.in_stock ? "" : '<span class="ribbon">Out of stock</span>'}
          </div>
          <div class="info">
            <div class="name">${escapeHtml(p.name)}</div>
            <div class="price">${formatPrice(p.price)}</div>
          </div>
        </a>`
      )
      .join("");
  }

  async function search(query) {
    searchInput.value = query;
    clearBtn.classList.toggle("hidden", !query);
    const url = new URL(window.location);
    if (query) url.searchParams.set("q", query);
    else url.searchParams.delete("q");
    history.replaceState(null, "", url);

    try {
      const data = await api(`/api/products?q=${encodeURIComponent(query)}`);
      if (query) {
        showAlert(
          message,
          data.count
            ? `${data.count} product(s) found for “${query}”.`
            : `No products found for “${query}”. Try a different keyword.`,
          data.count ? "info" : "warning"
        );
      } else {
        clearAlert(message);
      }
      render(data.products, query);
    } catch (err) {
      grid.innerHTML = "";
      showAlert(message, err.errors);
    }
  }

  searchForm.addEventListener("submit", (e) => {
    e.preventDefault();
    search(searchInput.value.trim());
  });
  clearBtn.addEventListener("click", () => search(""));

  search((queryParam("q") || "").trim());
})();
