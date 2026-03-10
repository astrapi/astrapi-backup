// Dark Mode
function toggleDarkMode() {
    document.documentElement.classList.toggle('light-mode');
    localStorage.setItem('lightMode', document.documentElement.classList.contains('light-mode') ? '1' : '0');
}

function initializeDarkMode() {
    if (localStorage.getItem('lightMode') === '1') {
        document.documentElement.classList.add('light-mode');
    }
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
    initializeDarkMode();
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
