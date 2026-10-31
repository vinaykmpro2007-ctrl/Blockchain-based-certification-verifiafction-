const token = sessionStorage.getItem('certichain_token');
if (!token) window.location.replace('/login.html');

const $ = (id) => document.getElementById(id);

let me = null;                 // { username, institution }
let summary = null;            // latest revocation summary
let certificates = [];
let documents = [];
let selectedId = null;
let revokeTarget = null;       // { kind: 'certificates' | 'documents', id, label }

/* ---------- Helpers ---------- */

function errorText(body) {
    const detail = body && body.detail;
    if (Array.isArray(detail)) return detail.map((item) => item.msg).join(', ');
    return detail || 'Request failed.';
}

function endSession() {
    sessionStorage.removeItem('certichain_token');
    window.location.replace('/login.html');
}

async function request(path, options = {}) {
    const response = await fetch(path, {
        ...options,
        headers: { Authorization: `Bearer ${token}`, ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...options.headers }
    });
    if (response.status === 401) { endSession(); throw new Error('Session expired. Sign in again.'); }
    return response;
}

async function api(path, options) {
    const response = await request(path, options);
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(errorText(body));
    return body;
}

function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
}

function cell(content, className) {
    const td = el('td', className);
    if (content instanceof Node) td.append(content); else td.textContent = content ?? '';
    return td;
}

function pill(status) {
    const label = status.charAt(0) + status.slice(1).toLowerCase();
    return el('span', `pill pill-${status.toLowerCase()}`, label);
}

function icon(name) {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('class', 'icon');
    svg.setAttribute('aria-hidden', 'true');
    const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
    use.setAttribute('href', `/static/img/icons.svg#i-${name}`);
    svg.append(use);
    return svg;
}

function toast(text, isError = false) {
    const box = el('div', `toast${isError ? ' is-error' : ''}`);
    box.append(icon(isError ? 'alert' : 'check'), el('span', '', text));
    const holder = $('toasts');
    holder.append(box);
    while (holder.children.length > 3) holder.firstElementChild.remove();
    setTimeout(() => box.remove(), isError ? 6500 : 3800);
}

function normalize(text) { return (text || '').trim().replace(/\s+/g, ' ').toLowerCase(); }

// An admin may revoke what they issued, or anything from their own institution.
function canRevoke(institution, issuedBy) {
    if (!me) return false;
    return issuedBy === me.username || normalize(institution) === normalize(me.institution);
}

function formatWhen(iso) { return iso ? iso.replace('T', ' ').replace('Z', '') : ''; }

function setBusy(button, busy, busyText) {
    if (busy) { button.dataset.label = button.textContent; button.textContent = busyText; }
    else if (button.dataset.label) { button.textContent = button.dataset.label; }
    button.disabled = busy;
    button.setAttribute('aria-busy', String(busy));
}

function revealToggle(button, input) {
    button.addEventListener('click', () => {
        const show = input.type === 'password';
        input.type = show ? 'text' : 'password';
        button.setAttribute('aria-pressed', String(show));
        button.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
        button.querySelector('use').setAttribute('href', `/static/img/icons.svg#i-${show ? 'eye-off' : 'eye'}`);
    });
}

/* ---------- Navigation ---------- */

const views = document.querySelectorAll('[data-view]');
const navLinks = document.querySelectorAll('[data-nav]');
const side = $('side');

function showView() {
    const wanted = location.hash.replace('#', '');
    const name = [...views].some((view) => view.dataset.view === wanted) ? wanted : 'overview';
    views.forEach((view) => { view.hidden = view.dataset.view !== name; });
    navLinks.forEach((link) => {
        const active = link.dataset.nav === name;
        link.classList.toggle('is-active', active);
        if (active) link.setAttribute('aria-current', 'page'); else link.removeAttribute('aria-current');
    });
    side.classList.remove('is-open');
    $('menu-btn').setAttribute('aria-expanded', 'false');
    window.scrollTo({ top: 0 });
}
window.addEventListener('hashchange', showView);
$('menu-btn').addEventListener('click', () => {
    const open = side.classList.toggle('is-open');
    $('menu-btn').setAttribute('aria-expanded', String(open));
});
$('logout').addEventListener('click', endSession);

/* ---------- Revocation banner ---------- */

