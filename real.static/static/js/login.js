const roleButtons = document.querySelectorAll('[data-role]');
const form = document.getElementById('login-form');
const nameInput = document.getElementById('login-name');
const institutionInput = document.getElementById('login-institution');
const institutionField = document.getElementById('institution-field');
const passwordInput = document.getElementById('login-password');
const submit = document.getElementById('login-submit');
const errorBox = document.getElementById('login-error');
const modeTabs = document.getElementById('mode-tabs');
const tabSignin = document.getElementById('tab-signin');
const tabSignup = document.getElementById('tab-signup');
const adminNote = document.getElementById('admin-note');
const hint = document.getElementById('password-hint');
const sub = document.getElementById('login-sub');
const reveal = document.getElementById('reveal');

let role = 'admin';
let creating = false;

function render() {
    // Admin accounts are never self-service: they are added from the admin dashboard.
    if (role === 'admin') creating = false;
    roleButtons.forEach((button) => {
        const active = button.dataset.role === role;
        button.classList.toggle('is-active', active);
        button.setAttribute('aria-pressed', String(active));
    });
    modeTabs.hidden = role === 'admin';
    adminNote.hidden = role !== 'admin';
    institutionField.hidden = role !== 'admin';
    tabSignin.setAttribute('aria-selected', String(!creating));
    tabSignup.setAttribute('aria-selected', String(creating));
    hint.hidden = !creating;
    passwordInput.minLength = creating ? 12 : 1;
    passwordInput.autocomplete = creating ? 'new-password' : 'current-password';
    sub.textContent = role === 'admin'
        ? 'Sign in to issue and manage certificates for your institution.'
        : (creating ? 'Create a free account to verify certificates.' : 'Sign in to verify certificates.');
    submit.textContent = role === 'admin' ? 'Sign in as admin' : (creating ? 'Create account' : 'Sign in');
    errorBox.textContent = '';
}

roleButtons.forEach((button) => button.addEventListener('click', () => { role = button.dataset.role; render(); }));
tabSignin.addEventListener('click', () => { creating = false; render(); });
tabSignup.addEventListener('click', () => { creating = true; render(); });

reveal.addEventListener('click', () => {
    const show = passwordInput.type === 'password';
    passwordInput.type = show ? 'text' : 'password';
    reveal.setAttribute('aria-pressed', String(show));
    reveal.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
    reveal.querySelector('use').setAttribute('href', `/static/img/icons.svg#i-${show ? 'eye-off' : 'eye'}`);
});

form.addEventListener('submit', async (event) => {
    event.preventDefault();
    errorBox.textContent = '';
    const username = nameInput.value.trim();
    const institution = institutionInput.value.trim().replace(/\s+/g, ' ');
    if (role === 'admin' && institution.length < 2) { errorBox.textContent = 'Enter your institution name.'; institutionInput.focus(); return; }
    if (!username || !passwordInput.value) { errorBox.textContent = 'Enter your username and password.'; return; }
    if (creating && passwordInput.value.length < 12) { errorBox.textContent = 'Use a password of at least 12 characters.'; return; }

    const endpoint = role === 'admin' ? '/api/auth/login' : (creating ? '/api/auth/register/user' : '/api/auth/user/login');
    submit.disabled = true;
    try {
        const response = await fetch(endpoint, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(role === 'admin' ? { username, password: passwordInput.value, institution } : { username, password: passwordInput.value })
        });
        const result = await response.json().catch(() => ({}));
        if (!response.ok) {
            const detail = result.detail;
            throw new Error(Array.isArray(detail) ? detail.map((item) => item.msg).join(', ') : detail || 'Could not sign in.');
        }
        sessionStorage.setItem(role === 'admin' ? 'certichain_token' : 'certichain_user_token', result.access_token);
        window.location.href = role === 'admin' ? '/admin.html' : '/user.html';
    } catch (error) {
        errorBox.textContent = error.message;
    } finally { submit.disabled = false; }
});

render();
