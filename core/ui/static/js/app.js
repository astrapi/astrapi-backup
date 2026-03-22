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

// ── Spaltenbreiten-Resize ─────────────────────────────────────────────────────
function initColResize(table) {
    const module = table.dataset.module;
    if (!module) return;
    const saved = JSON.parse(table.dataset.colWidths || '{}');
    const headers = Array.from(table.querySelectorAll('thead th'));
    const last = headers.length - 1;

    headers.forEach((th, i) => {
        if (i === 0 || i === last || i === last - 1) return;
        if (saved[i] !== undefined) th.style.width = saved[i] + 'px';

        const handle = document.createElement('span');
        handle.className = 'col-resize-handle';
        th.appendChild(handle);

        handle.addEventListener('mousedown', e => {
            e.preventDefault();
            const startX = e.clientX;
            const startW = th.offsetWidth;
            handle.classList.add('resizing');

            const onMove = e => {
                th.style.width = Math.max(40, startW + e.clientX - startX) + 'px';
            };
            const onUp = () => {
                handle.classList.remove('resizing');
                document.removeEventListener('mousemove', onMove);
                document.removeEventListener('mouseup', onUp);
                const widths = {};
                headers.forEach((h, idx) => {
                    if (idx === 0 || idx === last || idx === last - 1) return;
                    widths[idx] = h.offsetWidth;
                });
                fetch(`/ui/preferences/col-widths/${module}`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({widths}),
                });
            };
            document.addEventListener('mousemove', onMove);
            document.addEventListener('mouseup', onUp);
        });
    });
}

function initAllColResize(root) {
    (root || document).querySelectorAll('.ds-list-table[data-module]').forEach(initColResize);
}

document.addEventListener('DOMContentLoaded', () => initAllColResize());
document.body.addEventListener('htmx:afterSwap', e => initAllColResize(e.detail.target));

// ── Karten-/Listenansicht Toggle ─────────────────────────────────────────────
function viewToggle(module) {
    return {
        view: localStorage.getItem(`view:${module}`) || 'card',
        setView(v) {
            this.view = v;
            localStorage.setItem(`view:${module}`, v);
        },
    };
}
