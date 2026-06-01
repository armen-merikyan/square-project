const siteHeader = document.querySelector(".site-header");
const menuToggle = document.querySelector(".menu-toggle");
const primaryNavigation = document.querySelector("#primaryNavigation");
const mobileMenuQuery = window.matchMedia("(max-width: 620px)");

function setMenuOpen(isOpen) {
  if (!siteHeader || !menuToggle || !primaryNavigation) {
    return;
  }

  siteHeader.classList.toggle("is-menu-open", isOpen);
  menuToggle.setAttribute("aria-expanded", String(isOpen));
  menuToggle.setAttribute("aria-label", isOpen ? "Close navigation menu" : "Open navigation menu");
}

if (siteHeader && menuToggle && primaryNavigation) {
  menuToggle.addEventListener("click", () => {
    setMenuOpen(!siteHeader.classList.contains("is-menu-open"));
  });

  primaryNavigation.addEventListener("click", (event) => {
    if (event.target.closest("a")) {
      setMenuOpen(false);
    }
  });

  document.addEventListener("click", (event) => {
    if (!mobileMenuQuery.matches || !siteHeader.classList.contains("is-menu-open")) {
      return;
    }

    if (!siteHeader.contains(event.target)) {
      setMenuOpen(false);
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      setMenuOpen(false);
      menuToggle.focus();
    }
  });

  mobileMenuQuery.addEventListener("change", (event) => {
    if (!event.matches) {
      setMenuOpen(false);
    }
  });
}
