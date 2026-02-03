// SharePoint Mirror - App JavaScript

// Timezone detection: set HTMX header + cookie so server renders in browser TZ
(function() {
    var tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
    if (!tz) return;

    // Set cookie for full-page loads
    document.cookie = "tz=" + tz + ";path=/;max-age=31536000;SameSite=Lax";

    // Set hx-headers on <body> so every HTMX request includes the TZ
    document.addEventListener('DOMContentLoaded', function() {
        document.body.setAttribute('hx-headers', JSON.stringify({"X-Timezone": tz}));
    });
})();

// Theme management (light/dark toggle, defaults to browser preference)
(function() {
    var THEME_KEY = 'spmirror-theme';
    var html = document.documentElement;

    function getSystemTheme() {
        return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }

    function getCurrentTheme() {
        return localStorage.getItem(THEME_KEY) || getSystemTheme();
    }

    function applyTheme(theme) {
        html.setAttribute('data-theme', theme);
    }

    // Apply immediately to prevent FOUC
    applyTheme(getCurrentTheme());

    document.addEventListener('DOMContentLoaded', function() {
        var checkbox = document.getElementById('mode-checkbox');
        if (!checkbox) return;

        checkbox.checked = (getCurrentTheme() === 'dark');

        checkbox.addEventListener('change', function() {
            html.classList.add('trans');
            var theme = checkbox.checked ? 'dark' : 'light';
            applyTheme(theme);
            localStorage.setItem(THEME_KEY, theme);
        });
    });

    // Respond to system preference changes when no stored preference
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function() {
        if (!localStorage.getItem(THEME_KEY)) {
            var theme = getSystemTheme();
            applyTheme(theme);
            var checkbox = document.getElementById('mode-checkbox');
            if (checkbox) checkbox.checked = (theme === 'dark');
        }
    });
})();

// HTMX event handlers
document.body.addEventListener('htmx:beforeRequest', function(evt) {
    // Add loading state
    evt.detail.elt.classList.add('loading');
});

document.body.addEventListener('htmx:afterRequest', function(evt) {
    // Remove loading state
    evt.detail.elt.classList.remove('loading');
});

// Handle HTMX errors
document.body.addEventListener('htmx:responseError', function(evt) {
    console.error('HTMX request failed:', evt.detail.error);
});