function renderSummary(data) {
    summary = data;
    const titles = { OK: 'Revocation activity', WARNING: 'Warning: many revocations', CRITICAL: 'Critical: too many revocations' };
    const banner = $('revoke-alert');
    banner.hidden = false;
    banner.classList.remove('is-ok', 'is-warning', 'is-critical');
    banner.classList.add(`is-${data.level.toLowerCase()}`);
    $('revoke-alert-title').textContent = titles[data.level];
    $('revoke-alert-message').textContent = data.level === 'OK' && data.remaining_before_warning > 0
        ? `${data.message} ${data.remaining_before_warning} more revocation${data.remaining_before_warning === 1 ? '' : 's'} will trigger a warning.`
        : data.message;
    $('revoke-count-own').textContent = data.own_revocations;
    $('revoke-count-institution').textContent = data.institution_revocations;
    $('revoke-window').textContent = data.window_days;
    $('revoke-warn-at').textContent = data.warn_threshold;
    $('revoke-critical-at').textContent = data.critical_threshold;
    $('revoke-alert-icon').setAttribute('href', `/static/img/icons.svg#i-${data.level === 'OK' ? 'info' : 'alert'}`);
}

/* ---------- Stats ---------- */

function renderStats() {
    const revokedCerts = certificates.filter((cert) => cert.status === 'REVOKED').length;
    const revokedDocs = documents.filter((doc) => doc.status === 'REVOKED').length;
    $('stat-issued').textContent = certificates.length;
    $('stat-valid').textContent = certificates.length - revokedCerts;
    $('stat-revoked').textContent = revokedCerts + revokedDocs;
    $('stat-documents').textContent = documents.length;
}

/* ---------- Certificates ---------- */

function renderRecent() {
    const body = $('recent-table').querySelector('tbody');
    body.replaceChildren();
    if (!certificates.length) {
        const row = el('tr'); const td = cell('No certificates yet. Issue the first one from the Certificates page.');
        td.colSpan = 3; td.className = 'sub'; row.append(td); body.append(row); return;
    }
    for (const cert of certificates.slice(0, 5)) {
        const row = el('tr', 'is-clickable');
        row.tabIndex = 0;
        const open = () => { selectedId = cert.certificate_id; location.hash = '#certificates'; renderCertificates(); showCertificate(); };
        row.addEventListener('click', open);
        row.addEventListener('keydown', (event) => { if (event.key === 'Enter') open(); });
        row.append(cell(cert.certificate_id, 'mono'), cell(cert.student_name), cell(pill(cert.status)));
        body.append(row);
    }
}

function renderCertificates() {
    const query = normalize($('cert-search').value);
    const filter = $('cert-filter').value;
    const rows = certificates.filter((cert) =>
        (!filter || cert.status === filter)
        && (!query || normalize(`${cert.student_name} ${cert.certificate_id} ${cert.course} ${cert.student_id}`).includes(query)));

    const body = $('cert-table').querySelector('tbody');
    body.replaceChildren();
    $('cert-count').textContent = `${certificates.length} certificate${certificates.length === 1 ? '' : 's'}`
        + (rows.length !== certificates.length ? `, ${rows.length} shown` : '');

    for (const cert of rows) {
        const row = el('tr', `is-clickable${cert.certificate_id === selectedId ? ' is-selected' : ''}`);
        row.tabIndex = 0;
        const select = () => { selectedId = cert.certificate_id; renderCertificates(); showCertificate(); };
        row.addEventListener('click', select);
        row.addEventListener('keydown', (event) => { if (event.key === 'Enter') select(); });
        row.append(cell(cert.certificate_id, 'mono'), cell(cert.student_name), cell(cert.course), cell(cert.issue_date, 'num'), cell(pill(cert.status)));
        body.append(row);
    }

    const none = !rows.length;
    $('cert-none').hidden = !none;
    $('cert-table').parentElement.hidden = none;
    if (none) {
        const filtered = certificates.length > 0;
        $('cert-none-title').textContent = filtered ? 'No matches' : 'No certificates yet';
        $('cert-none-text').textContent = filtered ? 'Try a different search or status.' : 'Issue your first certificate with the form above.';
    }
}

function selectedCertificate() { return certificates.find((cert) => cert.certificate_id === selectedId) || null; }

function showCertificate() {
    const cert = selectedCertificate();
    $('cert-empty').hidden = !!cert;
    $('cert-detail').hidden = !cert;
    $('cert-error').textContent = '';
    if (!cert) return;
    $('cp-institution').textContent = cert.institution;
    $('cp-name').textContent = cert.student_name;
    $('cp-course').textContent = cert.course;
    $('cp-date').textContent = cert.issue_date;
    $('cp-id').textContent = cert.certificate_id;
    $('cert-paper').classList.toggle('is-revoked', cert.status === 'REVOKED');
    $('revoke-selected').hidden = !(cert.status !== 'REVOKED' && canRevoke(cert.institution, cert.issued_by));
}

