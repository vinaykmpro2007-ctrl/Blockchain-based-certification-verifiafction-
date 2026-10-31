const $ = (id) => document.getElementById(id);
const tabs = [...document.querySelectorAll('[data-method]')];
const panels = { id: $('panel-id'), qr: $('panel-qr'), pdf: $('panel-pdf') };
const idInput = $('certificate-id');
const fileInput = $('certificate-file');
const result = $('result');
const video = $('camera-preview');
let stream = null;
let frame = null;

/* ---------- Header: show sign-out when a verifier is signed in ---------- */
(function headerState() {
    if (!sessionStorage.getItem('certichain_user_token')) return;
    const link = $('nav-login');
    link.querySelector('span').textContent = 'Log out';
    link.href = '#';
    link.addEventListener('click', (event) => {
        event.preventDefault();
        sessionStorage.removeItem('certichain_user_token');
        window.location.reload();
    });
})();

/* ---------- Result card ---------- */

function icon(name) {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('class', 'icon'); svg.setAttribute('aria-hidden', 'true');
    const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
    use.setAttribute('href', `/static/img/icons.svg#i-${name}`);
    svg.append(use);
    return svg;
}

function node(tag, className, text) {
    const item = document.createElement(tag);
    if (className) item.className = className;
    if (text !== undefined) item.textContent = text;
    return item;
}

function showHeadOnly(kind, iconName, title, detail) {
    result.hidden = false;
    result.className = `result is-${kind}`;
    const head = node('div', 'result-head');
    const text = node('div');
    text.append(node('span', '', title));
    if (detail) text.append(node('small', '', detail));
    head.append(icon(iconName), text);
    result.replaceChildren(head);
}

function row(label, value, keep) {
    const wrap = node('div');
    wrap.append(node('dt', '', label), node('dd', keep ? 'keep' : '', value));
    return wrap;
}

function showResult(item) {
    const isDocument = item.kind === 'DOCUMENT';
    const revoked = item.status === 'REVOKED';
    const label = isDocument ? item.doc_type_label : 'Certificate';

    result.hidden = false;
    result.className = `result ${revoked ? 'is-bad' : 'is-ok'}`;

    const head = node('div', 'result-head');
    const text = node('div');
    if (revoked) {
        text.append(node('span', '', `${label} revoked`));
        text.append(node('small', '', `Withdrawn by the issuer${item.revoked_at ? ' on ' + item.revoked_at.slice(0, 10) : ''}. It is no longer valid.`));
    } else {
        text.append(node('span', '', `Valid ${label.toLowerCase()}`));
        text.append(node('small', '', 'Issued by the institution and not revoked.'));
    }
    head.append(icon(revoked ? 'x' : 'check'), text);

    const facts = node('dl', 'facts');
    if (isDocument) {
        facts.append(
            row('Holder', item.holder_name), row('Document', item.doc_type_label),
            row('Issued by', item.issuing_institution), row('Number', item.number_masked),
            row('Issued on', item.issue_date), row('Document ID', item.document_id, true));
        if (item.details) {
            facts.append(row('Exam year', String(item.details.exam_year)),
                row('Result', `${item.details.total_marks}/${item.details.max_total_marks} marks · ${item.details.percentage}% · ${item.details.result}`));
        }
    } else {
        facts.append(
            row('Student', item.student_name), row('Student ID', item.student_id), row('Course', item.course),
            row('Issued by', item.institution), row('Issued on', item.issue_date), row('Certificate ID', item.certificate_id, true));
    }

    const foot = node('div', 'result-foot');
    const again = node('button', 'btn btn-sm', 'Check another');
    again.type = 'button';
    again.addEventListener('click', () => { result.hidden = true; idInput.value = ''; fileInput.value = ''; resetDrop(); selectTab('id'); idInput.focus(); });
    foot.append(again);
    result.replaceChildren(head, facts, foot);
}

async function verify(id) {
    showHeadOnly('working', 'search', 'Checking…');
    const response = await fetch(`/api/verify/${encodeURIComponent(id)}`);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
        const detail = typeof data.detail === 'string' ? data.detail : '';
        throw new Error(response.status === 404 && !detail.startsWith('Unknown')
            ? `No record found for ${id}. Check the ID and try again.` : detail || 'Verification failed.');
    }
    showResult(data);
    result.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function fail(error) { showHeadOnly('error', 'alert', 'Could not verify', error.message); }

/* ---------- Tabs ---------- */

function selectTab(method) {
    tabs.forEach((tab) => {
        const active = tab.dataset.method === method;
        tab.classList.toggle('is-active', active);
        tab.setAttribute('aria-selected', String(active));
        tab.tabIndex = active ? 0 : -1;
    });
    Object.entries(panels).forEach(([name, panel]) => { panel.hidden = name !== method; });
    if (method !== 'qr') stopCamera();
}

tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => { selectTab(tab.dataset.method); result.hidden = true; });
    tab.addEventListener('keydown', (event) => {
        const step = { ArrowRight: 1, ArrowLeft: -1 }[event.key];
        if (!step) return;
        const next = tabs[(index + step + tabs.length) % tabs.length];
        next.focus(); next.click();
    });
});

