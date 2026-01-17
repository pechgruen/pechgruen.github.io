(() => {
  /**
   * Bindet die Overlay-Logik pro .sg-section.
   * - Stelzengrün: 1 Overlay (.sg-overlay)
   * - Doglasgrün: 2 Overlays (.sg-overlay[data-sg-layer="0|1"]) + Buttons [data-sg-layer-set]
   */
  function bind(root) {
    const overlays = Array.from(root.querySelectorAll(".sg-overlay"));
    const slider = root.querySelector(".sg-range");
    const val = root.querySelector(".sg-val");

    // Stelzengrün-Buttons (0/100)
    const opacityButtons = root.querySelectorAll("[data-sg-set]");

    // Doglasgrün-Buttons (Layer Auswahl)
    const layerButtons = root.querySelectorAll("[data-sg-layer-set]");

    if (overlays.length === 0 || !slider) return;

    let activeLayer = 0;

    function clampPct(pct) {
      return Math.max(0, Math.min(100, Number(pct)));
    }

    function setActiveLayer(layerIdx) {
      const idx = Number(layerIdx);
      if (Number.isNaN(idx)) return;
      activeLayer = Math.max(0, Math.min(overlays.length - 1, idx));

      // Layer-Buttons aria-pressed aktualisieren
      layerButtons.forEach((b) => {
        const target = Number(b.getAttribute("data-sg-layer-set") || "0");
        b.setAttribute("aria-pressed", target === activeLayer ? "true" : "false");
      });

      // sicherstellen, dass nur aktives Overlay sichtbar ist (entsprechend Slider)
      setOpacity(slider.value);
    }

    function setOpacity(pct) {
      const p = clampPct(pct);

      overlays.forEach((img, i) => {
        img.style.opacity = i === activeLayer ? String(p / 100) : "0";
      });

      slider.value = String(p);
      if (val) val.textContent = `${p}%`;

      // Stelzengrün-Buttons (0/100) aria-pressed aktualisieren
      opacityButtons.forEach((b) => {
        const target = Number(b.getAttribute("data-sg-set") || "0");
        b.setAttribute("aria-pressed", target === p ? "true" : "false");
      });
    }

    function onKey(e, fn) {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        fn();
      }
    }

    slider.addEventListener("input", () => setOpacity(slider.value));

    // Stelzengrün: Buttons setzen Opacity direkt auf 0/100
    opacityButtons.forEach((b) => {
      const which = Number(b.getAttribute("data-sg-set") || "0");
      b.addEventListener("click", () => setOpacity(which));
      b.addEventListener("keydown", (e) => onKey(e, () => setOpacity(which)));
    });

    // Doglasgrün: Buttons wählen Layer, Opacity bleibt (Sliderwert)
    layerButtons.forEach((b) => {
      const which = Number(b.getAttribute("data-sg-layer-set") || "0");
      b.addEventListener("click", () => setActiveLayer(which));
      b.addEventListener("keydown", (e) => onKey(e, () => setActiveLayer(which)));
    });

    // init Opacity
    const initialAttr = root.getAttribute("data-sg-initial");
    const initial =
      initialAttr !== null ? Number(initialAttr) :
      slider.value !== "" ? Number(slider.value) :
      0;

    // init Layer (nur relevant, wenn mehrere Overlays existieren)
    const layerInitialAttr = root.getAttribute("data-sg-layer-initial");
    const initialLayer =
      layerInitialAttr !== null ? Number(layerInitialAttr) : 0;

    activeLayer = 0;
    if (overlays.length > 1) {
      setActiveLayer(initialLayer);
    } else {
      // Stelzengrün: Layer 0 fix
      activeLayer = 0;
    }

    // Startzustand: wie bei dir gewünscht definiert
    setOpacity(initial);
  }

  document.querySelectorAll(".sg-section").forEach(bind);
})();
