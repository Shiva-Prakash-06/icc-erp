// OIA Project Intelligence Platform - Common Javascript Controller

document.addEventListener('DOMContentLoaded', function() {
    document.documentElement.classList.add('has-ui-controller');

    // Presentation-only shell preference. Navigation and authorization remain
    // server-rendered and complete regardless of this enhancement.
    const railToggle = document.querySelector('[data-rail-toggle]');
    const railKey = 'oia.ui.rail-collapsed';
    function setRail(collapsed) {
        document.documentElement.classList.toggle('is-rail-collapsed', collapsed);
        if (railToggle) {
            railToggle.setAttribute('aria-pressed', String(collapsed));
            railToggle.setAttribute('aria-label', collapsed ? 'Expand navigation' : 'Collapse navigation');
        }
    }
    try { setRail(window.localStorage.getItem(railKey) === 'true'); } catch (_) { setRail(false); }
    if (railToggle) {
        railToggle.addEventListener('click', function() {
            const collapsed = !document.documentElement.classList.contains('is-rail-collapsed');
            setRail(collapsed);
            try { window.localStorage.setItem(railKey, String(collapsed)); } catch (_) { /* Preference persistence is optional. */ }
            document.dispatchEvent(new CustomEvent('oia:rail-change', {detail: {collapsed: collapsed}}));
        });
    }

    // Flask-WTF validates every browser mutation. Injecting the server-issued
    // token centrally also protects legacy forms while they are migrated to
    // explicit form classes.
    const csrfMeta = document.querySelector('meta[name="csrf-token"]');
    if (csrfMeta) {
        document.querySelectorAll('form[method="POST"], form[method="post"]').forEach(function(form) {
            if (!form.querySelector('input[name="csrf_token"]')) {
                const input = document.createElement('input');
                input.type = 'hidden';
                input.name = 'csrf_token';
                input.value = csrfMeta.content;
                form.appendChild(input);
            }
        });
    }
    
    document.querySelectorAll('[data-ui-dismiss="alert"]').forEach(function(button) {
        button.addEventListener('click', function() {
            const alert = button.closest('.alert');
            if (alert) alert.remove();
        });
    });

    // Transient positive feedback may dismiss; warnings and errors persist.
    document.querySelectorAll('.alert-success.alert-dismissible, .alert-info.alert-dismissible').forEach(function(alert) {
        setTimeout(function() { if (alert.isConnected) alert.remove(); }, 5000);
    });

    // Accessible mobile navigation drawer.
    const drawer = document.getElementById('mobileNavDrawer');
    const drawerScrim = document.querySelector('[data-ui-drawer-close].drawer-scrim');
    let drawerTrigger = null;
    function setDrawer(open, trigger) {
        if (!drawer) return;
        if (trigger) drawerTrigger = trigger;
        drawer.classList.toggle('is-open', open);
        drawer.setAttribute('aria-hidden', String(!open));
        if (drawerScrim) drawerScrim.classList.toggle('is-open', open);
        document.querySelectorAll('[data-ui-drawer-toggle]').forEach(function(button) { button.setAttribute('aria-expanded', String(open)); });
        document.body.style.overflow = open ? 'hidden' : '';
        if (open) {
            const focusTarget = drawer.querySelector('button, a, input, select, textarea');
            if (focusTarget) focusTarget.focus();
        } else if (drawerTrigger) {
            drawerTrigger.focus();
        }
    }
    document.querySelectorAll('[data-ui-drawer-toggle]').forEach(function(button) {
        button.addEventListener('click', function() {
            if (drawer) setDrawer(!drawer.classList.contains('is-open'), button);
        });
    });
    document.querySelectorAll('[data-ui-drawer-close]').forEach(function(button) {
        button.addEventListener('click', function() { setDrawer(false); });
    });

    // Server-authorized notification preview sheet.
    const notificationPanel = document.getElementById('notificationPanel');
    const notificationScrim = document.querySelector('[data-notification-close].notification-scrim');
    let notificationTrigger = null;
    function setNotifications(open, trigger) {
        if (!notificationPanel) return;
        if (trigger) notificationTrigger = trigger;
        notificationPanel.classList.toggle('is-open', open);
        notificationPanel.setAttribute('aria-hidden', String(!open));
        if (notificationScrim) notificationScrim.classList.toggle('is-open', open);
        document.querySelectorAll('[data-notification-toggle]').forEach(function(button) { button.setAttribute('aria-expanded', String(open)); });
        if (open) {
            const focusTarget = notificationPanel.querySelector('button, a');
            if (focusTarget) focusTarget.focus();
        } else if (notificationTrigger) {
            notificationTrigger.focus();
        }
        document.dispatchEvent(new CustomEvent('oia:notification-change', {detail: {open: open}}));
    }
    document.querySelectorAll('[data-notification-toggle]').forEach(function(button) {
        button.addEventListener('click', function() { setNotifications(!notificationPanel.classList.contains('is-open'), button); });
    });
    document.querySelectorAll('[data-notification-close]').forEach(function(control) {
        control.addEventListener('click', function() { setNotifications(false); });
    });

    // Native disclosure controller replacing Bootstrap Collapse.
    document.querySelectorAll('[data-ui-toggle="disclosure"]').forEach(function(button) {
        const selector = button.getAttribute('data-ui-target');
        const target = selector ? document.querySelector(selector) : null;
        if (!target) return;
        button.addEventListener('click', function() {
            const expanded = button.getAttribute('aria-expanded') === 'true';
            const parentSelector = target.getAttribute('data-ui-parent');
            if (!expanded && parentSelector) {
                document.querySelectorAll(`${parentSelector} .aurora-collapse.is-open`).forEach(function(sibling) {
                    if (sibling === target) return;
                    sibling.classList.remove('is-open');
                    const siblingButton = document.querySelector(`[data-ui-target="#${sibling.id}"]`);
                    if (siblingButton) siblingButton.setAttribute('aria-expanded', 'false');
                });
            }
            target.classList.toggle('is-open', !expanded);
            button.classList.toggle('is-collapsed', expanded);
            button.setAttribute('aria-expanded', String(!expanded));
        });
    });

    // Lightweight dropdown behavior with Escape and outside-click dismissal.
    document.querySelectorAll('[data-ui-toggle="dropdown"]').forEach(function(button) {
        const menu = button.parentElement && button.parentElement.querySelector('.aurora-menu__popover');
        if (!menu) return;
        button.addEventListener('click', function(event) {
            event.stopPropagation();
            const open = menu.classList.toggle('is-open');
            button.setAttribute('aria-expanded', String(open));
        });
    });
    document.addEventListener('click', function() {
        document.querySelectorAll('.aurora-menu__popover.is-open').forEach(function(menu) {
            menu.classList.remove('is-open');
            const toggle = menu.parentElement && menu.parentElement.querySelector('[data-ui-toggle="dropdown"]');
            if (toggle) toggle.setAttribute('aria-expanded', 'false');
        });
    });

    // Confirmation is progressive enhancement; form actions and payloads stay native.
    document.querySelectorAll('[data-confirm]').forEach(function(control) {
        control.addEventListener('click', function(event) {
            if (!window.confirm(control.getAttribute('data-confirm'))) event.preventDefault();
        });
    });

    document.querySelectorAll('form[data-confirm-submit]').forEach(function(form) {
        form.addEventListener('submit', function(event) {
            if (!window.confirm(form.getAttribute('data-confirm-submit'))) event.preventDefault();
        });
    });

    // Filter selectors submit through a shared progressive-enhancement hook.
    // Their form action, query-string field name, and server-side fallback stay native.
    document.querySelectorAll('[data-ui-auto-submit]').forEach(function(control) {
        control.addEventListener('change', function() {
            if (control.form) control.form.requestSubmit();
        });
    });

    // Server-provided percentages are treated as data and clamped before they
    // become presentation, avoiding arbitrary inline style injection.
    document.querySelectorAll('[data-progress]').forEach(function(progress) {
        const value = Number.parseFloat(progress.getAttribute('data-progress'));
        const normalized = Math.min(100, Math.max(0, Number.isFinite(value) ? value : 0));
        progress.style.width = '100%';
        progress.style.transform = `scaleX(${normalized / 100})`;
        progress.style.transformOrigin = 'left center';
    });

    // Prototype-style project views use the same server-rendered records and
    // introduce no route, mutation, or lifecycle behavior.
    const projectViewKey = 'oia.ui.projects-view';
    const viewButtons = document.querySelectorAll('[data-project-view]');
    const views = document.querySelectorAll('[data-project-view-panel]');
    function setProjectView(name) {
        const allowed = ['cards', 'board', 'table'];
        const next = allowed.includes(name) ? name : 'cards';
        viewButtons.forEach(function(button) {
            const active = button.getAttribute('data-project-view') === next;
            button.classList.toggle('is-active', active);
            button.setAttribute('aria-pressed', String(active));
        });
        views.forEach(function(view) { view.classList.toggle('is-active', view.getAttribute('data-project-view-panel') === next); });
        try { window.localStorage.setItem(projectViewKey, next); } catch (_) { /* Preference persistence is optional. */ }
        document.dispatchEvent(new CustomEvent('oia:project-view-change', {detail: {view: next}}));
    }
    if (viewButtons.length && views.length) {
        let initialView = 'cards';
        try { initialView = window.localStorage.getItem(projectViewKey) || 'cards'; } catch (_) { /* Use server-first card view. */ }
        setProjectView(initialView);
        viewButtons.forEach(function(button) { button.addEventListener('click', function() { setProjectView(button.getAttribute('data-project-view')); }); });
    }

    // Cursor light and shallow tilt are decorative, desktop-only enhancements.
    const finePointer = window.matchMedia('(hover: hover) and (pointer: fine)');
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    if (finePointer.matches && !reducedMotion.matches) {
        document.querySelectorAll('.aurora-card__value, .display-6').forEach(function(metric) {
            const card = metric.closest('.aurora-card, .aurora-card--padded');
            if (!card) return;
            card.classList.add('kpi-card');
            card.setAttribute('data-glass-spotlight', '');
            card.addEventListener('pointermove', function(event) {
                const rect = card.getBoundingClientRect();
                const x = ((event.clientX - rect.left) / rect.width) * 100;
                const y = ((event.clientY - rect.top) / rect.height) * 100;
                card.style.setProperty('--spot-x', `${x}%`);
                card.style.setProperty('--spot-y', `${y}%`);
                card.style.setProperty('--tilt-x', `${((x - 50) / 50) * 1.2}deg`);
                card.style.setProperty('--tilt-y', `${((50 - y) / 50) * 1.2}deg`);
            });
            card.addEventListener('pointerleave', function() {
                card.style.removeProperty('--tilt-x');
                card.style.removeProperty('--tilt-y');
            });
        });
    }

    document.querySelectorAll('form').forEach(function(form) {
        form.addEventListener('submit', function(event) {
            if (event.defaultPrevented || !form.checkValidity()) return;
            const submitter = event.submitter;
            if (!submitter || submitter.hasAttribute('data-no-busy')) return;
            submitter.setAttribute('aria-disabled', 'true');
            submitter.classList.add('is-busy');
        });
    });

    function openCommand(trigger) {
        document.dispatchEvent(new CustomEvent('aurora:command-open', {detail: {trigger: trigger}}));
    }
    document.querySelectorAll('[data-command-open]').forEach(function(button) {
        button.addEventListener('click', function() { openCommand(button); });
    });
    document.addEventListener('keydown', function(event) {
        if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
            event.preventDefault();
            openCommand(document.activeElement);
        }
        if (event.key === 'Escape' && drawer && drawer.classList.contains('is-open')) setDrawer(false);
        if (event.key === 'Escape' && notificationPanel && notificationPanel.classList.contains('is-open')) setNotifications(false);
    });

    // Conditional fields on registration keep all server-owned names intact.
    const roleSelect = document.querySelector('[name="preferred_role"]');
    const volunteerFields = document.querySelector('[data-volunteer-fields]');
    if (roleSelect && volunteerFields) {
        const syncRoleFields = function() {
            const visible = roleSelect.value === 'Volunteer' || roleSelect.value === 'Buddy';
            volunteerFields.hidden = !visible;
        };
        roleSelect.addEventListener('change', syncRoleFields);
        syncRoleFields();
    }

    const projectChartData = document.getElementById('project-chart-data');
    if (projectChartData && window.Chart) {
        try { OIACharts.initProjectCharts(JSON.parse(projectChartData.textContent)); } catch (_) { /* Server content remains usable without charts. */ }
    }
});

