
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll('[id^="transkription-"]').forEach((fenster) => {
    const griff = fenster.querySelector('[id^="griff-"]');
    if (!griff) return;

    let startX, startY, links, oben;
    let dragging = false;

    griff.style.touchAction = "none";

    griff.addEventListener("pointerdown", (e) => {
      if (e.target.closest("button")) return;

      const rect = fenster.getBoundingClientRect();

      startX = e.clientX;
      startY = e.clientY;
      links = rect.left;
      oben = rect.top;

      dragging = true;
      griff.setPointerCapture(e.pointerId);
    });

    griff.addEventListener("pointermove", (e) => {
      if (!dragging) return;

      const x = links + e.clientX - startX;
      const y = oben + e.clientY - startY;

      fenster.style.left =
        Math.max(0, Math.min(x, window.innerWidth - fenster.offsetWidth)) + "px";

      fenster.style.top =
        Math.max(0, Math.min(y, window.innerHeight - griff.offsetHeight)) + "px";

      fenster.style.right = "auto";
    });

    griff.addEventListener("pointerup", () => {
      dragging = false;
    });

    griff.addEventListener("pointercancel", () => {
      dragging = false;
    });
  });
});
