// Applies a saved Light or Dark choice before the first paint. A separate file
// because the content security policy allows no inline scripts.
(function () {
  try {
    var theme = localStorage.getItem("m2o-theme");
    if (theme === "light" || theme === "dark") document.documentElement.dataset.theme = theme;
  } catch (error) {
    /* Storage unavailable: the system setting applies. */
  }
})();