if ('serviceWorker' in navigator) {
    window.addEventListener('load', function() {
        navigator.serviceWorker.register('/static/sw.js').catch(function() {
            // Installation is optional; the authenticated application remains fully usable online.
        });
    });
}

function uiToken(name, fallback) {
    const value = window.getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return value || fallback;
}

const OIAChartTheme = {
    get primary() { return uiToken('--color-primary', '#0369a1'); },
    get primarySoft() { return 'rgb(14 165 233 / 48%)'; },
    get secondary() { return uiToken('--color-secondary', '#2563eb'); },
    get info() { return uiToken('--color-info', '#0284c7'); },
    get infoSoft() { return 'rgb(56 189 248 / 48%)'; },
    get success() { return uiToken('--color-success', '#047857'); },
    get successSoft() { return 'rgb(5 150 105 / 42%)'; },
    get warning() { return uiToken('--color-warning', '#b45309'); },
    get danger() { return uiToken('--color-danger', '#b91c1c'); },
    get surface() { return uiToken('--color-surface-1', '#ffffff'); },
    get border() { return uiToken('--color-border', '#bae6fd'); },
    get muted() { return uiToken('--color-text-tertiary', '#475569'); },
    get text() { return uiToken('--color-text', '#0f172a'); },
    font: 'Inter, ui-sans-serif, system-ui, sans-serif'
};

