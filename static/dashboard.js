(() => {
  "use strict";

  // ---------- Element refs ----------
  const apiKeyInput = document.getElementById("api-key-input");
  const saveApiKeyBtn = document.getElementById("save-api-key");
  const authStatus = document.getElementById("auth-status");

  const statTotal = document.getElementById("stat-total");
  const statUnreviewed = document.getElementById("stat-unreviewed");
  const statLowConf = document.getElementById("stat-lowconf");
  const statAvg = document.getElementById("stat-avg");

  const filterButtons = Array.from(document.querySelectorAll(".dash-filter"));
  const searchInput = document.getElementById("dash-search");
  const sortSelect = document.getElementById("dash-sort");
  const refreshBtn = document.getElementById("dash-refresh");

  const dashHint = document.getElementById("dash-hint");
  const dashTable = document.getElementById("dash-table");
  const dashEmpty = document.getElementById("dash-empty");
  const dashRows = document.getElementById("dash-rows");
  const selectAllCheckbox = document.getElementById("select-all");

  const bulkBar = document.getElementById("bulk-bar");
  const bulkCount = document.getElementById("bulk-count");
  const bulkMarkReviewedBtn = document.getElementById("bulk-mark-reviewed");
  const bulkClearBtn = document.getElementById("bulk-clear");

  const API_KEY_STORAGE_KEY = "scriptgrader_api_key";

  let allRecords = [];
  let activeFilter = "all";
  let searchTerm = "";
  let sortMode = "date-desc";
  const selectedIds = new Set();

  // ============================================================
  // API key
  // ============================================================

  function getApiKey() {
    return localStorage.getItem(API_KEY_STORAGE_KEY) || "";
  }

  function authHeaders() {
    const key = getApiKey();
    return key ? { "X-API-Key": key, "Content-Type": "application/json" } : { "Content-Type": "application/json" };
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
    loadQueue();
  });

  // ============================================================
  // Loading the queue
  // ============================================================

  async function loadQueue() {
    if (!getApiKey()) {
      dashHint.hidden = false;
      dashHint.textContent = "Enter your API key above to load the review queue.";
      dashTable.hidden = true;
      dashEmpty.hidden = true;
      updateStats([]);
      return;
    }

    dashHint.hidden = false;
    dashHint.textContent = "Loading…";
    dashTable.hidden = true;

    try {
      const response = await fetch("/api/evaluations?limit=200", { headers: authHeaders() });
      if (response.status === 401) {
        dashHint.textContent = "Invalid API key — queue unavailable.";
        updateStats([]);
        return;
      }
      if (!response.ok) throw new Error(`status ${response.status}`);

      allRecords = await response.json();
      dashHint.hidden = true;
      updateStats(allRecords);
      render();
    } catch {
      dashHint.hidden = false;
      dashHint.textContent = "Couldn't load the queue. Try refreshing.";
    }
  }

  function updateStats(records) {
    statTotal.textContent = records.length;
    statUnreviewed.textContent = records.filter((r) => !r.reviewed).length;
    statLowConf.textContent = records.filter((r) => r.low_confidence).length;
    if (records.length === 0) {
      statAvg.textContent = "—";
    } else {
      const pctSum = records.reduce(
        (sum, r) => sum + (r.total_max > 0 ? (r.total_awarded / r.total_max) * 100 : 0),
        0
      );
      statAvg.textContent = `${Math.round(pctSum / records.length)}%`;
    }
  }

  // ============================================================
  // Filtering / sorting / rendering
  // ============================================================

  filterButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      filterButtons.forEach((b) => {
        b.classList.remove("is-active");
        b.setAttribute("aria-selected", "false");
      });
      btn.classList.add("is-active");
      btn.setAttribute("aria-selected", "true");
      activeFilter = btn.dataset.filter;
      render();
    });
  });

  searchInput.addEventListener("input", () => {
    searchTerm = searchInput.value.trim().toLowerCase();
    render();
  });

  sortSelect.addEventListener("change", () => {
    sortMode = sortSelect.value;
    render();
  });

  refreshBtn.addEventListener("click", loadQueue);

  function getFiltered() {
    let records = allRecords;

    if (activeFilter === "unreviewed") records = records.filter((r) => !r.reviewed);
    else if (activeFilter === "reviewed") records = records.filter((r) => r.reviewed);
    else if (activeFilter === "lowconf") records = records.filter((r) => r.low_confidence);

    if (searchTerm) {
      records = records.filter((r) => r.question_number.toLowerCase().includes(searchTerm));
    }

    const sorted = [...records];
    switch (sortMode) {
      case "date-asc":
        sorted.sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
        break;
      case "score-asc":
        sorted.sort((a, b) => pct(a) - pct(b));
        break;
      case "score-desc":
        sorted.sort((a, b) => pct(b) - pct(a));
        break;
      case "date-desc":
      default:
        sorted.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
    }
    return sorted;
  }

  function pct(record) {
    return record.total_max > 0 ? (record.total_awarded / record.total_max) * 100 : 0;
  }

  function render() {
    const records = getFiltered();
    dashRows.innerHTML = "";

    if (records.length === 0) {
      dashTable.hidden = true;
      dashEmpty.hidden = false;
      updateBulkBar();
      return;
    }

    dashEmpty.hidden = true;
    dashTable.hidden = false;

    records.forEach((record) => {
      const row = document.createElement("tr");
      row.className = "dash-row";
      if (record.low_confidence) row.classList.add("dash-row--lowconf");

      const scorePct = Math.round(pct(record));
      const flags = [];
      if (record.low_confidence) flags.push('<span class="flag-chip flag-chip--red">Low confidence</span>');

      row.innerHTML = `
        <td><input type="checkbox" class="dash-row__select" data-id="${escapeHtml(record.id)}" aria-label="Select row"></td>
        <td class="dash-table__expand-col">
          <button type="button" class="expand-toggle" aria-expanded="false" aria-label="Show explanation">▸</button>
        </td>
        <td class="dash-table__question">Q${escapeHtml(record.question_number)}</td>
        <td class="dash-table__score">${roundClean(record.total_awarded)}/${roundClean(record.total_max)} <span class="dash-table__pct">(${scorePct}%)</span></td>
        <td>${escapeHtml(record.grade || "—")}</td>
        <td>
          <span class="status-chip ${record.reviewed ? "status-chip--reviewed" : "status-chip--unreviewed"}">
            ${record.reviewed ? "Reviewed" : "Awaiting review"}
          </span>
        </td>
        <td>${flags.join(" ") || "—"}</td>
        <td class="dash-table__date">${formatDate(record.created_at)}</td>
        <td class="dash-table__action-col">
          <a href="/index.html?eval=${encodeURIComponent(record.id)}" class="btn btn--ghost btn--small">Review →</a>
        </td>
      `;

      const checkbox = row.querySelector(".dash-row__select");
      checkbox.checked = selectedIds.has(record.id);
      checkbox.addEventListener("change", () => {
        if (checkbox.checked) selectedIds.add(record.id);
        else selectedIds.delete(record.id);
        updateBulkBar();
      });

      const detailRow = buildDetailRow(record);
      const toggle = row.querySelector(".expand-toggle");
      toggle.addEventListener("click", () => {
        const isOpen = detailRow.hidden === false;
        detailRow.hidden = isOpen;
        toggle.setAttribute("aria-expanded", String(!isOpen));
        toggle.textContent = isOpen ? "▸" : "▾";
        row.classList.toggle("dash-row--expanded", !isOpen);
      });

      dashRows.appendChild(row);
      dashRows.appendChild(detailRow);
    });

    updateBulkBar();
  }

  function buildDetailRow(record) {
    const tr = document.createElement("tr");
    tr.className = "dash-detail-row";
    tr.hidden = true;

    const criteriaHtml = (record.criteria || [])
      .map((c) => {
        const ratio = c.max_marks > 0 ? c.awarded / c.max_marks : 0;
        const kind = ratio >= 0.999 ? "full" : ratio <= 0.001 ? "zero" : "partial";
        return `
          <div class="explain-item explain-item--${kind}">
            <div class="explain-item__head">
              <span class="explain-item__name">${escapeHtml(c.name)}</span>
              <span class="explain-item__marks">${roundClean(c.awarded)} / ${roundClean(c.max_marks)}</span>
            </div>
            <p class="explain-item__evidence">${escapeHtml(c.evidence)}</p>
            <p class="explain-item__reason">${escapeHtml(c.reason)}</p>
          </div>
        `;
      })
      .join("");

    tr.innerHTML = `
      <td colspan="9">
        <div class="dash-explain">
          <div class="dash-explain__criteria">${criteriaHtml}</div>
          ${
            record.overall_feedback
              ? `<div class="dash-explain__overall">
                   <span class="dash-explain__overall-label">Overall feedback</span>
                   <p>${escapeHtml(record.overall_feedback)}</p>
                 </div>`
              : ""
          }
        </div>
      </td>
    `;
    return tr;
  }

  selectAllCheckbox.addEventListener("change", () => {
    const visible = getFiltered();
    if (selectAllCheckbox.checked) {
      visible.forEach((r) => selectedIds.add(r.id));
    } else {
      visible.forEach((r) => selectedIds.delete(r.id));
    }
    render();
  });

  function updateBulkBar() {
    const count = selectedIds.size;
    bulkBar.hidden = count === 0;
    bulkCount.textContent = `${count} selected`;
  }

  bulkClearBtn.addEventListener("click", () => {
    selectedIds.clear();
    render();
  });

  // ============================================================
  // Bulk mark-reviewed
  // ============================================================

  bulkMarkReviewedBtn.addEventListener("click", async () => {
    const ids = Array.from(selectedIds);
    if (ids.length === 0) return;

    bulkMarkReviewedBtn.disabled = true;
    bulkMarkReviewedBtn.textContent = "Marking…";

    let failures = 0;
    for (const id of ids) {
      const record = allRecords.find((r) => r.id === id);
      if (!record) continue;
      // Re-send existing awarded marks unchanged — this marks the record
      // reviewed without altering any score (the API requires at least
      // one criterion in the override payload).
      const criteria = record.criteria.map((c) => ({ name: c.name, awarded: c.awarded }));
      try {
        const response = await fetch(`/api/evaluations/${id}`, {
          method: "PATCH",
          headers: authHeaders(),
          body: JSON.stringify({ criteria }),
        });
        if (!response.ok) failures += 1;
      } catch {
        failures += 1;
      }
    }

    bulkMarkReviewedBtn.disabled = false;
    bulkMarkReviewedBtn.textContent = "Mark reviewed";
    selectedIds.clear();

    if (failures > 0) {
      dashHint.hidden = false;
      dashHint.textContent = `Marked ${ids.length - failures} of ${ids.length} — ${failures} failed. Try again.`;
    }
    await loadQueue();
  });

  // ============================================================
  // Utilities
  // ============================================================

  function roundClean(n) {
    const num = Number(n);
    if (Number.isNaN(num)) return "0";
    const rounded = Math.round(num * 100) / 100;
    return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
  }

  function formatDate(iso) {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "—";
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" }) +
      " · " + d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = String(str ?? "");
    return div.innerHTML;
  }

  // ---------- Init ----------
  initApiKeyField();
  loadQueue();
})();
