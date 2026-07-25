document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-confirm]").forEach((el) => {
    el.addEventListener("submit", (event) => {
      if (!window.confirm(el.dataset.confirm)) {
        event.preventDefault();
      }
    });
  });

  initSortableTables();
});

// Any <table data-sortable> gets a filter box injected above it and click-to-sort
// headers — entirely client-side (no server round-trip, no build step), which fits
// this app's list sizes and its "no Node/build step" design elsewhere. Mark a header
// data-no-sort to exclude it (e.g. a trailing actions column with no meaningful order),
// or data-type="number" for columns that must sort numerically rather than as text
// (amounts, counts) — plain text columns already sort correctly with numeric-aware
// locale comparison, including ISO-formatted dates, so no separate "date" type exists.
function initSortableTables() {
  document.querySelectorAll("table[data-sortable]").forEach((table) => {
    const tbody = table.tBodies[0];
    if (!tbody) return;
    const rows = Array.from(tbody.rows);

    const search = document.createElement("input");
    search.type = "search";
    search.className = "table-search";
    search.placeholder = "Filter...";
    search.setAttribute("aria-label", "Filter table rows");
    table.parentNode.insertBefore(search, table);

    search.addEventListener("input", () => {
      const query = search.value.trim().toLowerCase();
      rows.forEach((row) => {
        row.style.display = !query || row.textContent.toLowerCase().includes(query) ? "" : "none";
      });
    });

    if (!table.tHead) return;
    const headers = Array.from(table.tHead.rows[0].cells);
    headers.forEach((th, index) => {
      if (th.hasAttribute("data-no-sort") || !th.textContent.trim()) return;
      th.classList.add("sortable-col");
      th.tabIndex = 0;

      const sort = () => {
        const nextDir = th.dataset.sortDir === "asc" ? "desc" : "asc";
        headers.forEach((h) => {
          delete h.dataset.sortDir;
          h.classList.remove("sort-asc", "sort-desc");
        });
        th.dataset.sortDir = nextDir;
        th.classList.add(nextDir === "asc" ? "sort-asc" : "sort-desc");

        const isNumber = th.dataset.type === "number";
        const factor = nextDir === "asc" ? 1 : -1;
        const sorted = rows.slice().sort((a, b) => {
          const av = (a.cells[index] ? a.cells[index].textContent : "").trim();
          const bv = (b.cells[index] ? b.cells[index].textContent : "").trim();
          if (isNumber) {
            const an = parseFloat(av.replace(/[^0-9.-]/g, ""));
            const bn = parseFloat(bv.replace(/[^0-9.-]/g, ""));
            return factor * ((isNaN(an) ? -Infinity : an) - (isNaN(bn) ? -Infinity : bn));
          }
          return factor * av.localeCompare(bv, undefined, { numeric: true, sensitivity: "base" });
        });
        sorted.forEach((row) => tbody.appendChild(row));
      };

      th.addEventListener("click", sort);
      th.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          sort();
        }
      });
    });
  });
}
