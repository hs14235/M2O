// Applies a saved Light or Dark choice, and calm motion, before the first paint. A
// separate file because the content security policy allows no inline scripts.
(function () {
  var root = document.documentElement;
  try {
    var theme = localStorage.getItem("m2o-theme");
    if (theme === "light" || theme === "dark") root.dataset.theme = theme;
    // Without this, entrance animations of the first screen would play before React
    // applies the saved calm preference.
    if (localStorage.getItem("m2o-calm") === "true") root.dataset.motion = "calm";
  } catch (error) {
    /* Storage unavailable: the system settings apply. */
  }
  if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches)
    root.dataset.motion = "calm";
})();
