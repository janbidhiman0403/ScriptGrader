(() => {
  "use strict";

  const MAX_UPLOAD_MB = 10;
  const ACCEPTED_TYPES = ["image/jpeg", "image/png", "image/webp"];

  // ---------- Element refs ----------
  const form = document.getElementById("grade-form");
  const rubricRows = document.getElementById("rubric-rows");
  const rubricTotalHint = document.getElementById("rubric-total-hint");
  const addCriterionBtn = document.getElementById("add-criterion");
  const dropzone = document.getElementById("dropzone");
  const dropzoneContent = document.getElementById("dropzone-content");
  const dropzonePreview = document.getElementById("dropzone-preview");
  const fileInput = document.getElementById("sheet-image");
  const submitBtn = document.getElementById("submit-btn");
  const formError = document.getElementById("form-error");

  const emptyState = document.getElementById("empty-state");
  const loadingState = document.getElementById("loading-state");
  const errorState = document.getElementById("error-state");
  const errorTitle = document.getElementById("error-title");
  const errorMessage = document.getElementById("error-message");
  const retryBtn = document.getElementById("retry-btn");
  const resultEl = document.getElementById("result");
  const markedSheetContainer = document.getElementById("marked-sheet-container");
  const markedSheetImage = document.getElementById("marked-sheet-image");
  const markedSheetCanvas = document.getElementById("marked-sheet-canvas");

  const apiKeyInput = document.getElementById("api-key-input");
  const saveApiKeyBtn = document.getElementById("save-api-key");
  const authStatus = document.getElementById("auth-status");

  const reviewToggle = document.getElementById("review-toggle");
  const reviewControls = document.getElementById("review-controls");
  const reviewNoteInput = document.getElementById("review-note-input");
  const saveOverrideBtn = document.getElementById("save-override");
  const reviewedBanner = document.getElementById("reviewed-banner");

  const historyHint = document.getElementById("history-hint");
  const historyRows = document.getElementById("history-rows");
  const refreshHistoryBtn = document.getElementById("refresh-history");

  let currentCriteria = [];
  let highlightedIndex = null;
  let currentEvaluationId = null;
  let isReviewMode = false;

  let rubricRowCount = 0;
  let lastFormData = null;
  let lastImageDataUrl = null;

  // ============================================================
  // API key (stored locally; sent as X-API-Key on every authed call)
  // ============================================================

  const API_KEY_STORAGE_KEY = "scriptgrader_api_key";

  function getApiKey() {
    return localStorage.getItem(API_KEY_STORAGE_KEY) || "";
  }

  function authHeaders() {
    const key = getApiKey();
    return key ? { "X-API-Key": key } : {};
  }

  function initApiKeyField() {
    const stored = getApiKey();
    if (stored) {
      apiKeyInput.value = stored;
      setAuthStatus("saved", "ok");
    }
  }

  function setAuthStatus(text, kind) {
    authStatus.textContent = text;
    authStatus.hidden = false;
    authStatus.className = `auth-bar__status is-${kind}`;
  }

  saveApiKeyBtn.addEventListener("click", () => {
    const value = apiKeyInput.value.trim();
    if (!value) {
      localStorage.removeItem(API_KEY_STORAGE_KEY);
      authStatus.hidden = true;
      return;
    }
    localStorage.setItem(API_KEY_STORAGE_KEY, value);
    setAuthStatus("saved", "ok");
    loadHistory();
  });

  // ============================================================
  // Rubric builder
  // ============================================================

  function addRubricRow(name = "", marks = "") {
    rubricRowCount += 1;
    const id = rubricRowCount;

    const row = document.createElement("div");
    row.className = "rubric-row";
    row.dataset.rowId = String(id);
    row.innerHTML = `
      <input type="text" class="criterion-name" placeholder="Concept accuracy" value="${escapeHtml(name)}" aria-label="Criterion name">
      <input type="text" class="marks" inputmode="decimal" placeholder="marks" value="${escapeHtml(String(marks))}" aria-label="Max marks">
      <button type="button" class="rubric-row__remove" aria-label="Remove criterion">&times;</button>
    `;

    row.querySelector(".rubric-row__remove").addEventListener("click", () => {
      row.remove();
      updateRubricTotal();
    });
    row.querySelector(".marks").addEventListener("input", updateRubricTotal);

    rubricRows.appendChild(row);
    updateRubricTotal();
  }

  function updateRubricTotal() {
    const marksInputs = rubricRows.querySelectorAll(".marks");
    let total = 0;
    marksInputs.forEach((input) => {
      const val = parseFloat(input.value);
      if (!Number.isNaN(val)) total += val;
    });
    rubricTotalHint.textContent = `Total: ${roundClean(total)} marks`;
  }

  function collectRubric() {
    const rows = Array.from(rubricRows.querySelectorAll(".rubric-row"));
    return rows
      .map((row) => {
        const name = row.querySelector(".criterion-name").value.trim();
        const marksRaw = row.querySelector(".marks").value.trim();
        const marks = parseFloat(marksRaw);
        return { name, marks, valid: name.length > 0 && !Number.isNaN(marks) && marks > 0 };
      })
      .filter((r) => r.name.length > 0 || r.marks);
  }

  addCriterionBtn.addEventListener("click", () => addRubricRow());
  addRubricRow("Concept accuracy", 5);
  addRubricRow("Completeness", 5);

  // ============================================================
  // File upload (dropzone)
  // ============================================================

  dropzone.addEventListener("click", () => fileInput.click());
  dropzone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      fileInput.click();
    }
  });

  ["dragenter", "dragover"].forEach((evt) =>
    dropzone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropzone.classList.add("is-dragover");
    })
  );
  ["dragleave", "drop"].forEach((evt) =>
    dropzone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropzone.classList.remove("is-dragover");
    })
  );
  dropzone.addEventListener("drop", (e) => {
    const file = e.dataTransfer?.files?.[0];
    if (file) {
      fileInput.files = e.dataTransfer.files;
      handleFileSelected(file);
    }
  });
  fileInput.addEventListener("change", () => {
    const file = fileInput.files?.[0];
    if (file) handleFileSelected(file);
  });

  function handleFileSelected(file) {
    clearFormError();

    if (!ACCEPTED_TYPES.includes(file.type)) {
      showFormError(`"${file.name}" isn't a supported image type. Use JPEG, PNG, or WebP.`);
      fileInput.value = "";
      return;
    }
    if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
      showFormError(`That image is ${(file.size / 1_048_576).toFixed(1)} MB — the limit is ${MAX_UPLOAD_MB} MB.`);
      fileInput.value = "";
      return;
    }

    const reader = new FileReader();
    reader.onload = (e) => {
      dropzonePreview.src = e.target.result;
      dropzonePreview.hidden = false;
      dropzoneContent.hidden = true;
      lastImageDataUrl = e.target.result;
    };
    reader.onerror = () => {
      showFormError("Couldn't read that file. Try a different image.");
      fileInput.value = "";
    };
    reader.readAsDataURL(file);
  }

  // ============================================================
  // Form submission
  // ============================================================

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    clearFormError();

    const validationError = validateForm();
    if (validationError) {
      showFormError(validationError);
      return;
    }

    const formData = buildFormData();
    lastFormData = formData;
    await submitGrading(formData);
  });

  retryBtn.addEventListener("click", async () => {
    if (lastFormData) await submitGrading(lastFormData);
  });

  function validateForm() {
    const questionNumber = document.getElementById("question-number").value.trim();
    const questionText = document.getElementById("question-text").value.trim();
    const modelAnswer = document.getElementById("model-answer").value.trim();
    const file = fileInput.files?.[0];
    const rubric = collectRubric();

    if (!questionNumber) return "Enter a question number.";
    if (!questionText) return "Enter the question text.";
    if (!modelAnswer) return "Enter a model answer or key points.";
    if (!file) return "Upload an image of the handwritten answer.";
    if (rubric.length === 0) return "Add at least one rubric criterion.";

    const invalid = rubric.find((r) => !r.valid);
    if (invalid) {
      return "Every rubric criterion needs a name and a positive mark value.";
    }

    return null;
  }

  function buildFormData() {
    const rubric = collectRubric().map((r) => ({
      name: r.name,
      max_marks: r.marks,
      description: "",
    }));

    const fd = new FormData();
    fd.append("question_number", document.getElementById("question-number").value.trim());
    fd.append("question_text", document.getElementById("question-text").value.trim());
    fd.append("model_answer", document.getElementById("model-answer").value.trim());
    fd.append("rubric_json", JSON.stringify(rubric));
    fd.append("sheet_image", fileInput.files[0]);
    return fd;
  }

  async function submitGrading(formData) {
    setSubmitting(true);
    showLoading();

    try {
      const response = await fetch("/api/grade", {
        method: "POST",
        headers: authHeaders(),
        body: formData,
      });
      const payload = await safeParseJson(response);

      if (!response.ok) {
        throw new ApiError(
          payload?.message || payload?.detail || `Request failed with status ${response.status}.`,
          response.status
        );
      }

      renderResult(payload);
      loadHistory();
    } catch (err) {
      if (err instanceof ApiError) {
        showError(errorTitleFor(err.status), err.message);
      } else if (err instanceof TypeError) {
        // fetch() throws TypeError on network failure (server down, offline, CORS)
        showError("Couldn't reach the server", "Check your connection and that the grading service is running, then try again.");
      } else {
        showError("Something went wrong", err.message || "An unexpected error occurred. Please try again.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  class ApiError extends Error {
    constructor(message, status) {
      super(message);
      this.status = status;
    }
  }

  async function safeParseJson(response) {
    try {
      return await response.json();
    } catch {
      return null;
    }
  }

  function errorTitleFor(status) {
    if (status === 401) return "Invalid API key";
    if (status === 429) return "Rate limit reached";
    if (status === 413) return "Image too large";
    if (status === 400 || status === 422) return "Check your input";
    if (status === 502) return "Grading service unavailable";
    return "Grading failed";
  }

  function setSubmitting(isSubmitting) {
    submitBtn.disabled = isSubmitting;
    submitBtn.textContent = isSubmitting ? "Grading…" : "Grade answer";
  }

  // ============================================================
  // Results panel states
  // ============================================================

  function showEmpty() {
    emptyState.hidden = false;
    loadingState.hidden = true;
    errorState.hidden = true;
    resultEl.hidden = true;
  }

  function showLoading() {
    emptyState.hidden = true;
    loadingState.hidden = false;
    errorState.hidden = true;
    resultEl.hidden = true;
  }

  function showError(title, message) {
    emptyState.hidden = true;
    loadingState.hidden = true;
    errorState.hidden = false;
    resultEl.hidden = true;
    errorTitle.textContent = title;
    errorMessage.textContent = message;
  }

  function renderResult(data, meta = {}) {
    emptyState.hidden = true;
    loadingState.hidden = true;
    errorState.hidden = true;
    resultEl.hidden = false;

    currentEvaluationId = meta.id || null;
    isReviewMode = false;
    reviewControls.hidden = true;
    reviewNoteInput.value = "";
    reviewToggle.hidden = !currentEvaluationId;
    reviewedBanner.hidden = !meta.reviewed;
    if (meta.reviewed && meta.review_note) {
      reviewedBanner.textContent = `Reviewed by a teacher: "${meta.review_note}"`;
    } else if (meta.reviewed) {
      reviewedBanner.textContent = "Reviewed by a teacher.";
    }

    document.getElementById("result-question-number").textContent = `Question ${data.question_number}`;
    document.getElementById("result-grade").textContent = data.grade;
    document.getElementById("score-value").textContent = `${roundClean(data.total_awarded)}/${roundClean(data.total_max)}`;

    const pct = data.total_max > 0 ? (data.total_awarded / data.total_max) * 100 : 0;
    document.getElementById("score-pct").textContent = `${roundClean(pct)}%`;

    document.getElementById("low-confidence-banner").hidden = !data.low_confidence;
    document.getElementById("transcript-body").textContent = data.transcription || "";
    document.getElementById("overall-feedback").textContent = data.overall_feedback || "";

    currentCriteria = data.criteria || [];
    renderLedger();
    setupMarkedSheet();
  }

  function renderLedger() {
    const ledgerRows = document.getElementById("ledger-rows");
    ledgerRows.innerHTML = "";

    currentCriteria.forEach((criterion, idx) => {
      const ratio = criterion.max_marks > 0 ? criterion.awarded / criterion.max_marks : 0;
      const rowClass = ratio >= 0.999 ? "ledger-row--full" : ratio <= 0.001 ? "ledger-row--zero" : "ledger-row--partial";

      const marksCell = isReviewMode
        ? `<input type="number" class="ledger-row__marks-input" data-criterion-name="${escapeHtml(criterion.name)}"
             value="${criterion.awarded}" min="0" max="${criterion.max_marks}" step="0.5"> / ${roundClean(criterion.max_marks)}`
        : `${roundClean(criterion.awarded)} / ${roundClean(criterion.max_marks)}`;

      const row = document.createElement("div");
      row.className = `ledger-row ${rowClass}`;
      row.dataset.criterionIndex = String(idx);
      row.innerHTML = `
        <div class="ledger-row__bar"></div>
        <div>
          <p class="ledger-row__name">${escapeHtml(criterion.name)}</p>
          <p class="ledger-row__evidence">${escapeHtml(criterion.evidence)}</p>
          <p class="ledger-row__reason">${escapeHtml(criterion.reason)}</p>
        </div>
        <div class="ledger-row__marks">${marksCell}</div>
      `;
      if (criterion.bounding_box && !isReviewMode) {
        row.addEventListener("mouseenter", () => setHighlight(idx));
        row.addEventListener("mouseleave", () => setHighlight(null));
        row.addEventListener("click", () => setHighlight(idx));
      }
      ledgerRows.appendChild(row);
    });
  }

  // ============================================================
  // Marked-sheet overlay (bounding boxes over the original image)
  // ============================================================

  function setupMarkedSheet() {
    const hasBoxes = currentCriteria.some((c) => c.bounding_box) && lastImageDataUrl;
    if (!hasBoxes) {
      markedSheetContainer.hidden = true;
      return;
    }
    markedSheetContainer.hidden = false;
    highlightedIndex = null;

    if (markedSheetImage.src !== lastImageDataUrl) {
      markedSheetImage.src = lastImageDataUrl;
    }
    if (markedSheetImage.complete) {
      drawOverlay();
    } else {
      markedSheetImage.onload = drawOverlay;
    }
  }

  function setHighlight(idx) {
    highlightedIndex = idx;
    drawOverlay();
    document.querySelectorAll(".ledger-row").forEach((row) => {
      row.classList.toggle("is-active", Number(row.dataset.criterionIndex) === idx);
    });
  }

  function drawOverlay() {
    if (markedSheetContainer.hidden) return;

    const width = markedSheetImage.clientWidth;
    const height = markedSheetImage.clientHeight;
    if (!width || !height) return;

    markedSheetCanvas.width = width;
    markedSheetCanvas.height = height;
    const ctx = markedSheetCanvas.getContext("2d");
    ctx.clearRect(0, 0, width, height);

    currentCriteria.forEach((criterion, idx) => {
      const box = criterion.bounding_box;
      if (!box) return;

      const ratio = criterion.max_marks > 0 ? criterion.awarded / criterion.max_marks : 0;
      const color = ratio >= 0.999 ? "31, 122, 92" : ratio <= 0.001 ? "178, 58, 46" : "156, 115, 39";
      const isActive = idx === highlightedIndex;

      const x = clamp01(box.x) * width;
      const y = clamp01(box.y) * height;
      const w = clamp01(box.width) * width;
      const h = clamp01(box.height) * height;

      ctx.fillStyle = `rgba(${color}, ${isActive ? 0.28 : 0.14})`;
      ctx.fillRect(x, y, w, h);
      ctx.strokeStyle = `rgba(${color}, ${isActive ? 1 : 0.6})`;
      ctx.lineWidth = isActive ? 2.5 : 1.5;
      ctx.strokeRect(x, y, w, h);
    });
  }

  markedSheetCanvas.addEventListener("click", (e) => {
    const rect = markedSheetCanvas.getBoundingClientRect();
    const clickX = (e.clientX - rect.left) / rect.width;
    const clickY = (e.clientY - rect.top) / rect.height;

    const hitIndex = currentCriteria.findIndex((c) => {
      const box = c.bounding_box;
      if (!box) return false;
      return (
        clickX >= box.x && clickX <= box.x + box.width &&
        clickY >= box.y && clickY <= box.y + box.height
      );
    });

    setHighlight(hitIndex === -1 ? null : hitIndex);
  });

  window.addEventListener("resize", () => {
    if (!markedSheetContainer.hidden) drawOverlay();
  });

  function clamp01(n) {
    return Math.min(1, Math.max(0, Number(n) || 0));
  }

  // ============================================================
  // Teacher review / override
  // ============================================================

  reviewToggle.addEventListener("click", () => {
    isReviewMode = !isReviewMode;
    reviewControls.hidden = !isReviewMode;
    reviewToggle.textContent = isReviewMode ? "Cancel" : "Override marks";
    highlightedIndex = null;
    renderLedger();
  });

  saveOverrideBtn.addEventListener("click", async () => {
    if (!currentEvaluationId) return;

    const inputs = document.querySelectorAll(".ledger-row__marks-input");
    const criteria = Array.from(inputs).map((input) => ({
      name: input.dataset.criterionName,
      awarded: parseFloat(input.value),
    }));

    if (criteria.some((c) => Number.isNaN(c.awarded) || c.awarded < 0)) {
      showFormError("Marks must be zero or a positive number.");
      return;
    }

    saveOverrideBtn.disabled = true;
    saveOverrideBtn.textContent = "Saving…";

    try {
      const response = await fetch(`/api/evaluations/${currentEvaluationId}`, {
        method: "PATCH",
        headers: { ...authHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({
          criteria,
          review_note: reviewNoteInput.value.trim() || null,
        }),
      });
      const payload = await safeParseJson(response);

      if (!response.ok) {
        throw new ApiError(payload?.detail || payload?.message || "Override failed.", response.status);
      }

      renderResult(payload, { id: payload.id, reviewed: payload.reviewed, review_note: payload.review_note });
      loadHistory();
    } catch (err) {
      showFormError(err instanceof ApiError ? err.message : "Couldn't save the override. Try again.");
    } finally {
      saveOverrideBtn.disabled = false;
      saveOverrideBtn.textContent = "Save override";
    }
  });

  // ============================================================
  // History panel
  // ============================================================

  async function loadHistory() {
    if (!getApiKey()) {
      historyHint.hidden = false;
      historyHint.textContent = "Enter your API key above to load history.";
      historyRows.innerHTML = "";
      return;
    }

    try {
      const response = await fetch("/api/evaluations?limit=20", { headers: authHeaders() });
      if (response.status === 401) {
        historyHint.hidden = false;
        historyHint.textContent = "Invalid API key — history unavailable.";
        historyRows.innerHTML = "";
        return;
      }
      if (!response.ok) throw new Error(`status ${response.status}`);

      const records = await response.json();
      historyHint.hidden = records.length > 0;
      historyHint.textContent = "No evaluations yet — grade an answer to see it here.";
      renderHistoryList(records);
    } catch {
      historyHint.hidden = false;
      historyHint.textContent = "Couldn't load history. Try refreshing.";
    }
  }

  function renderHistoryList(records) {
    historyRows.innerHTML = "";
    records.forEach((record) => {
      const pct = record.total_max > 0 ? Math.round((record.total_awarded / record.total_max) * 100) : 0;
      const row = document.createElement("div");
      row.className = "history-row";
      row.innerHTML = `
        <span class="history-row__question">Question ${escapeHtml(record.question_number)}</span>
        <span class="history-row__score">${roundClean(record.total_awarded)}/${roundClean(record.total_max)} (${pct}%)</span>
        <span class="history-row__badge ${record.reviewed ? "history-row__badge--reviewed" : "history-row__badge--unreviewed"}">
          ${record.reviewed ? "Reviewed" : "Unreviewed"}
        </span>
      `;
      row.addEventListener("click", () => loadEvaluationIntoView(record.id));
      historyRows.appendChild(row);
    });
  }

  async function loadEvaluationIntoView(id) {
    try {
      const response = await fetch(`/api/evaluations/${id}`, { headers: authHeaders() });
      if (!response.ok) throw new Error(`status ${response.status}`);
      const record = await response.json();
      lastImageDataUrl = null; // history records don't retain the original image client-side
      renderResult(record, { id: record.id, reviewed: record.reviewed, review_note: record.review_note });
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch {
      showFormError("Couldn't load that evaluation. Try refreshing history.");
    }
  }

  refreshHistoryBtn.addEventListener("click", loadHistory);

  // ============================================================
  // Utilities
  // ============================================================

  function showFormError(message) {
    formError.textContent = message;
    formError.hidden = false;
  }

  function clearFormError() {
    formError.hidden = true;
    formError.textContent = "";
  }

  function roundClean(n) {
    const num = Number(n);
    if (Number.isNaN(num)) return "0";
    const rounded = Math.round(num * 100) / 100;
    return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = String(str ?? "");
    return div.innerHTML;
  }

  // ---------- Init ----------
  initApiKeyField();
  showEmpty();
  loadHistory();
})();