async function refreshCertificates() {
    certificates = await api('/api/certificates');
    renderCertificates(); renderRecent(); showCertificate(); renderStats();
}

$('cert-search').addEventListener('input', renderCertificates);
$('cert-filter').addEventListener('change', renderCertificates);

/* PDF download: the endpoint needs the sign-in token, so a plain link will not work.
   Fetch it with the token, then hand the file to the browser. */
$('download-pdf').addEventListener('click', async (event) => {
    const cert = selectedCertificate();
    if (!cert) return;
    const button = event.currentTarget;
    $('cert-error').textContent = '';
    setBusy(button, true, 'Preparing PDF…');
    try {
        const response = await request(`/api/certificates/${encodeURIComponent(cert.certificate_id)}/pdf`);
        if (!response.ok) throw new Error(errorText(await response.json().catch(() => ({}))));
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url; link.download = `${cert.certificate_id}.pdf`;
        document.body.append(link); link.click(); link.remove();
        setTimeout(() => URL.revokeObjectURL(url), 15000);
        toast(`Downloaded ${cert.certificate_id}.pdf`);
    } catch (error) {
        $('cert-error').textContent = `Could not download the PDF. ${error.message}`;
    } finally { setBusy(button, false); }
});

$('copy-link').addEventListener('click', async () => {
    const cert = selectedCertificate();
    if (!cert) return;
    const url = `${location.origin}/user.html?id=${encodeURIComponent(cert.certificate_id)}`;
    try {
        await navigator.clipboard.writeText(url);
        toast('Verification link copied');
    } catch (error) {
        window.prompt('Copy this verification link:', url);
    }
});

/* Issue certificate. The institution is fixed by the account, so it is never sent. */
$('issue-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const error = $('issue-error');
    error.textContent = '';
    const fields = {
        student_name: $('std-name').value.trim(), student_id: $('std-id').value.trim(),
        course: $('std-course').value.trim(), issue_date: $('std-date').value
    };
    if (Object.values(fields).some((value) => !value)) { error.textContent = 'Fill in every field.'; return; }
    const button = $('issue-submit');
    setBusy(button, true, 'Issuing…');
    try {
        const cert = await api('/api/certificates', { method: 'POST', body: JSON.stringify(fields) });
        event.target.reset();
        $('std-date').value = today();
        $('std-ins').value = me.institution;   // reset() clears the locked field
        selectedId = cert.certificate_id;
        await refreshCertificates();
        toast(`Certificate issued: ${cert.certificate_id}`);
    } catch (problem) { error.textContent = problem.message; }
    finally { setBusy(button, false); }
});

function today() { return new Date().toISOString().slice(0, 10); }

/* ---------- Documents ---------- */

async function refreshDocuments() {
    documents = await api('/api/documents');
    const body = $('documents-table').querySelector('tbody');
    body.replaceChildren();
    $('documents-empty').hidden = documents.length > 0;
    $('documents-table').parentElement.hidden = documents.length === 0;
    for (const doc of documents) {
        const row = el('tr');
        const docCell = cell(doc.doc_type_label);
        if (doc.details) {
            docCell.append(el('span', 'doc-sub', `${doc.details.total_marks}/${doc.details.max_total_marks} · ${doc.details.percentage}% · ${doc.details.result}`));
        }
        const action = cell('');
        if (doc.status !== 'REVOKED' && canRevoke(doc.issuing_institution, doc.issued_by)) {
            const button = el('button', 'btn btn-sm btn-quiet', 'Revoke');
            button.type = 'button';
            button.addEventListener('click', () => openRevoke({
                kind: 'documents', id: doc.document_id,
                label: `${doc.doc_type_label} of ${doc.holder_name} (${doc.document_id})`
            }));
            action.append(button);
        }
        row.append(cell(doc.holder_name), docCell, cell(doc.issuing_institution), cell(doc.number_masked, 'mono'), cell(pill(doc.status)), action);
        body.append(row);
    }
    renderStats();
}

/* ---------- Activity log ---------- */

async function refreshRevocationLog() {
    const entries = await api('/api/admin/revocations');
    const body = $('revocation-table').querySelector('tbody');
    body.replaceChildren();
    $('revocation-empty').hidden = entries.length > 0;
    $('revocation-table').parentElement.hidden = entries.length === 0;
    for (const entry of entries) {
        const row = el('tr');
        row.append(cell(formatWhen(entry.revoked_at), 'num'), cell(entry.target_id, 'mono'), cell(entry.revoked_by), cell(entry.reason));
        body.append(row);
    }
}

async function refreshSummary() { renderSummary(await api('/api/admin/revocations/summary')); }

/* ---------- Team ---------- */

