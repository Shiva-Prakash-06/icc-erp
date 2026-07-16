// OIA Project Intelligence Platform - Common Javascript Controller

document.addEventListener('DOMContentLoaded', function() {
    console.log("OIA Mission Control initialized.");

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
    
    // Auto-dismiss alert boxes after 5 seconds
    const alerts = document.querySelectorAll('.alert-dismissible');
    alerts.forEach(function(alert) {
        setTimeout(function() {
            try {
                const closeBtn = alert.querySelector('.btn-close');
                if (closeBtn) closeBtn.click();
            } catch (e) {
                alert.style.display = 'none';
            }
        }, 5000);
    });
});

if ('serviceWorker' in navigator) {
    window.addEventListener('load', function() {
        navigator.serviceWorker.register('/static/sw.js').catch(function() {
            // Installation is optional; the authenticated application remains fully usable online.
        });
    });
}

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
                        backgroundColor: 'rgba(56, 189, 248, 0.6)',
                        borderColor: '#38BDF8',
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
                            grid: { color: '#243B5C' },
                            ticks: { color: '#94A3B8', precision: 0 }
                        },
                        x: {
                            grid: { display: false },
                            ticks: { color: '#94A3B8' }
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
                        backgroundColor: ['#00A3FF', '#38BDF8'],
                        borderColor: '#15263F',
                        borderWidth: 2
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            position: 'bottom',
                            labels: { color: '#F8FAFC', font: { family: 'Outfit' } }
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
                'Active': '#22C55E',
                'Planned': '#EAB308',
                'Completed': '#38BDF8',
                'Draft': '#94A3B8',
                'Archived': '#EF4444'
            };
            
            const backgroundColors = data.statuses.map(s => colors[s] || '#94A3B8');

            new Chart(statusCtx, {
                type: 'pie',
                data: {
                    labels: data.statuses,
                    datasets: [{
                        data: data.statusCounts,
                        backgroundColor: backgroundColors,
                        borderColor: '#15263F',
                        borderWidth: 2
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            position: 'bottom',
                            labels: { color: '#F8FAFC', font: { family: 'Outfit' } }
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
                        backgroundColor: ['#00A3FF', '#38BDF8', '#22C55E', '#EAB308', '#A855F7', '#EF4444'],
                        borderColor: '#15263F',
                        borderWidth: 2
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            position: 'bottom',
                            labels: { color: '#F8FAFC', font: { family: 'Outfit' } }
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
                        backgroundColor: 'rgba(56, 189, 248, 0.6)',
                        borderColor: '#38BDF8',
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
                            grid: { color: '#243B5C' },
                            ticks: { color: '#94A3B8' }
                        },
                        x: {
                            grid: { display: false },
                            ticks: { color: '#94A3B8' }
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
                        backgroundColor: 'rgba(34, 197, 94, 0.6)',
                        borderColor: '#22C55E',
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
                            grid: { color: '#243B5C' },
                            ticks: { color: '#94A3B8', precision: 0 }
                        },
                        x: {
                            grid: { display: false },
                            ticks: { color: '#94A3B8' }
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
