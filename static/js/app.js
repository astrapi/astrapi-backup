// Dark Mode Functions
function toggleDarkMode() {
    const html = document.documentElement;
    const isDark = html.classList.contains('dark');
    
    if (isDark) {
        html.classList.remove('dark');
        localStorage.setItem('darkMode', 'false');
    } else {
        html.classList.add('dark');
        localStorage.setItem('darkMode', 'true');
    }
}

function initializeDarkMode() {
    const savedMode = localStorage.getItem('darkMode');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    
    if (savedMode === 'true' || (savedMode === null && prefersDark)) {
        document.documentElement.classList.add('dark');
    }
}

// Initialize dark mode and notifications on page load
document.addEventListener('DOMContentLoaded', function() {
    initializeDarkMode();
    updateActiveNav();
    //initializeNotifications();
});

document.body.addEventListener("htmx:afterSwap", (evt) => {
    if (evt.detail.target.id === "main-content") {
        updateActiveNav();
    }
});

function updateActiveNav() {
    const path = window.location.pathname.replace(/^\/+/, "");

    document.querySelectorAll(".nav-item").forEach(btn => {
        const key = btn.id.replace("nav-", "");
        const isActive = (path === key);

        btn.classList.toggle("bg-blue-100", isActive);
        btn.classList.toggle("text-blue-700", isActive);
        btn.classList.toggle("dark:bg-gray-700", isActive);
        btn.classList.toggle("dark:text-blue-400", isActive);
        btn.classList.toggle("font-semibold", isActive);
    });
}