async function refreshTeam() {
    const members = await api('/api/admins');
    const body = $('team-table').querySelector('tbody');
    body.replaceChildren();
    $('team-count').textContent = `${members.length} admin${members.length === 1 ? '' : 's'}`;
    for (const member of members) {
        const name = cell(member.username);
        if (member.username === me.username) name.append(el('span', 'sub', 'You'));
        const row = el('tr');
        row.append(name, cell(el('span', `pill ${member.is_active ? 'pill-ok' : 'pill-neutral'}`, member.is_active ? 'Active' : 'Inactive')));
        body.append(row);
    }
}

revealToggle($('team-reveal'), $('team-password'));

$('team-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const error = $('team-error');
    error.textContent = '';
    const username = $('team-name').value.trim();
    const password = $('team-password').value;
    if (username.length < 3) { error.textContent = 'Username must be at least 3 characters.'; return; }
    if (password.length < 12) { error.textContent = 'Password must be at least 12 characters.'; return; }
    const button = $('team-submit');
    setBusy(button, true, 'Creating…');
    try {
        await api('/api/admins', { method: 'POST', body: JSON.stringify({ username, password }) });
        event.target.reset();
        $('team-inst').value = me.institution;
        toast(`${username} can now sign in for ${me.institution}`);
        await refreshTeam();
    } catch (problem) { error.textContent = problem.message; }
    finally { setBusy(button, false); }
});

/* ---------- Revoke dialog ---------- */

const revokeDialog = $('revoke-dialog');

function openRevoke(target) {
    revokeTarget = target;
    $('revoke-title').textContent = target.kind === 'documents' ? 'Revoke document' : 'Revoke certificate';
    $('revoke-target').textContent = target.label;
    $('revoke-reason').value = '';
    $('revoke-error').textContent = '';
    // Warn BEFORE the action if this revocation reaches, or is past, the limit.
    const upcoming = summary ? summary.own_revocations + 1 : 0;
    const show = summary && (summary.level !== 'OK' || upcoming >= summary.warn_threshold);
    $('revoke-heads-up').hidden = !show;
    $('revoke-heads-up-text').textContent = !show ? '' : (summary.level === 'OK'
        ? `This will be revocation number ${upcoming} for you in the last ${summary.window_days} days, which reaches the warning limit of ${summary.warn_threshold}.`
        : `You have already revoked ${summary.own_revocations} item(s) in the last ${summary.window_days} days. Please make sure this one is necessary.`);
    revokeDialog.showModal();
    $('revoke-reason').focus();
}

$('revoke-close').addEventListener('click', () => revokeDialog.close());
$('revoke-cancel').addEventListener('click', () => revokeDialog.close());
revokeDialog.addEventListener('click', (event) => { if (event.target === revokeDialog) revokeDialog.close(); });

$('revoke-selected').addEventListener('click', () => {
    const cert = selectedCertificate();
    if (cert) openRevoke({ kind: 'certificates', id: cert.certificate_id, label: `Certificate ${cert.certificate_id} (${cert.student_name})` });
});

$('revoke-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const reason = $('revoke-reason').value.trim();
    if (!revokeTarget) return;
    if (reason.length < 5) { $('revoke-error').textContent = 'Give a reason of at least 5 characters.'; return; }
    const button = $('revoke-confirm');
    setBusy(button, true, 'Revoking…');
    try {
        const result = await api(`/api/${revokeTarget.kind}/${encodeURIComponent(revokeTarget.id)}/revoke`, {
            method: 'POST', body: JSON.stringify({ reason })
        });
        revokeDialog.close();
        renderSummary(result.summary);
        toast(`${revokeTarget.label} revoked`);
        await Promise.all([refreshCertificates(), refreshDocuments(), refreshRevocationLog()]);
    } catch (error) { $('revoke-error').textContent = error.message; }
    finally { setBusy(button, false); }
});

/* ---------- Start ---------- */

(async () => {
    showView();
    $('std-date').value = today();
    try {
        me = await api('/api/auth/me');
        $('who-name').textContent = me.username;
        $('who-inst').textContent = me.institution;
        $('avatar').textContent = me.username.charAt(0).toUpperCase();
        $('std-ins').value = me.institution;
        $('team-inst').value = me.institution;
        document.querySelectorAll('.inst-name').forEach((node) => { node.textContent = me.institution; });
        $('overview-sub').textContent = `Signed in as ${me.username} at ${me.institution}.`;
        await Promise.all([refreshCertificates(), refreshDocuments(), refreshRevocationLog(), refreshSummary(), refreshTeam()]);
    } catch (error) { toast(error.message, true); }
})();