/* ---------- By ID ---------- */

$('id-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const id = idInput.value.trim().toUpperCase();
    if (!id) { fail(new Error('Enter a certificate or document ID.')); return; }
    try { await verify(id); } catch (error) { fail(error); }
});

/* ---------- Camera / QR ---------- */

function setCameraText(text) { $('camera-status').textContent = text; }

async function startCamera() {
    if (!navigator.mediaDevices?.getUserMedia) {
        setCameraText('This browser cannot open the camera here. Use HTTPS or localhost, or enter the ID instead.');
        return;
    }
    if (!window.jsQR) { setCameraText('The QR reader could not load. Check your connection or enter the ID instead.'); return; }
    $('camera-toggle').disabled = true;
    try {
        stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' } }, audio: false });
        video.srcObject = stream;
        video.hidden = false;
        $('camera-idle').hidden = true;
        $('camera-toggle').textContent = 'Stop camera';
        $('camera-toggle').setAttribute('aria-pressed', 'true');
        setCameraText('Looking for a CertiChain QR code…');
        frame = requestAnimationFrame(scan);
    } catch (error) {
        setCameraText(error.name === 'NotAllowedError'
            ? 'Camera permission was denied. Allow it in your browser settings, or enter the ID instead.'
            : 'The camera could not be opened. Enter the ID instead.');
    } finally { $('camera-toggle').disabled = false; }
}

function stopCamera() {
    if (frame) cancelAnimationFrame(frame);
    frame = null;
    stream?.getTracks().forEach((track) => track.stop());
    stream = null;
    video.srcObject = null;
    video.hidden = true;
    $('camera-idle').hidden = false;
    $('camera-toggle').textContent = 'Start camera';
    $('camera-toggle').setAttribute('aria-pressed', 'false');
}

const scratch = document.createElement('canvas');

function scan() {
    if (!stream) return;
    if (video.readyState >= 2 && video.videoWidth) {
        scratch.width = video.videoWidth; scratch.height = video.videoHeight;
        const context = scratch.getContext('2d', { willReadFrequently: true });
        context.drawImage(video, 0, 0);
        const code = window.jsQR(context.getImageData(0, 0, scratch.width, scratch.height).data, scratch.width, scratch.height);
        const match = code && code.data.match(/(?:CERT|DOC)-[A-Z0-9]+/i);
        if (match) {
            const id = match[0].toUpperCase();
            idInput.value = id;
            stopCamera();
            setCameraText(`Scanned ${id}.`);
            verify(id).catch(fail);
            return;
        }
    }
    frame = requestAnimationFrame(scan);
}

$('camera-toggle').addEventListener('click', () => (stream ? (stopCamera(), setCameraText('Camera stopped.')) : startCamera()));

/* ---------- PDF upload ---------- */

function resetDrop() {
    $('drop-title').textContent = 'Choose a certificate PDF';
    $('drop-sub').textContent = 'We read the ID printed in the file and check it.';
}

fileInput.addEventListener('change', () => {
    const file = fileInput.files[0];
    if (!file) { resetDrop(); return; }
    $('drop-title').textContent = file.name;
    $('drop-sub').textContent = `${Math.max(1, Math.round(file.size / 1024))} KB. Select Verify PDF to check it.`;
});

const drop = $('drop');
['dragenter', 'dragover'].forEach((name) => drop.addEventListener(name, (event) => { event.preventDefault(); drop.classList.add('is-over'); }));
['dragleave', 'drop'].forEach((name) => drop.addEventListener(name, (event) => { event.preventDefault(); drop.classList.remove('is-over'); }));
drop.addEventListener('drop', (event) => {
    if (event.dataTransfer.files.length) { fileInput.files = event.dataTransfer.files; fileInput.dispatchEvent(new Event('change')); }
});

$('pdf-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    try {
        const file = fileInput.files[0];
        if (!file) throw new Error('Choose a PDF file first.');
        if (file.type !== 'application/pdf') throw new Error('That file is not a PDF.');
        if (!window.pdfjsLib) throw new Error('The PDF reader could not load. Check your connection or enter the ID instead.');
        showHeadOnly('working', 'search', 'Reading the PDF…');
        const pdf = await pdfjsLib.getDocument({ data: await file.arrayBuffer() }).promise;
        let text = '';
        for (let page = 1; page <= pdf.numPages; page++) {
            const content = await (await pdf.getPage(page)).getTextContent();
            text += content.items.map((item) => item.str).join(' ') + ' ';
        }
        const id = text.match(/(?:CERT|DOC)-[A-Z0-9]+/i)?.[0];
        if (!id) throw new Error('No CertiChain certificate or document ID was found in this PDF.');
        idInput.value = id.toUpperCase();
        await verify(id.toUpperCase());
    } catch (error) { fail(error); }
});

/* ---------- Opened from a QR code or shared link: /user.html?id=CERT-... ---------- */
(function autoVerify() {
    const params = new URLSearchParams(location.search);
    const id = (params.get('id') || params.get('certificate_id') || '').trim().toUpperCase();
    if (!id) return;
    idInput.value = id;
    verify(id).catch(fail);
    $('verify').scrollIntoView({ block: 'start' });
})();
