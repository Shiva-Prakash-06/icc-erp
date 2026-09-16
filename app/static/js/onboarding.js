// First-run onboarding: welcome modal, anchored spotlight tour, checklist.
//
// No library. Shepherd and Intro.js each cost more gzipped than this whole
// stylesheet, and both want to own focus and scrolling in ways the shell
// already handles.
//
// The tour's state lives on the server (users.onboarding_step), not in
// sessionStorage, because two of its steps anchor to elements on other pages:
// advancing across a full page load has to survive the navigation, and a
// half-finished tour has to survive a logout.

(function () {
    'use strict';

    const source = document.getElementById('onboarding-data');
    if (!source) return;

    let config;
    try {
        config = JSON.parse(source.textContent);
    } catch (error) {
        return;
    }
    if (!config || !Array.isArray(config.steps) || !config.steps.length) return;

    const steps = config.steps;
    const endpoint = config.endpoint;
    const csrfToken = (document.querySelector('meta[name="csrf-token"]') || {}).content || '';

    const welcome = document.getElementById('onboardingWelcome');
    const spotlight = document.getElementById('onboardingSpotlight');
    const card = document.getElementById('onboardingCard');
    const cardTitle = document.getElementById('onboardingCardTitle');
    const cardBody = document.getElementById('onboardingCardBody');
    const counter = card && card.querySelector('[data-onboarding-counter]');
    const dots = card && card.querySelector('[data-onboarding-dots]');
    const backButton = card && card.querySelector('[data-onboarding-back]');
    const nextButton = card && card.querySelector('[data-onboarding-next]');

    // Where the card sits relative to its target, and how far off it.
    const GAP = 12;
    const CARD_WIDTH = 340;
    const EDGE = 16;

    let current = 0;          // 1-based, matching users.onboarding_step
    let lastFocused = null;

    function patch(payload) {
        return fetch(endpoint, {
            method: 'PATCH',
            credentials: 'same-origin',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken},
            body: JSON.stringify(payload),
        }).catch(function () { /* onboarding must never block the page */ });
    }

    // ── signals ──────────────────────────────────────────────────────────
    // Reported at most once per tab per signal; the server is idempotent
    // anyway, this just avoids a request on every page view.
    function recordSignal(signal) {
        if (!signal) return;
        const key = 'onb:' + signal;
        try {
            if (sessionStorage.getItem(key)) return;
            sessionStorage.setItem(key, '1');
        } catch (error) { /* private browsing: fall through and just POST */ }
        patch({signal: signal});
    }

    recordSignal(config.pageSignal);
    document.addEventListener('aurora:command-open', function () { recordSignal('search_used'); }, {once: true});

    // ── measuring ────────────────────────────────────────────────────────
    // A target can be declared twice -- the primary nav exists as a desktop
    // top bar and a mobile bottom bar -- so take the first one that is
    // actually laid out.
    function findTarget(name) {
        const candidates = document.querySelectorAll('[data-tour="' + name + '"]');
        for (let index = 0; index < candidates.length; index += 1) {
            const rect = candidates[index].getBoundingClientRect();
            if (rect.width > 0 && rect.height > 0) return candidates[index];
        }
        return null;
    }

    function measure(element) {
        const rect = element.getBoundingClientRect();
        return {top: rect.top, left: rect.left, width: rect.width, height: rect.height, bottom: rect.bottom, right: rect.right};
    }

    function clamp(value, min, max) {
        return Math.max(min, Math.min(value, max));
    }

    // Place below the target by default; fall back to the side with room, and
    // clamp to the viewport so the card is never half off-screen on a phone or
    // at 200% zoom.
    function place(box, preferred) {
        const cardRect = card.getBoundingClientRect();
        const height = cardRect.height || 200;
        const width = Math.min(CARD_WIDTH, window.innerWidth - EDGE * 2);
        const viewportHeight = window.innerHeight;
        const viewportWidth = window.innerWidth;

        // Sideways before above: a tall target (the decision queue runs past
        // the fold) leaves no room below, and a card placed above it covers
        // the page heading instead of pointing at anything.
        const order = [preferred || 'bottom', 'bottom', 'right', 'left', 'top'];
        let placement = 'bottom';
        for (let index = 0; index < order.length; index += 1) {
            const option = order[index];
            if (option === 'bottom' && box.bottom + GAP + height <= viewportHeight) { placement = option; break; }
            if (option === 'top' && box.top - GAP - height >= 0) { placement = option; break; }
            if (option === 'right' && box.right + GAP + width <= viewportWidth) { placement = option; break; }
            if (option === 'left' && box.left - GAP - width >= 0) { placement = option; break; }
        }

        let top;
        let left;
        if (placement === 'bottom') { top = box.bottom + GAP; left = box.left; }
        else if (placement === 'top') { top = box.top - GAP - height; left = box.left; }
        else if (placement === 'right') { top = box.top; left = box.right + GAP; }
        else { top = box.top; left = box.left - GAP - width; }

        card.style.width = width + 'px';
        card.style.top = clamp(top, EDGE, Math.max(EDGE, viewportHeight - height - EDGE)) + 'px';
        card.style.left = clamp(left, EDGE, Math.max(EDGE, viewportWidth - width - EDGE)) + 'px';
    }

    function tourMove() {
        if (!current) return;
        const step = steps[current - 1];
        const target = step && findTarget(step.target);
        if (!target) return;
        const box = measure(target);
        spotlight.style.top = box.top + 'px';
        spotlight.style.left = box.left + 'px';
        spotlight.style.width = box.width + 'px';
        spotlight.style.height = box.height + 'px';
        place(box, step.placement);
    }

    // ── the tour ─────────────────────────────────────────────────────────
    function samePage(url) {
        if (!url) return true;
        const target = new URL(url, window.location.origin);
        return target.pathname === window.location.pathname;
    }

    // A step can be shown here if its target is on this page. A step whose
    // target is missing and which has no page of its own is dropped outright
    // rather than rendered as an orphan tooltip.
    function reachable(index) {
        const step = steps[index - 1];
        if (!step) return false;
        if (samePage(step.url)) return Boolean(findTarget(step.target));
        return Boolean(step.url);
    }

    function nextReachable(from, direction) {
        let index = from;
        while (index >= 1 && index <= steps.length) {
            if (reachable(index)) return index;
            index += direction;
        }
        return 0;
    }

    function endTour(persist) {
        current = 0;
        card.hidden = true;
        spotlight.hidden = true;
        document.body.classList.remove('onb-touring');
        if (persist !== false) patch({step: 0, seen: true});
        if (lastFocused && lastFocused.isConnected) lastFocused.focus();
    }

    function show(index) {
        const resolved = nextReachable(index, index >= current ? 1 : -1);
        if (!resolved) { endTour(); return; }
        const step = steps[resolved - 1];

        if (!samePage(step.url)) {
            // The step lives on another page. Persist first, then navigate:
            // the next page load resumes at exactly this step.
            patch({step: resolved, seen: true}).then(function () { window.location.assign(step.url); });
            return;
        }

        current = resolved;
        cardTitle.textContent = step.title;
        cardBody.textContent = step.body;
        counter.textContent = 'Step ' + resolved + ' of ' + steps.length;
        backButton.disabled = nextReachable(resolved - 1, -1) === 0;
        nextButton.textContent = nextReachable(resolved + 1, 1) === 0 ? 'Got it' : 'Next';

        dots.innerHTML = '';
        for (let position = 1; position <= steps.length; position += 1) {
            const dot = document.createElement('span');
            dot.className = 'onb-dot' + (position === resolved ? ' is-current' : '') + (position < resolved ? ' is-done' : '');
            dots.appendChild(dot);
        }

        spotlight.hidden = false;
        card.hidden = false;
        document.body.classList.add('onb-touring');
        tourMove();
        card.focus();
        patch({step: resolved, seen: true});
    }

    function startTour(fromStep) {
        if (!card || !spotlight) return;
        lastFocused = document.activeElement;
        current = 0;
        show(fromStep || 1);
    }

    if (nextButton) nextButton.addEventListener('click', function () { show(current + 1); });
    if (backButton) backButton.addEventListener('click', function () { show(current - 1); });
    const skipButton = card && card.querySelector('[data-onboarding-skip]');
    if (skipButton) skipButton.addEventListener('click', function () { endTour(); });

    document.addEventListener('keydown', function (event) {
        if (!current) return;
        if (event.key === 'Escape') { event.preventDefault(); endTour(); }
        else if (event.key === 'ArrowRight') { event.preventDefault(); show(current + 1); }
        else if (event.key === 'ArrowLeft') { event.preventDefault(); show(current - 1); }
    });

    let frame = null;
    function scheduleMove() {
        if (!current || frame) return;
        frame = window.requestAnimationFrame(function () { frame = null; tourMove(); });
    }
    window.addEventListener('resize', scheduleMove);
    window.addEventListener('scroll', scheduleMove, true);

    // ── the welcome modal ────────────────────────────────────────────────
    function closeWelcome() {
        if (!welcome) return;
        welcome.hidden = true;
        document.body.classList.remove('onb-modal-open');
    }

    function openWelcome() {
        if (!welcome) return;
        lastFocused = document.activeElement;
        welcome.hidden = false;
        document.body.classList.add('onb-modal-open');
        const first = welcome.querySelector('button');
        if (first) first.focus();
    }

    if (welcome) {
        // Focus trap: the modal is the only thing on the page while it is up,
        // and Esc is the same as "I'll explore myself" -- both mean "not now",
        // and neither should be able to strand the user behind a scrim.
        welcome.addEventListener('keydown', function (event) {
            if (event.key === 'Escape') {
                event.preventDefault();
                closeWelcome();
                patch({seen: true, step: 0});
                if (lastFocused && lastFocused.isConnected) lastFocused.focus();
                return;
            }
            if (event.key !== 'Tab') return;
            const focusable = welcome.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
            if (!focusable.length) return;
            const first = focusable[0];
            const last = focusable[focusable.length - 1];
            if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
            else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
        });

        const startButton = welcome.querySelector('[data-onboarding-start]');
        const declineButton = welcome.querySelector('[data-onboarding-decline]');
        if (startButton) startButton.addEventListener('click', function () { closeWelcome(); startTour(1); });
        if (declineButton) declineButton.addEventListener('click', function () {
            closeWelcome();
            patch({seen: true, step: 0});
            if (lastFocused && lastFocused.isConnected) lastFocused.focus();
        });
    }

    // ── checklist card ───────────────────────────────────────────────────
    const progress = document.querySelector('[data-onboarding-progress]');
    if (progress) {
        const percent = Number(progress.getAttribute('data-onboarding-progress')) || 0;
        progress.style.width = percent + '%';
    }

    document.querySelectorAll('[data-onboarding-replay]').forEach(function (button) {
        button.addEventListener('click', function () { startTour(1); });
    });

    document.querySelectorAll('[data-onboarding-hide-checklist]').forEach(function (button) {
        button.addEventListener('click', function () {
            const section = document.getElementById('onboardingChecklist');
            if (section) section.remove();
            patch({signal: 'checklist_hidden'});
        });
    });

    // ── entry point ──────────────────────────────────────────────────────
    if (config.step > 0) startTour(config.step);
    else if (!config.seen) openWelcome();
})();