// Chart.js helper methods for dynamic analytics rendering
const OIACharts = {
    // 1. Global Dashboard Chart loaders
    initGlobalCharts: function(data) {
        // Campuses Distribution Bar Chart
        const campusCtx = document.getElementById('campusDistributionChart');
        if (campusCtx && data.campuses && data.campusCounts) {
            new Chart(campusCtx, {
                type: 'bar',
                data: {
                    labels: data.campuses,
                    datasets: [{
                        label: 'Projects',
                        data: data.campusCounts,
                        backgroundColor: OIAChartTheme.infoSoft,
                        borderColor: OIAChartTheme.info,
                        borderWidth: 1,
                        borderRadius: 6
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false }
                    },
                    scales: {
                        y: {
                            grid: { color: OIAChartTheme.border },
                            ticks: { color: OIAChartTheme.muted, precision: 0 }
                        },
                        x: {
                            grid: { display: false },
                            ticks: { color: OIAChartTheme.muted }
                        }
                    }
                }
            });
        }

        // Program Type Doughnut Chart (ICC vs IGP)
        const progCtx = document.getElementById('programTypeChart');
        if (progCtx && data.programs && data.programCounts) {
            new Chart(progCtx, {
                type: 'doughnut',
                data: {
                    labels: data.programs,
                    datasets: [{
                        data: data.programCounts,
                        backgroundColor: [OIAChartTheme.primary, OIAChartTheme.info],
                        borderColor: OIAChartTheme.surface,
                        borderWidth: 2
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            position: 'bottom',
                            labels: { color: OIAChartTheme.text, font: { family: OIAChartTheme.font } }
                        }
                    },
                    cutout: '70%'
                }
            });
        }

        // Project Status Pie Chart
        const statusCtx = document.getElementById('projectStatusChart');
        if (statusCtx && data.statuses && data.statusCounts) {
            const colors = {
                'Active': OIAChartTheme.success,
                'Planned': OIAChartTheme.warning,
                'Completed': OIAChartTheme.info,
                'Draft': OIAChartTheme.muted,
                'Archived': OIAChartTheme.danger
            };
            
            const backgroundColors = data.statuses.map(s => colors[s] || OIAChartTheme.muted);

            new Chart(statusCtx, {
                type: 'pie',
                data: {
                    labels: data.statuses,
                    datasets: [{
                        data: data.statusCounts,
                        backgroundColor: backgroundColors,
                        borderColor: OIAChartTheme.surface,
                        borderWidth: 2
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            position: 'bottom',
                            labels: { color: OIAChartTheme.text, font: { family: OIAChartTheme.font } }
                        }
                    }
                }
            });
        }
    },

    // 2. Project Workspace Chart loaders
    initProjectCharts: function(data) {
        // Participant Type Breakdown (Doughnut)
        const partCtx = document.getElementById('participantBreakdownChart');
        if (partCtx && data.partTypes && data.partCounts) {
            new Chart(partCtx, {
                type: 'doughnut',
                data: {
                    labels: data.partTypes,
                    datasets: [{
                        data: data.partCounts,
                        backgroundColor: [OIAChartTheme.primary, OIAChartTheme.info, OIAChartTheme.success, OIAChartTheme.warning, OIAChartTheme.secondary, OIAChartTheme.danger],
                        borderColor: OIAChartTheme.surface,
                        borderWidth: 2
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            position: 'bottom',
                            labels: { color: OIAChartTheme.text, font: { family: OIAChartTheme.font } }
                        }
                    },
                    cutout: '65%'
                }
            });
        }

        // Contributions Hours by Division (Bar Chart)
        const divCtx = document.getElementById('contributionDivisionChart');
        if (divCtx && data.divisions && data.hours) {
            new Chart(divCtx, {
                type: 'bar',
                data: {
                    labels: data.divisions,
                    datasets: [{
                        label: 'Approved Hours',
                        data: data.hours,
                        backgroundColor: OIAChartTheme.infoSoft,
                        borderColor: OIAChartTheme.info,
                        borderWidth: 1,
                        borderRadius: 4
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false }
                    },
                    scales: {
                        y: {
                            grid: { color: OIAChartTheme.border },
                            ticks: { color: OIAChartTheme.muted }
                        },
                        x: {
                            grid: { display: false },
                            ticks: { color: OIAChartTheme.muted }
                        }
                    }
                }
            });
        }

        // Feedback Rating Distribution (Bar Chart)
        const feedCtx = document.getElementById('feedbackDistributionChart');
        if (feedCtx && data.ratings && data.ratingCounts) {
            new Chart(feedCtx, {
                type: 'bar',
                data: {
                    labels: data.ratings,
                    datasets: [{
                        label: 'Submissions',
                        data: data.ratingCounts,
                        backgroundColor: OIAChartTheme.successSoft,
                        borderColor: OIAChartTheme.success,
                        borderWidth: 1,
                        borderRadius: 4
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false }
                    },
                    scales: {
                        y: {
                            grid: { color: OIAChartTheme.border },
                            ticks: { color: OIAChartTheme.muted, precision: 0 }
                        },
                        x: {
                            grid: { display: false },
                            ticks: { color: OIAChartTheme.muted }
                        }
                    }
                }
            });
        }
    }
};

