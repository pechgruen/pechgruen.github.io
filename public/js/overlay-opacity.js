(() => {
  /**
   * Bindet die Overlay-Logik pro .sg-section.
   * Wichtig: Alles wird relativ zu root gesucht, damit andere Slider auf der Seite egal sind.
   */
  function bind(root) {
    const overlay = root.querySelector(".sg-overlay");
    const slider = root.querySelector(".sg-range");
    const val = root.querySelector(".sg-val");
    const buttons = root.querySelectorAll("[data-sg-set]");

    if (!overlay || !slider) return;

    function setOpacity(pct) {
      const p = Math.max(0, Math.min(100, Number(pct)));
      overlay.style.opacity = String(p / 100);
      slider.value = String(p);
      if (val) val.textContent = `${p}%`;

      buttons.forEach((b) => {
        const target = Number(b.getAttribute("data-sg-set") || "0");
        b.setAttribute("aria-pressed", target === p ? "true" : "false");
      });
    }

    function activate(pct) {
      setOpacity(pct);
    }

    function onKey(e, pct) {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        activate(pct);
      }
    }

    slider.addEventListener("input", () => setOpacity(slider.value));

    buttons.forEach((b) => {
      const which = Number(b.getAttribute("data-sg-set") || "0");
      b.addEventListener("click", () => activate(which));
      b.addEventListener("keydown", (e) => onKey(e, which));
    });

    // init: bevorzugt data-sg-initial, sonst slider.value, default 0
    const initialAttr = root.getAttribute("data-sg-initial");
    const initial =
      initialAttr !== null ? Number(initialAttr) :
      slider.value !== "" ? Number(slider.value) :
      0;

    setOpacity(0);
  }

  document.querySelectorAll(".sg-section").forEach(bind);
})();
