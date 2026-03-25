document.addEventListener("DOMContentLoaded", () => {
  const picker = document.getElementById("directory-picker");
  const pickBtn = document.getElementById("pick-folder-btn");
  const processBtn = document.getElementById("process-batch-btn");
  const resetFlowBtn = document.getElementById("reset-flow-btn");
  const folderNameEl = document.getElementById("folder-name");
  const fileCountEl = document.getElementById("file-count");
  const filePreviewEl = document.getElementById("file-preview");
  const apiStatusEl = document.getElementById("api-status");
  const apiErrorEl = document.getElementById("api-error");
  const processResultEl = document.getElementById("process-result");
  const processResultMessageEl = document.getElementById("process-result-message");
  const processDownloadWrapEl = document.getElementById("process-download-wrap");
  const processDownloadLinkEl = document.getElementById("process-download-link");
  const batchFailuresAlertEl = document.getElementById("batch-failures-alert");
  const batchFailuresSummaryEl = document.getElementById("batch-failures-summary");
  const batchFailureListEl = document.getElementById("batch-failure-list");
  const batchJobPanelEl = document.getElementById("batch-job-panel");
  const batchStatusBadgeEl = document.getElementById("batch-status-badge");
  const batchStatusIconEl = document.getElementById("batch-status-icon");
  const batchStatusBadgeLabelEl = document.getElementById("batch-status-badge-label");
  const batchStatusDetailEl = document.getElementById("batch-status-detail");
  const selectionViewEl = document.getElementById("selection-view");
  const actionsRowEl = document.getElementById("actions-row");
  const previewSectionEl = document.getElementById("preview-section");
  const categoryPanelEl = document.getElementById("category-panel");
  const categoryBreakdownEl = document.getElementById("category-breakdown");
  const categoriesUnsupportedNoteEl = document.getElementById(
    "categories-unsupported-note"
  );

  /**
   * @type {{
   *   folder: string;
   *   pdfCount: number;
   *   supportedPdfCount: number;
   *   pdfPaths: string[];
   *   uploadJobId: string | null;
   * } | null}
   */
  let lastBatch = null;

  /** Mirrors ``SUPPORTED_BATCH_FOLDER_CATEGORIES`` (``app/core/supported_pdf_categories.py``). */
  const SUPPORTED_FOLDER_CATEGORIES = new Set(["dc"]);

  function stripPickerRootPrefix(parts, rootFolderName) {
    if (!parts.length || !rootFolderName || !String(rootFolderName).trim()) {
      return parts;
    }
    const root = String(rootFolderName).trim();
    if (parts[0].toLowerCase() === root.toLowerCase()) {
      return parts.slice(1);
    }
    return parts;
  }

  function immediateSubfolderCategory(pdfPath, pickerRootFolderName) {
    const rp = String(pdfPath || "").replace(/\\/g, "/").trim();
    let parts = rp.split("/").filter(Boolean);
    parts = stripPickerRootPrefix(parts, pickerRootFolderName);
    if (parts.length <= 1) return "(root)";
    return parts[0];
  }

  function isParserSupportedCategory(categoryName) {
    return SUPPORTED_FOLDER_CATEGORIES.has(
      String(categoryName || "").trim().toLowerCase()
    );
  }

  function sortCategoriesForDisplay(names) {
    const ROOT = "(root)";
    return [...names].sort((a, b) => {
      const asup = isParserSupportedCategory(a);
      const bsup = isParserSupportedCategory(b);
      const aroot = a === ROOT;
      const broot = b === ROOT;
      if (asup !== bsup) return asup ? -1 : 1;
      if (aroot !== broot) return aroot ? 1 : -1;
      return a.localeCompare(b, undefined, { sensitivity: "base" });
    });
  }

  /**
   * Build category counts from picked files (same rules as server ``pdf_category``).
   * @param {string[]} pdfPaths
   * @param {string} rootFolderName
   */
  function summarizeLocalFolderPdfPaths(pdfPaths, rootFolderName) {
    const byCat = new Map();
    for (const p of pdfPaths) {
      const cat = immediateSubfolderCategory(p, rootFolderName);
      byCat.set(cat, (byCat.get(cat) || 0) + 1);
    }
    const categoryNames = sortCategoriesForDisplay(Array.from(byCat.keys()));
    const pdf_categories = categoryNames.map((category_name) => ({
      category_name,
      pdf_count: byCat.get(category_name) || 0,
      parser_supported: isParserSupportedCategory(category_name),
    }));
    const pdf_sample = pdfPaths.slice(0, 10).map((pdf_path) => ({ pdf_path }));
    return {
      pdf_total_count: pdfPaths.length,
      pdf_categories,
      pdf_sample,
    };
  }

  /**
   * After a successful process+download flow for the current folder listing, keep Process
   * disabled until the user picks a folder again (avoids double-submit / duplicate jobs).
   */
  let batchAlreadyProcessedForSelection = false;
  let isProcessingBatch = false;
  let isUploadingToServer = false;
  let ignoreNextPickerChange = false;

  if (
    !picker ||
    !pickBtn ||
    !processBtn ||
    !resetFlowBtn ||
    !folderNameEl ||
    !fileCountEl ||
    !filePreviewEl ||
    !apiStatusEl ||
    !apiErrorEl ||
    !processResultEl ||
    !processResultMessageEl ||
    !processDownloadWrapEl ||
    !processDownloadLinkEl ||
    !batchFailuresAlertEl ||
    !batchFailuresSummaryEl ||
    !batchFailureListEl ||
    !batchJobPanelEl ||
    !batchStatusBadgeEl ||
    !batchStatusIconEl ||
    !batchStatusBadgeLabelEl ||
    !batchStatusDetailEl ||
    !selectionViewEl ||
    !actionsRowEl ||
    !previewSectionEl ||
    !categoryPanelEl ||
    !categoryBreakdownEl ||
    !categoriesUnsupportedNoteEl
  ) {
    return;
  }

  function formatCategoryDisplayName(name) {
    if (name === "(root)") return "Root folder (no subfolder)";
    return name;
  }

  /**
   * @param {Array<{ category_name?: string; pdf_count?: number; parser_supported?: boolean }>} categories
   */
  function renderCategoryBreakdown(categories) {
    categoryBreakdownEl.innerHTML = "";
    categoriesUnsupportedNoteEl.hidden = true;
    categoriesUnsupportedNoteEl.textContent = "";

    if (!categories.length) {
      categoryPanelEl.hidden = true;
      return;
    }

    categoryPanelEl.hidden = false;
    for (const c of categories) {
      const name = typeof c.category_name === "string" ? c.category_name : "?";
      const pdfCount = Number(c.pdf_count ?? 0);
      const supported = Boolean(c.parser_supported);

      const li = document.createElement("li");
      li.className =
        "flex flex-wrap items-center justify-between gap-2 px-4 py-3";

      const left = document.createElement("span");
      left.className = "font-medium text-slate-800";
      left.textContent = formatCategoryDisplayName(name);

      const badge = document.createElement("span");
      if (supported) {
        badge.className =
          "text-xs font-semibold uppercase tracking-wide text-green-800 bg-green-100 px-2 py-0.5 rounded-md";
        badge.textContent = "Supported";
      } else {
        badge.className =
          "text-xs font-semibold uppercase tracking-wide text-slate-600 bg-slate-100 px-2 py-0.5 rounded-md";
        badge.textContent = "Not available yet";
      }

      const countEl = document.createElement("span");
      countEl.className = "text-slate-600 tabular-nums";
      countEl.textContent = `${pdfCount} PDF${pdfCount === 1 ? "" : "s"}`;

      const right = document.createElement("div");
      right.className = "flex items-center gap-2";
      right.appendChild(countEl);
      right.appendChild(badge);

      li.appendChild(left);
      li.appendChild(right);
      categoryBreakdownEl.appendChild(li);
    }

    const unsupported = categories.filter(
      (c) => !c.parser_supported && (Number(c.pdf_count) || 0) > 0
    );
    if (unsupported.length) {
      const names = unsupported
        .map((c) =>
          formatCategoryDisplayName(
            typeof c.category_name === "string" ? c.category_name : "?"
          )
        )
        .join(", ");
      categoriesUnsupportedNoteEl.hidden = false;
      categoriesUnsupportedNoteEl.textContent =
        `These categories are listed for your reference only — they are not processed yet: ${names}. ` +
        `Only PDFs inside a "DC" subfolder are parsed today; support for other folders will be added later.`;
    }
  }

  function renderLucideIcons() {
    if (window.lucide && typeof window.lucide.createIcons === "function") {
      window.lucide.createIcons();
    }
  }

  renderLucideIcons();

  function getFolderNameFromWebkitRelativePath(webkitRelativePath) {
    if (!webkitRelativePath) return null;
    return webkitRelativePath.split("/")[0] || null;
  }

  /** @param {File[]} files */
  function collectPdfPathsFromFileList(files) {
    const out = [];
    for (const f of files) {
      const p = f.webkitRelativePath || f.name;
      const base = (p.split("/").pop() || "").toLowerCase();
      if (base.endsWith(".pdf")) out.push(p);
    }
    return out;
  }

  async function uploadFolderToBackend(files, rootFolderName) {
    const form = new FormData();
    form.append("root_folder_name", rootFolderName);

    for (const f of files) {
      const rel = f.webkitRelativePath || f.name;
      const base = String(rel || "").toLowerCase().split("/").pop() || "";
      if (!base.endsWith(".pdf")) continue;

      // Use the browser relative path as the multipart filename so the server
      // can reconstruct the folder layout.
      form.append("files", f, rel);
    }

    const res = await fetch("/api/upload-folder", {
      method: "POST",
      body: form,
    });

    let data = null;
    try {
      data = await res.json();
    } catch {
      data = null;
    }

    if (!res.ok) {
      throw new Error(errorMessageFromFetchResponse(res, data));
    }
    if (
      !data ||
      typeof data !== "object" ||
      typeof data.upload_job_id !== "string"
    ) {
      throw new Error(
        "Upload succeeded but server did not return an upload job id. Try again."
      );
    }
    return data;
  }

  /**
   * Confirm the batch output file exists on the server before offering download.
   * @param {string} downloadUrl - Same-origin path e.g. /api/download/batch-output/...
   */
  async function verifyBatchOutputExists(downloadUrl) {
    let res;
    try {
      res = await fetch(downloadUrl, { method: "HEAD", cache: "no-store" });
    } catch (netErr) {
      throw new Error(formatErrorForUser(netErr));
    }
    if (!res.ok) {
      const hint = friendlyHttpStatusMessage(res.status);
      throw new Error(
        hint ||
        `Could not confirm the output file on the server (HTTP ${res.status}). Try running the batch again.`
      );
    }
  }

  function renderPreviewFromPaths(paths, maxItems) {
    filePreviewEl.innerHTML = "";
    const items = paths.slice(0, maxItems);
    for (const p of items) {
      const li = document.createElement("li");
      li.className =
        "group flex items-center gap-2 px-3 py-2 rounded-lg border border-slate-100 bg-white hover:bg-slate-50 transition";

      const icon = document.createElement("i");
      icon.setAttribute("data-lucide", "file-text");
      icon.className = "icon icon-inline text-slate-500";
      icon.setAttribute("aria-hidden", "true");

      const text = document.createElement("span");
      text.textContent = p;
      text.className =
        "truncate text-sm text-slate-700 group-hover:text-slate-900";

      li.appendChild(icon);
      li.appendChild(text);
      filePreviewEl.appendChild(li);
    }
    renderLucideIcons();
  }

  function setError(message) {
    if (message) {
      apiErrorEl.hidden = false;
      apiErrorEl.textContent = message;
      try {
        apiErrorEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
      } catch {
        /* older browsers */
      }
    } else {
      apiErrorEl.hidden = true;
      apiErrorEl.textContent = "";
    }
  }

  function setStatus(text) {
    apiStatusEl.textContent = text || "";
  }

  /**
   * FastAPI may return detail as string, validation array, or nested object.
   * @param {unknown} detail
   * @returns {string}
   */
  function parseFastApiDetail(detail) {
    if (detail == null) return "";
    if (typeof detail === "string") {
      const s = detail.trim();
      return s;
    }
    if (Array.isArray(detail)) {
      const parts = [];
      for (const item of detail) {
        if (item && typeof item === "object") {
          const msg = item.msg;
          const loc = Array.isArray(item.loc)
            ? item.loc
              .filter((x) => x !== "body" && x != null && String(x))
              .join(" → ")
            : "";
          if (typeof msg === "string" && msg.trim()) {
            parts.push(loc ? `${loc}: ${msg}` : msg);
          }
        } else if (typeof item === "string") {
          parts.push(item);
        }
      }
      return parts.join(" ").trim();
    }
    if (typeof detail === "object") {
      const d = detail;
      if (typeof d.msg === "string" && d.msg.trim()) return d.msg.trim();
      if (typeof d.message === "string" && d.message.trim()) {
        return d.message.trim();
      }
    }
    try {
      return JSON.stringify(detail);
    } catch {
      return "";
    }
  }

  /**
   * @param {number} status
   * @returns {string}
   */
  function friendlyHttpStatusMessage(status) {
    switch (status) {
      case 400:
        return "The server could not use this request. Check your input and try again.";
      case 401:
        return "You are not authorized for this action.";
      case 403:
        return "Access was denied. Check permissions and try again.";
      case 404:
        return "That resource was not found. It may have expired — try the previous step again.";
      case 408:
        return "The request timed out. Try again.";
      case 422:
        return "Some inputs were invalid. Review your selection and try again.";
      case 429:
        return "Too many requests. Wait a moment and try again.";
      case 502:
      case 503:
      case 504:
        return "The service is temporarily unavailable. Try again in a moment.";
      default:
        if (status >= 500) {
          return "The server had an error. Please try again later.";
        }
        return "";
    }
  }

  /**
   * Build a user-safe message from a fetch Response and optional parsed JSON body.
   * @param {Response} res
   * @param {Record<string, unknown> | null} parsedJson
   * @returns {string}
   */
  function errorMessageFromFetchResponse(res, parsedJson) {
    const detailMsg =
      parsedJson &&
        typeof parsedJson === "object" &&
        "detail" in parsedJson
        ? parseFastApiDetail(parsedJson.detail)
        : "";
    if (detailMsg) return detailMsg;
    const fallback = friendlyHttpStatusMessage(res.status);
    if (fallback) return fallback;
    const st = (res.statusText || "").trim();
    if (st) return `${st} (HTTP ${res.status})`;
    return `Something went wrong (HTTP ${res.status}).`;
  }

  /**
   * Turn thrown errors into safe UI copy (no stack dumps).
   * @param {unknown} err
   * @returns {string}
   */
  function formatErrorForUser(err) {
    if (err instanceof TypeError) {
      const m = err.message || "";
      if (/load failed|fetch|network|aborted|failed to fetch/i.test(m)) {
        return "Could not reach the server. Check your connection and that the app is running, then try again.";
      }
    }
    if (err instanceof Error && err.message) {
      let m = err.message.trim();
      if (!m || m === "[object Object]") {
        return "Something went wrong. Please try again.";
      }
      if (m.length > 1500) {
        m = `${m.slice(0, 1500)}…`;
      }
      return m;
    }
    if (typeof err === "string" && err.trim()) {
      return err.trim().length > 1500 ? `${err.trim().slice(0, 1500)}…` : err.trim();
    }
    return "Something went wrong. Please try again.";
  }

  /**
   * Hide batch progress UI (badge + detail). General `#api-status` can be used again.
   */
  function hideBatchJobUi() {
    batchJobPanelEl.hidden = true;
    batchStatusDetailEl.textContent = "";
    batchStatusBadgeLabelEl.textContent = "";
    batchStatusBadgeEl.className = "batch-status-badge";
  }

  /**
   * Simple state machine for the UX.
   * @param {"idle" | "selection" | "processing" | "done"} state
   */
  function updateUIState(state) {
    if (state === "idle") {
      selectionViewEl.hidden = true;
      batchJobPanelEl.hidden = true;
      processResultEl.hidden = true;
      actionsRowEl.hidden = false;
      previewSectionEl.hidden = false;
      return;
    }

    selectionViewEl.hidden = false;

    if (state === "selection") {
      batchJobPanelEl.hidden = true;
      processResultEl.hidden = true;
      actionsRowEl.hidden = false;
      previewSectionEl.hidden = false;
      return;
    }

    if (state === "processing") {
      batchJobPanelEl.hidden = false;
      processResultEl.hidden = true;
      actionsRowEl.hidden = true;
      previewSectionEl.hidden = true;
      return;
    }

    // done
    batchJobPanelEl.hidden = true;
    actionsRowEl.hidden = false;
    previewSectionEl.hidden = false;
  }

  /**
   * @param {"submitting" | "queued" | "running" | "completed" | "completed-warnings" | "failed"} badgeKind
   * @param {string} badgeTitle - Short label: Queued, In progress, etc.
   * @param {string} detailText - Extra line from server or our copy (never raw URLs).
   */
  function setBatchJobUi(badgeKind, badgeTitle, detailText) {
    const iconByKind = {
      queued: "file-text",
      running: "file-text",
      completed: "check-circle",
      "completed-warnings": "alert-triangle",
      failed: "file-text",
      submitting: "folder",
    };
    const iconName = iconByKind[badgeKind] || "file-text";
    batchStatusIconEl.setAttribute("data-lucide", iconName);
    batchJobPanelEl.hidden = false;
    apiStatusEl.textContent = "";
    batchStatusBadgeEl.className = `batch-status-badge batch-status-badge--${badgeKind}`;
    batchStatusBadgeLabelEl.textContent = badgeTitle;
    batchStatusDetailEl.textContent = detailText;
    renderLucideIcons();
  }

  /**
   * @param {Record<string, unknown>} data - status JSON (may include failed_paths)
   * @param {string} baseDetail
   * @returns {string}
   */
  function appendFailedPathsToDetail(data, baseDetail) {
    const fp = data.failed_paths;
    if (!Array.isArray(fp) || fp.length === 0) {
      return baseDetail;
    }
    const lines = fp.map((row) => {
      const p =
        row && typeof row.pdf_path === "string" ? row.pdf_path : "?";
      const err =
        row && typeof row.error === "string"
          ? row.error
          : "Unknown error.";
      return `• ${p}: ${err}`;
    });
    return (
      `${baseDetail}\n\nCould not process ${fp.length} file(s):\n` +
      lines.join("\n")
    );
  }

  /**
   * @param {Record<string, unknown>} data - `GET /api/process-batch/status/{job_id}` JSON
   */
  function updateBatchUiFromPollData(data) {
    const st = /** @type {string} */ (data.status);
    const fp = data.failed_paths;
    const nFailPoll = Array.isArray(fp) ? fp.length : 0;

    const titleByStatus = {
      queued: "Queued",
      running: "In progress",
      completed: "Completed",
      failed: "Failed",
    };
    const title =
      st === "completed" && nFailPoll > 0
        ? "Finished with issues"
        : titleByStatus[st] || "Working…";
    const kind =
      st === "failed"
        ? "failed"
        : st === "completed" && nFailPoll > 0
          ? "completed-warnings"
          : st === "completed"
            ? "completed"
            : st === "running"
              ? "running"
              : st === "queued"
                ? "queued"
                : "submitting";
    const msg =
      typeof data.message === "string" && data.message.trim()
        ? data.message.trim()
        : "";
    const checked = new Date().toLocaleTimeString(undefined, {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
    let detail = msg
      ? `${msg} · Last checked ${checked}`
      : `Last checked ${checked}`;
    if (st === "completed") {
      detail = appendFailedPathsToDetail(data, detail);
    }
    setBatchJobUi(kind, title, detail);
  }

  function resetBatchFailurePanel() {
    batchFailuresAlertEl.hidden = true;
    batchFailureListEl.innerHTML = "";
    batchFailuresSummaryEl.textContent = "";
    processResultEl.classList.remove("process-result--warnings");
    processResultEl.classList.add("process-result--ok");
  }

  /**
   * @param {Array<{ pdf_path?: string; error?: string }>} fp
   * @param {number} attempted
   * @param {number} nFail
   */
  function revealPreDownloadFailures(fp, attempted, nFail) {
    processResultEl.hidden = false;
    processResultEl.classList.remove("process-result--ok");
    processResultEl.classList.add("process-result--warnings");
    batchFailuresAlertEl.hidden = false;
    const ok = Math.max(0, attempted - nFail);
    const head =
      attempted > 0
        ? `This batch included ${attempted} PDF path(s). ${nFail} could not be processed.`
        : `${nFail} file(s) could not be processed.`;
    const tail =
      ok > 0 ? ` ${ok} path(s) produced rows in the spreadsheet.` : "";
    batchFailuresSummaryEl.textContent = head + tail;
    batchFailureListEl.innerHTML = "";
    for (const row of fp) {
      const li = document.createElement("li");
      const p =
        row && typeof row.pdf_path === "string" ? row.pdf_path : "?";
      const err =
        row && typeof row.error === "string" ? row.error : "Unknown error.";
      li.textContent = `${p}: ${err}`;
      batchFailureListEl.appendChild(li);
    }
    processResultMessageEl.textContent =
      "Review the errors above before downloading. The same details are in the FailedPaths sheet.";
    processDownloadWrapEl.hidden = true;
    renderLucideIcons();
  }

  function setProcessResult(text) {
    processDownloadWrapEl.hidden = true;
    processDownloadLinkEl.href = "#";
    processDownloadLinkEl.removeAttribute("download");
    if (text) {
      processResultEl.hidden = false;
      processResultMessageEl.textContent = text;
    } else {
      resetBatchFailurePanel();
      processResultEl.hidden = true;
      processResultMessageEl.textContent = "";
    }
  }

  /**
   * @param {string} url - Same-origin download URL from the API.
   * @param {string} [filename] - Suggested filename for the browser download attribute.
   */
  function showDownloadLink(url, filename) {
    processResultEl.hidden = false;
    processDownloadLinkEl.href = url;
    if (filename) processDownloadLinkEl.setAttribute("download", filename);
    else processDownloadLinkEl.removeAttribute("download");
    processDownloadWrapEl.hidden = false;
  }

  function syncProcessButton() {
    const total = lastBatch?.pdfCount ?? 0;
    const supported = lastBatch?.supportedPdfCount ?? 0;
    const hasPdfs = Boolean(lastBatch?.folder) && total > 0;
    if (!hasPdfs) {
      processBtn.disabled = true;
      processBtn.removeAttribute("title");
      return;
    }
    if (isUploadingToServer) {
      processBtn.disabled = true;
      processBtn.title = "Uploading PDFs to the server…";
      return;
    }
    if (!lastBatch?.uploadJobId) {
      processBtn.disabled = true;
      processBtn.title = "Upload must finish before processing.";
      return;
    }
    if (supported < 1) {
      processBtn.disabled = true;
      processBtn.title =
        'Only PDFs under a "DC" subfolder can be processed right now. Add or move PDFs into "DC" to run the batch.';
      return;
    }
    if (batchAlreadyProcessedForSelection) {
      processBtn.disabled = true;
      processBtn.title =
        "This folder was already processed. Choose the folder again to run another batch.";
      return;
    }
    processBtn.disabled = false;
    processBtn.removeAttribute("title");
  }

  function syncResetButton() {
    const hasSelection = Boolean(lastBatch?.folder);
    if (!hasSelection) {
      resetFlowBtn.disabled = true;
      resetFlowBtn.title = "Select a folder first.";
      return;
    }
    if (isProcessingBatch) {
      resetFlowBtn.disabled = true;
      resetFlowBtn.title = "Cannot reset while processing is in progress.";
      return;
    }
    resetFlowBtn.disabled = false;
    resetFlowBtn.removeAttribute("title");
  }

  const reset = () => {
    folderNameEl.textContent = "None";
    fileCountEl.textContent = "0";
    renderPreviewFromPaths([], 10);
    renderCategoryBreakdown([]);
    categoryPanelEl.hidden = true;
    setError("");
    setStatus("");
    hideBatchJobUi();
    setProcessResult("");
    updateUIState("idle");
    lastBatch = null;
    batchAlreadyProcessedForSelection = false;
    isUploadingToServer = false;
    syncProcessButton();
    syncResetButton();
    pickBtn.disabled = false;
    processBtn.disabled = true;
  };

  reset();

  pickBtn.addEventListener("click", () => {
    // If reset didn't trigger a synthetic `change`, don't let the next real pick get ignored.
    ignoreNextPickerChange = false;
    picker.click();
  });

  resetFlowBtn.addEventListener("click", () => {
    if (isProcessingBatch) {
      setError("Cannot reset while processing is in progress.");
      return;
    }
    const shouldReset = window.confirm(
      "Reset the current flow? This clears selected folder, preview, progress, and download link."
    );
    if (!shouldReset) return;
    // Some browsers fire `change` when value is cleared; others don't.
    // We guard only that synthetic event and then immediately clear the guard.
    ignoreNextPickerChange = true;
    if (picker) picker.value = "";
    queueMicrotask(() => {
      ignoreNextPickerChange = false;
    });
    reset();
  });

  async function startBatchJob() {
    if (
      !lastBatch?.folder ||
      !lastBatch?.uploadJobId ||
      (lastBatch.pdfCount ?? 0) < 1 ||
      (lastBatch.supportedPdfCount ?? 0) < 1
    ) {
      return null;
    }

    const body = {
      root_folder: lastBatch.folder,
      upload_job_id: lastBatch.uploadJobId,
    };

    let res;
    try {
      res = await fetch("/api/process-batch", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify(body),
      });
    } catch (netErr) {
      throw new Error(formatErrorForUser(netErr));
    }

    let data = null;
    try {
      data = await res.json();
    } catch {
      data = null;
    }

    if (res.status !== 202) {
      throw new Error(errorMessageFromFetchResponse(res, data));
    }
    if (!data || typeof data !== "object" || !data.job_id) {
      throw new Error(
        "The server accepted the batch but did not return a job id. Try again."
      );
    }
    /** Never rely on `status_url` for display — poll using `job_id` only. */
    return { job_id: data.job_id, message: data.message };
  }

  /** How often to re-check job status after the previous check completes (ms). */
  const BATCH_STATUS_POLL_MS = 5000;

  function batchStatusPollUrl(jobId) {
    return `/api/process-batch/status/${encodeURIComponent(jobId)}`;
  }

  async function fetchBatchJobStatus(jobId) {
    let res;
    try {
      res = await fetch(batchStatusPollUrl(jobId), {
        headers: { Accept: "application/json" },
      });
    } catch (netErr) {
      throw new Error(formatErrorForUser(netErr));
    }

    let data = null;
    try {
      data = await res.json();
    } catch {
      data = null;
    }

    if (!res.ok) {
      throw new Error(errorMessageFromFetchResponse(res, data));
    }
    if (!data || typeof data !== "object") {
      throw new Error("Could not read batch status. Try refreshing or starting a new batch.");
    }
    return data;
  }

  /**
   * Poll until the job completes or fails (server runs work in the background).
   * Updates badge + detail after every successful status check (uses `job_id` only).
   * @param {string} jobId
   * @param {{ onUpdate?: (data: Record<string, unknown>) => void }} [opts]
   */
  async function pollBatchUntilDone(jobId, opts) {
    const deadline = Date.now() + 5 * 60 * 1000;
    while (Date.now() < deadline) {
      const data = await fetchBatchJobStatus(jobId);
      if (opts?.onUpdate) opts.onUpdate(data);
      else updateBatchUiFromPollData(data);

      if (data.status === "completed") return data;
      if (data.status === "failed") {
        const ed =
          typeof data.error_detail === "string" && data.error_detail.trim()
            ? data.error_detail.trim()
            : "";
        const mg =
          typeof data.message === "string" && data.message.trim()
            ? data.message.trim()
            : "";
        const combined = [ed, mg].filter(Boolean).join(" ");
        throw new Error(
          combined ||
          "Processing could not finish. Try again or contact support if it keeps happening."
        );
      }
      await new Promise((r) => setTimeout(r, BATCH_STATUS_POLL_MS));
    }
    throw new Error(
      "Timed out waiting for the batch to finish. Check the server logs and try again."
    );
  }

  processBtn.addEventListener("click", async () => {
    if (
      !lastBatch?.folder ||
      (lastBatch.pdfCount ?? 0) < 1 ||
      (lastBatch.supportedPdfCount ?? 0) < 1
    ) {
      return;
    }
    isProcessingBatch = true;
    setError("");
    setProcessResult("");
    setStatus("");
    updateUIState("processing");
    setBatchJobUi(
      "submitting",
      "Submitting…",
      "Sending your batch to the server. Next we’ll poll for job status (queued → in progress → done)."
    );
    processBtn.disabled = true;
    processBtn.setAttribute("aria-busy", "true");
    pickBtn.disabled = true;
    syncResetButton();

    try {
      const accepted = await startBatchJob();
      if (!accepted) return;

      const done = await pollBatchUntilDone(accepted.job_id, {
        onUpdate: (data) => updateBatchUiFromPollData(data),
      });

      const fp = Array.isArray(done.failed_paths) ? done.failed_paths : [];
      const nFail = fp.length;
      const attemptedRaw = done.pdf_paths_attempted;
      const attempted =
        typeof attemptedRaw === "number" && attemptedRaw >= 0
          ? attemptedRaw
          : nFail;

      const dl = typeof done.download_url === "string" ? done.download_url : "";
      if (!dl) {
        throw new Error("Server did not return a download link for the output file.");
      }

      if (nFail > 0) {
        revealPreDownloadFailures(fp, attempted, nFail);
        const msg0 =
          typeof done.message === "string" && done.message.trim()
            ? done.message.trim()
            : "Processing finished with one or more file errors.";
        setBatchJobUi(
          "completed-warnings",
          "Finished with issues",
          appendFailedPathsToDetail(done, msg0)
        );
      } else {
        resetBatchFailurePanel();
        setBatchJobUi(
          "completed",
          "Completed",
          "Verifying the output file on the server before showing the download link…"
        );
      }

      await verifyBatchOutputExists(dl);

      const doneBase =
        (typeof done.message === "string" && done.message.trim()
          ? done.message.trim()
          : "Processing finished.") +
        " · Download is available below.";

      if (nFail > 0) {
        setBatchJobUi(
          "completed-warnings",
          "Finished with issues",
          appendFailedPathsToDetail(done, doneBase)
        );
        processResultMessageEl.textContent =
          "Download is ready. Open the workbook to compare ParsedRows with the FailedPaths sheet.";
        processResultEl.hidden = false;
      } else {
        setBatchJobUi(
          "completed",
          "Completed",
          appendFailedPathsToDetail(done, doneBase)
        );
        processResultEl.hidden = false;
        processResultEl.classList.add("process-result--ok");
        setProcessResult("Output file is ready.");
      }

      updateUIState("done");
      const base = dl.split("/").pop() || "batch-output.xlsx";
      showDownloadLink(dl, base);
      batchAlreadyProcessedForSelection = true;
    } catch (e) {
      const message = formatErrorForUser(e);
      setError(message);
      setBatchJobUi("failed", "Failed", message);
      setProcessResult("");
      batchAlreadyProcessedForSelection = false;
      updateUIState("selection");
    } finally {
      isProcessingBatch = false;
      processBtn.removeAttribute("aria-busy");
      pickBtn.disabled = false;
      syncProcessButton();
      syncResetButton();
    }
  });

  picker.addEventListener("change", async () => {
    if (ignoreNextPickerChange) {
      ignoreNextPickerChange = false;
      return;
    }
    const files = Array.from(picker.files || []);
    if (files.length === 0) {
      reset();
      return;
    }

    const folderName = getFolderNameFromWebkitRelativePath(files[0].webkitRelativePath);
    const displayRoot = folderName || "Selected folder";
    folderNameEl.textContent = displayRoot;
    setError("");
    setProcessResult("");
    hideBatchJobUi();
    lastBatch = null;
    batchAlreadyProcessedForSelection = false;
    syncProcessButton();
    syncResetButton();
    setStatus("Scanning selected folder…");
    pickBtn.disabled = true;
    processBtn.disabled = true;

    try {
      const pdfPaths = collectPdfPathsFromFileList(files);
      const data = summarizeLocalFolderPdfPaths(pdfPaths, displayRoot);
      const pdfCount = Number(data.pdf_total_count ?? 0);
      fileCountEl.textContent = String(pdfCount);
      const pdfCategories = data.pdf_categories;
      const supportedPdfCount = pdfCategories.reduce(
        (n, c) =>
          n +
          (c.parser_supported ? Number(c.pdf_count ?? 0) || 0 : 0),
        0
      );
      renderCategoryBreakdown(pdfCategories);
      if (pdfCount < 1) {
        categoryPanelEl.hidden = true;
      }
      const samplePaths = (data.pdf_sample || []).map((e) => e.pdf_path);
      renderPreviewFromPaths(samplePaths, 10);
      lastBatch = {
        folder: displayRoot,
        pdfCount,
        supportedPdfCount,
        pdfPaths,
        uploadJobId: null,
      };
      console.info(
        "[LeadfFlow] Picked folder:",
        displayRoot,
        "— uploading PDFs to the server for staged processing."
      );
      if (pdfCount > 0) {
        isUploadingToServer = true;
        setStatus(`Uploading ${pdfCount} PDFs to the server…`);
        const up = await uploadFolderToBackend(files, displayRoot);
        lastBatch.uploadJobId = up.upload_job_id;
        isUploadingToServer = false;
        console.info(
          "[LeadfFlow] Upload complete:",
          up.upload_job_id,
          "staging_dir:",
          up.staging_dir
        );
        setStatus("Upload complete — review, then click “Process folder”.");
      } else {
        setStatus("No PDFs in this folder — pick another folder or add PDFs.");
      }
      syncProcessButton();
      syncResetButton();
      updateUIState("selection");
    } catch (e) {
      const message = formatErrorForUser(e);
      console.warn("[LeadfFlow] folder scan failed for folder:", displayRoot, e);
      setError(message);
      setStatus("");
      fileCountEl.textContent = "0";
      renderPreviewFromPaths([], 10);
      renderCategoryBreakdown([]);
      categoryPanelEl.hidden = true;
      lastBatch = null;
      isUploadingToServer = false;
      syncProcessButton();
      syncResetButton();
      updateUIState("selection");
    } finally {
      pickBtn.disabled = false;
      isUploadingToServer = false;
    }
  });
});