// Explicit, read-only offline snapshots. The AES key lives only in
// sessionStorage, so browser restart/logout makes persisted ciphertext unusable.
window.ICCOffline = (() => {
    const DB_NAME = 'icc-erp-offline-v1';
    const STORE = 'encrypted-snapshots';
    const KEY_NAME = 'icc-erp-offline-key';

    const bytesToBase64 = bytes => btoa(String.fromCharCode(...new Uint8Array(bytes)));
    const base64ToBytes = value => Uint8Array.from(atob(value), char => char.charCodeAt(0));

    async function key() {
        let encoded = sessionStorage.getItem(KEY_NAME);
        if (!encoded) {
            const raw = crypto.getRandomValues(new Uint8Array(32));
            encoded = bytesToBase64(raw);
            sessionStorage.setItem(KEY_NAME, encoded);
        }
        return crypto.subtle.importKey('raw', base64ToBytes(encoded), 'AES-GCM', false, ['encrypt', 'decrypt']);
    }

    function database() {
        return new Promise((resolve, reject) => {
            const request = indexedDB.open(DB_NAME, 1);
            request.onupgradeneeded = () => request.result.createObjectStore(STORE);
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }

    async function put(value) {
        const db = await database();
        return new Promise((resolve, reject) => {
            const tx = db.transaction(STORE, 'readwrite');
            tx.objectStore(STORE).put(value, 'current');
            tx.oncomplete = resolve;
            tx.onerror = () => reject(tx.error);
        });
    }

    async function get() {
        const db = await database();
        return new Promise((resolve, reject) => {
            const request = db.transaction(STORE).objectStore(STORE).get('current');
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }

    async function refresh() {
        const response = await fetch('/api/v1/offline-snapshot', {credentials: 'same-origin', cache: 'no-store'});
        if (!response.ok) throw new Error('Offline snapshot could not be refreshed.');
        const snapshot = await response.json();
        const iv = crypto.getRandomValues(new Uint8Array(12));
        const plaintext = new TextEncoder().encode(JSON.stringify(snapshot.data));
        const ciphertext = await crypto.subtle.encrypt({name: 'AES-GCM', iv}, await key(), plaintext);
        await put({iv: bytesToBase64(iv), ciphertext: bytesToBase64(ciphertext), expiresAt: snapshot.data.expires_at});
        return snapshot.data;
    }

    async function read() {
        const stored = await get();
        if (!stored || !sessionStorage.getItem(KEY_NAME) || new Date(stored.expiresAt) <= new Date()) return null;
        try {
            const plaintext = await crypto.subtle.decrypt(
                {name: 'AES-GCM', iv: base64ToBytes(stored.iv)},
                await key(),
                base64ToBytes(stored.ciphertext)
            );
            return JSON.parse(new TextDecoder().decode(plaintext));
        } catch (_) {
            return null;
        }
    }

    async function purge() {
        sessionStorage.removeItem(KEY_NAME);
        const db = await database();
        return new Promise(resolve => {
            const tx = db.transaction(STORE, 'readwrite');
            tx.objectStore(STORE).clear();
            tx.oncomplete = resolve;
        });
    }

    document.querySelectorAll('a[href$="/logout"]').forEach(link => link.addEventListener('click', () => purge()));
    return {refresh, read, purge};
})();
