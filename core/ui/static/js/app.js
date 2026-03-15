// Dark Mode – Fallback: localStorage nur wenn JS-Toggle benötigt wird
// (Server setzt .light-mode per class-Attribut; diese Funktion bleibt
// für Rückwärtskompatibilität und sofortigen Effekt nach Settings-Save)
function applyLightMode(value) {
    document.documentElement.classList.toggle('light-mode', value === '1' || value === true);
}

// Active Nav
function updateActiveNav() {
    const path = window.location.pathname.replace(/^\/+/, "") || "overview";
    document.querySelectorAll(".nav-item").forEach(btn => {
        const key = btn.id.replace("nav-", "");
        if (key) {
            btn.classList.toggle("active", path === key);
        }
    });
}

document.addEventListener('DOMContentLoaded', function() {
    updateActiveNav();
});

document.body.addEventListener("htmx:afterSwap", (evt) => {
    if (evt.detail.target.id === "main-content") {
        updateActiveNav();
    }
});

document.body.addEventListener("htmx:pushedIntoHistory", () => {
    updateActiveNav();
});
