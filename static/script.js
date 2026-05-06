// ======================== DOM ELEMENTS ========================
const dropzone = document.getElementById('dropzone');
const fileInput = document.getElementById('fileInput');
const dropzoneContent = document.getElementById('dropzoneContent');
const previewContainer = document.getElementById('previewContainer');
const imagePreview = document.getElementById('imagePreview');
const removeBtn = document.getElementById('removeBtn');
const historyInput = document.getElementById('historyInput');
const generateBtn = document.getElementById('generateBtn');
const btnContent = document.getElementById('btnContent');
const btnLoading = document.getElementById('btnLoading');
const generateHint = document.getElementById('generateHint');
const reportSection = document.getElementById('reportSection');
const reportMeta = document.getElementById('reportMeta');
const findingsBody = document.getElementById('findingsBody');
const impressionBody = document.getElementById('impressionBody');
const recommendationsBody = document.getElementById('recommendationsBody');
const disclaimerText = document.getElementById('disclaimerText');
const rawOutput = document.getElementById('rawOutput');
const headerStatus = document.getElementById('headerStatus');

let selectedFile = null;

// ======================== HEALTH CHECK ========================
async function checkHealth() {
    const dot = headerStatus.querySelector('.status-dot');
    const text = headerStatus.querySelector('.status-text');
    try {
        const res = await fetch('/api/health');
        const data = await res.json();
        if (data.status === 'ready') {
            dot.className = 'status-dot ready';
            text.textContent = `Model ready (${data.device.toUpperCase()})`;
        } else {
            dot.className = 'status-dot';
            text.textContent = 'Model loading...';
            setTimeout(checkHealth, 3000);
        }
    } catch {
        dot.className = 'status-dot error';
        text.textContent = 'Server offline';
        setTimeout(checkHealth, 5000);
    }
}
checkHealth();

// ======================== FILE HANDLING ========================
dropzone.addEventListener('click', () => fileInput.click());

dropzone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropzone.classList.add('dragover');
});
dropzone.addEventListener('dragleave', () => {
    dropzone.classList.remove('dragover');
});
dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropzone.classList.remove('dragover');
    const files = e.dataTransfer.files;
    if (files.length > 0 && files[0].type.startsWith('image/')) {
        handleFile(files[0]);
    }
});

fileInput.addEventListener('change', () => {
    if (fileInput.files.length > 0) {
        handleFile(fileInput.files[0]);
    }
});

removeBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    clearFile();
});

function handleFile(file) {
    selectedFile = file;
    const reader = new FileReader();
    reader.onload = (e) => {
        imagePreview.src = e.target.result;
        dropzoneContent.style.display = 'none';
        previewContainer.style.display = 'block';
        generateBtn.disabled = false;
        generateHint.textContent = 'Ready to generate';
    };
    reader.readAsDataURL(file);
}

function clearFile() {
    selectedFile = null;
    fileInput.value = '';
    imagePreview.src = '';
    dropzoneContent.style.display = 'block';
    previewContainer.style.display = 'none';
    generateBtn.disabled = true;
    generateHint.textContent = 'Upload an X-ray image to begin';
}

// ======================== GENERATE REPORT ========================
generateBtn.addEventListener('click', async () => {
    if (!selectedFile) return;

    // UI: loading state
    btnContent.style.display = 'none';
    btnLoading.style.display = 'flex';
    generateBtn.disabled = true;
    generateHint.textContent = 'This may take few seconds';
    reportSection.style.display = 'none';

    const formData = new FormData();
    formData.append('image', selectedFile);
    formData.append('history', historyInput.value.trim());

    try {
        const res = await fetch('/api/generate', {
            method: 'POST',
            body: formData,
        });

        const data = await res.json();

        if (!res.ok) {
            throw new Error(data.error || 'Server error');
        }

        displayReport(data);
    } catch (err) {
        generateHint.textContent = `Error: ${err.message}`;
        generateHint.style.color = '#f87171';
    } finally {
        btnContent.style.display = 'flex';
        btnLoading.style.display = 'none';
        generateBtn.disabled = false;
    }
});

