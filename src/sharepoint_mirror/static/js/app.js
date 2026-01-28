// SharePoint Mirror - App JavaScript

// Theme toggle
function toggleTheme() {
    const html = document.documentElement;
    const currentTheme = html.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';

    html.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
    updateThemeIcon(newTheme);
}

function updateThemeIcon(theme) {
    const icon = document.getElementById('theme-icon');
    if (icon) {
        // Moon for light theme (click to go dark), Sun for dark theme (click to go light)
        icon.textContent = theme === 'dark' ? '\u2600' : '\u263E';
    }
}

// Initialize theme from localStorage or system preference
function initTheme() {
    const savedTheme = localStorage.getItem('theme');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const theme = savedTheme || (prefersDark ? 'dark' : 'light');

    document.documentElement.setAttribute('data-theme', theme);
    updateThemeIcon(theme);
}

// Run on page load
document.addEventListener('DOMContentLoaded', initTheme);

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
