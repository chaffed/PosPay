document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-confirm]").forEach((el) => {
    el.addEventListener("submit", (event) => {
      if (!window.confirm(el.dataset.confirm)) {
        event.preventDefault();
      }
    });
  });

  // A <select>/<input> with data-auto-submit submits its enclosing form on change --
  // used instead of an inline onchange="..." attribute so the app can run a strict,
  // nonce-based script-src Content-Security-Policy (see web/security_headers.py) with no
  // 'unsafe-inline'. data-auto-submit="request" uses requestSubmit() instead of submit()
  // where a route relies on the submit button/native validation running (submit() skips
  // both); plain data-auto-submit uses the plain, no-validation submit().
  document.querySelectorAll("[data-auto-submit]").forEach((el) => {
    el.addEventListener("change", () => {
      if (el.dataset.autoSubmit === "request") {
        el.form.requestSubmit();
      } else {
        el.form.submit();
      }
    });
  });

  initSortableTables();
  initHelpDialog();
  initNavToggle();
  initBannerCarousel();
});

// templates/partials/_banner.html renders one .banner-slide per message that's actually
// set (tenant's own, and/or the logged-in user's own customer's) -- 0 or 1 slides need no
// rotation at all (a no-op here; CSS shows the lone slide, if any, on its own). With 2,
// auto-advance between them (tenant's shows first, per _banner.html's own slide order),
// looping indefinitely; the dots are clickable and reset the timer on manual pick rather
// than fighting it. Uses inline style.display (not a CSS "hide unless .active" rule) so a
// single-slide carousel still renders correctly with zero JS/CSS coordination needed.
function initBannerCarousel() {
  document.querySelectorAll("[data-banner-carousel]").forEach((carousel) => {
    const slides = Array.from(carousel.querySelectorAll(".banner-slide"));
    const dots = Array.from(carousel.querySelectorAll(".banner-dot"));
    if (slides.length < 2) return;

    let current = 0;
    let timer = null;

    const show = (index) => {
      current = index;
      slides.forEach((slide, i) => {
        slide.style.display = i === index ? "" : "none";
      });
      dots.forEach((dot, i) => dot.classList.toggle("active", i === index));
    };

    const startAutoAdvance = () => {
      if (timer) clearInterval(timer);
      timer = setInterval(() => show((current + 1) % slides.length), 8000);
    };

    dots.forEach((dot, i) => {
      dot.addEventListener("click", () => {
        show(i);
        startAutoAdvance();
      });
    });

    show(0);
    startAutoAdvance();
  });
}

// Mobile-only hamburger toggle (see base.html's .sidenav-header / #sidenav-panel and
// app.css's @media (max-width: 720px) rules) -- the button and panel only exist so this
// is a no-op at desktop widths where CSS keeps the panel always visible regardless of
// the "open" class. No "close on navigate" handling needed: this is a server-rendered
// multi-page app, so every link click is a full page load that resets the toggle state.
function initNavToggle() {
  const toggle = document.getElementById("nav-toggle");
  const panel = document.getElementById("sidenav-panel");
  if (!toggle || !panel) return;

  toggle.addEventListener("click", () => {
    const isOpen = panel.classList.toggle("open");
    toggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
  });
}

// Opt-in per page via base.html's help_title/help_body blocks — the button and
// <dialog> only render at all when a page defines help_body (see base.html), so this
// is a no-op on every page that doesn't.
function initHelpDialog() {
  const dialog = document.getElementById("page-help-dialog");
  const button = document.getElementById("page-help-button");
  if (!dialog || !button) return;

  button.addEventListener("click", () => dialog.showModal());
  const closeButton = dialog.querySelector(".help-close");
  if (closeButton) closeButton.addEventListener("click", () => dialog.close());

  // Native <dialog> doesn't close on backdrop click by itself — a click that lands on
  // the dialog element itself (not one of its content children) means the backdrop.
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
}

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
      th.setAttribute("role", "button");
      th.setAttribute("aria-sort", "none");

      const sort = () => {
        const nextDir = th.dataset.sortDir === "asc" ? "desc" : "asc";
        headers.forEach((h) => {
          delete h.dataset.sortDir;
          h.classList.remove("sort-asc", "sort-desc");
          h.setAttribute("aria-sort", "none");
        });
        th.dataset.sortDir = nextDir;
        th.classList.add(nextDir === "asc" ? "sort-asc" : "sort-desc");
        th.setAttribute("aria-sort", nextDir === "asc" ? "ascending" : "descending");

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