// ======================== DISPLAY REPORT ========================
function displayReport(data) {
    const { sections, raw_report, inference_time, device } = data;

    const patientId = 'MRN-' + Math.floor(Math.random() * 1000000);

    // Store report data for PDF export
    lastReportData = { sections, raw_report, history: historyInput.value.trim(), patientId };

    // Meta info for UI
    reportMeta.innerHTML = `
        <span>⚡ ${inference_time}s</span>
        <span>🖥️ ${device.toUpperCase()}</span>
    `;

    // Fill PDF Document Header Info
    const dateObj = new Date();
    document.getElementById('docDate').textContent = dateObj.toLocaleDateString('en-US', {
        year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit'
    });

    const historyText = historyInput.value.trim();
    document.getElementById('docHistory').textContent = historyText ? historyText : "Not provided.";
    document.getElementById('docPatientId').textContent = patientId;

    // Findings
    if (sections.findings && sections.findings.length > 0) {
        findingsBody.innerHTML = '<ol>' +
            sections.findings.map(f => `<li>${escapeHtml(f)}</li>`).join('') +
            '</ol>';
    } else {
        findingsBody.innerHTML = '<p class="no-data">No specific findings extracted.</p>';
    }

    // Impression — render as structured list
    if (sections.impression && sections.impression.length > 0) {
        impressionBody.innerHTML = '<ul style="list-style-type: disc; margin-left: 20px;">' +
            sections.impression.map(i => `<li style="margin-bottom: 8px; line-height: 1.5;">${escapeHtml(i)}</li>`).join('') +
            '</ul>';
    } else {
        impressionBody.innerHTML = '<p class="no-data">No impression extracted.</p>';
    }

    // Recommendations
    recommendationsBody.innerHTML = '<ul>' +
        sections.recommendations.map(r => `<li>${escapeHtml(r)}</li>`).join('') +
        '</ul>';

    // Disclaimer
    disclaimerText.textContent = '⚠️ ' + sections.disclaimer;

    // Raw output
    rawOutput.textContent = raw_report;

    // Show Report Section
    reportSection.style.display = 'block';
    generateHint.textContent = 'Report generated successfully';
    generateHint.style.color = '';

    // Scroll to report
    reportSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ======================== STORE REPORT DATA FOR PDF ========================
let lastReportData = null;

// ======================== PDF EXPORT (jsPDF text-based) ========================
document.getElementById('downloadPdfBtn').addEventListener('click', () => {
    if (!lastReportData) return;

    const { jsPDF } = window.jspdf;
    const doc = new jsPDF({ unit: 'pt', format: 'letter' });
    const pageWidth = doc.internal.pageSize.getWidth();
    const pageHeight = doc.internal.pageSize.getHeight();
    const margin = 50;
    const contentWidth = pageWidth - margin * 2;
    let y = margin;

    // ── Helper: add new page if needed ──
    function checkPage(needed) {
        if (y + needed > pageHeight - 60) {
            doc.addPage();
            y = margin;
        }
    }

    // ── Helper: draw wrapped text, returns new Y ──
    function drawWrappedText(text, x, startY, maxWidth, fontSize, color) {
        doc.setFontSize(fontSize);
        doc.setTextColor(...color);
        const lines = doc.splitTextToSize(text, maxWidth);
        for (const line of lines) {
            checkPage(fontSize + 4);
            doc.text(line, x, startY);
            startY += fontSize + 4;
        }
        return startY;
    }

    // ══════════════════════════════════════════════
    //  HEADER
    // ══════════════════════════════════════════════

    // Top accent bar
    doc.setFillColor(56, 189, 248);
    doc.rect(0, 0, pageWidth, 6, 'F');
    y = 36;

    // Logo
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(22);
    doc.setTextColor(14, 165, 233);
    doc.text('MedReport AI', pageWidth / 2, y, { align: 'center' });
    y += 24;

    // Title
    doc.setFontSize(14);
    doc.setTextColor(51, 65, 85);
    doc.text('RADIOLOGY EXAMINATION REPORT', pageWidth / 2, y, { align: 'center' });
    y += 18;

    // Date
    const dateStr = new Date().toLocaleDateString('en-US', {
        year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit'
    });
    doc.setFont('helvetica', 'normal');
    doc.setFontSize(10);
    doc.setTextColor(100, 116, 139);
    doc.text(dateStr, pageWidth / 2, y, { align: 'center' });
    y += 14;

    // Divider line
    doc.setDrawColor(226, 232, 240);
    doc.setLineWidth(1.5);
    doc.line(margin, y, pageWidth - margin, y);
    y += 20;

    // ══════════════════════════════════════════════
    //  PATIENT INFO BOX
    // ══════════════════════════════════════════════
    const boxH = 70;
    doc.setFillColor(248, 250, 252);
    doc.setDrawColor(226, 232, 240);
    doc.roundedRect(margin, y, contentWidth, boxH, 4, 4, 'FD');

    const infoY = y + 18;
    // Left column
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(8);
    doc.setTextColor(100, 116, 139);
    doc.text('PATIENT ID', margin + 14, infoY);
    doc.setFont('helvetica', 'normal');
    doc.setFontSize(11);
    doc.setTextColor(30, 41, 59);
    doc.text(lastReportData.patientId || 'MRN-UNKNOWN', margin + 14, infoY + 14);

    // Right column
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(8);
    doc.setTextColor(100, 116, 139);
    doc.text('EXAM TYPE', pageWidth / 2 + 10, infoY);
    doc.setFont('helvetica', 'normal');
    doc.setFontSize(11);
    doc.setTextColor(30, 41, 59);
    doc.text('Chest X-Ray (PA/Lateral)', pageWidth / 2 + 10, infoY + 14);

    // History row
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(8);
    doc.setTextColor(100, 116, 139);
    doc.text('CLINICAL INDICATION / HISTORY', margin + 14, infoY + 34);
    doc.setFont('helvetica', 'normal');
    doc.setFontSize(10);
    doc.setTextColor(30, 41, 59);
    const histText = lastReportData.history || 'Not provided.';
    const histLines = doc.splitTextToSize(histText, contentWidth - 28);
    doc.text(histLines[0], margin + 14, infoY + 46);

    y += boxH + 28;

    // ══════════════════════════════════════════════
    //  SECTION HELPER
    // ══════════════════════════════════════════════
    function drawSection(title, items, bulletChar) {
        checkPage(40);
        // Section title
        doc.setFont('helvetica', 'bold');
        doc.setFontSize(12);
        doc.setTextColor(2, 132, 199);
        doc.text(title, margin, y);
        y += 4;
        doc.setDrawColor(203, 213, 225);
        doc.setLineWidth(0.5);
        doc.line(margin, y, pageWidth - margin, y);
        y += 16;

        // Section items
        doc.setFont('helvetica', 'normal');
        doc.setFontSize(11);
        doc.setTextColor(51, 65, 85);

        if (items && items.length > 0) {
            items.forEach((item, idx) => {
                const prefix = bulletChar === '#' ? `${idx + 1}. ` : `${bulletChar} `;
                const fullText = sanitizeForPdf(prefix + item);
                const lines = doc.splitTextToSize(fullText, contentWidth - 20);
                for (const line of lines) {
                    checkPage(16);
                    doc.text(line, margin + 10, y);
                    y += 15;
                }
                y += 3;
            });
        } else {
            doc.setFont('helvetica', 'italic');
            doc.setTextColor(148, 163, 184);
            doc.text('No data available.', margin + 10, y);
            y += 15;
        }
        y += 10;
    }

    // ══════════════════════════════════════════════
    //  BODY SECTIONS
    // ══════════════════════════════════════════════
    drawSection('FINDINGS', lastReportData.sections.findings, '#');
    drawSection('IMPRESSION', lastReportData.sections.impression, '>');
    drawSection('RECOMMENDATIONS', lastReportData.sections.recommendations, '-');

    // ══════════════════════════════════════════════
    //  FOOTER
    // ══════════════════════════════════════════════
    checkPage(100);
    y += 10;
    doc.setDrawColor(226, 232, 240);
    doc.setLineWidth(0.5);
    doc.line(margin, y, pageWidth - margin, y);
    y += 16;

    // Disclaimer (left)
    doc.setFont('helvetica', 'normal');
    doc.setFontSize(9);
    doc.setTextColor(239, 68, 68);
    const disclaimerLines = doc.splitTextToSize(
        lastReportData.sections.disclaimer, contentWidth * 0.55
    );
    const disclaimerStartY = y;
    for (const line of disclaimerLines) {
        doc.text(line, margin, y);
        y += 12;
    }

    // Signature (right)
    const sigX = pageWidth - margin - 160;
    let sigY = disclaimerStartY;
    doc.setDrawColor(148, 163, 184);
    doc.line(sigX, sigY + 20, sigX + 150, sigY + 20);
    sigY += 32;
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(11);
    doc.setTextColor(30, 41, 59);
    doc.text('MedReport AI System', sigX, sigY);
    sigY += 14;
    doc.setFont('helvetica', 'normal');
    doc.setFontSize(9);
    doc.setTextColor(100, 116, 139);
    doc.text('Automated Radiology Assistant', sigX, sigY);
    sigY += 12;
    doc.setFont('helvetica', 'italic');
    doc.setFontSize(8);
    doc.setTextColor(148, 163, 184);
    doc.text('Powered by ViT (rad-dino) + BioGPT', sigX, sigY);

    // Save
    doc.save(`Radiology_Report_${new Date().getTime()}.pdf`);
});

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Strip non-ASCII characters that break jsPDF's built-in fonts
function sanitizeForPdf(text) {
    return text
        .replace(/[\u2014\u2013]/g, '-')   // em-dash, en-dash -> hyphen
        .replace(/[\u2018\u2019]/g, "'")   // smart quotes -> apostrophe
        .replace(/[\u201C\u201D]/g, '"')   // smart double quotes -> quote
        .replace(/[\u2022]/g, '-')          // bullet -> hyphen
        .replace(/[\u2192]/g, '>')          // arrow -> greater-than
        .replace(/[^\x00-\x7F]/g, '');     // strip any remaining non-ASCII
}
