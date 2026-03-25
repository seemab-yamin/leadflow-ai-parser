/**
 * Folder discovery (categories / buckets) and parser-available badges are client-side UX only.
 * `POST /api/process-batch` must send `selection`; the server maps each file’s category from that payload.
 */
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
  const bucketSelectionPanelEl = document.getElementById("bucket-selection-panel");
  const bucketSelectionCategoriesEl = document.getElementById(
    "bucket-selection-categories"
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

  /**
   * UX-only hint for badges; server truth is `resolve_parser_key_for_user_category_folder`.
   */
  const PARSER_AVAILABLE_CATEGORY_FOLDERS = new Set(["dc"]);

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

  function categoryFolderHasParser(categoryName) {
    return PARSER_AVAILABLE_CATEGORY_FOLDERS.has(
      String(categoryName || "").trim().toLowerCase()
    );
  }

  function sortCategoryNamesForDisplay(names) {
    const ROOT = "(root)";
    return [...names].sort((a, b) => {
      const aroot = a === ROOT;
      const broot = b === ROOT;
      if (aroot !== broot) return aroot ? 1 : -1;
      return a.localeCompare(b, undefined, { sensitivity: "base" });
    });
  }

  /**
   * @typedef {{ pdfCount: number, parserAvailable: boolean }} BucketScanBucket
   * @typedef {{ buckets: Map<string, BucketScanBucket>, parserAvailable: boolean }} BucketScanCategory
   * Scan picked files: category = first segment under root; bucket = next segment (or "" for PDFs directly in category).
   * @param {File[]} files
   * @param {string} rootFolderName
   * @returns {Map<string, BucketScanCategory>}
   */
  function scanFolderBucketHierarchy(files, rootFolderName) {
    const categories = new Map();
    const root = String(rootFolderName || "").trim();

    for (const f of files) {
      const rel = f.webkitRelativePath || f.name;
      let parts = String(rel || "")
        .replace(/\\/g, "/")
        .split("/")
        .filter(Boolean);
      parts = stripPickerRootPrefix(parts, root);
      if (parts.length < 1) continue;

      const leaf = parts[parts.length - 1] || "";
      const isPdf = leaf.toLowerCase().endsWith(".pdf");
      if (!isPdf) continue;

      if (parts.length === 1) {
        const cat = "(root)";
        if (!categories.has(cat)) {
          categories.set(cat, {
            buckets: new Map(),
            parserAvailable: categoryFolderHasParser(cat),
          });
        }
        const bkey = "";
        const c = categories.get(cat);
        const prev = c.buckets.get(bkey) || {
          pdfCount: 0,
          parserAvailable: c.parserAvailable,
        };
        prev.pdfCount += 1;
        c.buckets.set(bkey, prev);
        continue;
      }

      const cat = parts[0];
      if (!categories.has(cat)) {
        categories.set(cat, {
          buckets: new Map(),
          parserAvailable: categoryFolderHasParser(cat),
        });
      }
      const c = categories.get(cat);

      if (parts.length === 2) {
        const bkey = "";
        const prev = c.buckets.get(bkey) || {
          pdfCount: 0,
          parserAvailable: c.parserAvailable,
        };
        prev.pdfCount += 1;
        c.buckets.set(bkey, prev);
      } else {
        const bkey = parts[1];
        const prev = c.buckets.get(bkey) || {
          pdfCount: 0,
          parserAvailable: c.parserAvailable,
        };
        prev.pdfCount += 1;
        c.buckets.set(bkey, prev);
      }
    }

    return categories;
  }

  /**
   * @param {string} pdfPath
   * @param {string} rootFolderName
   * @param {Map<string, Set<string>>} selection category -> set of bucket keys ("" allowed)
   */
  function pdfPathMatchesBucketSelection(pdfPath, rootFolderName, selection) {
    let parts = String(pdfPath || "")
      .replace(/\\/g, "/")
      .split("/")
      .filter(Boolean);
    parts = stripPickerRootPrefix(parts, rootFolderName);
    if (parts.length < 1) return false;
    const leaf = parts[parts.length - 1] || "";
    if (!leaf.toLowerCase().endsWith(".pdf")) return false;

    if (parts.length === 1) {
      const set = selection.get("(root)");
      return Boolean(set && set.has(""));
    }

    const cat = parts[0];
    const set = selection.get(cat);
    if (!set) return false;
    if (parts.length === 2) return set.has("");
    const bucket = parts[1];
    return set.has(bucket);
  }

  /**
   * Build `selection` for `POST /api/process-batch` from checked bucket boxes.
   * @returns {{ category: string, subfolders: string[] }[]}
   */
  function readSelectionForApi() {
    const map = readBucketCheckboxSelection();
    const names = sortCategoryNamesForDisplay(Array.from(map.keys()));
    const selection = [];
    for (const cat of names) {
      const set = map.get(cat);
      if (!set || set.size === 0) continue;
      const subfolders = Array.from(set).sort((a, b) => {
        if (a === "" && b !== "") return -1;
        if (b === "" && a !== "") return 1;
        return a.localeCompare(b, undefined, { sensitivity: "base" });
      });
      selection.push({ category: cat, subfolders });
    }
    return selection;
  }

  /**
   * @returns {Map<string, Set<string>>}
   */
  function readBucketCheckboxSelection() {
    const map = new Map();
    const boxes = bucketSelectionCategoriesEl.querySelectorAll(
      "input[type=checkbox][data-bucket-key]"
    );
    for (const el of boxes) {
      if (!(el instanceof HTMLInputElement)) continue;
      if (!el.checked) continue;
      const cat = el.getAttribute("data-category");
      if (cat == null) continue;
      const bucketKey = el.getAttribute("data-bucket-key") ?? "";
      if (!map.has(cat)) map.set(cat, new Set());
      map.get(cat).add(bucketKey);
    }
    return map;
  }

  function filterPdfPathsByBucketSelection(pdfPaths, rootFolderName, selection) {
    return pdfPaths.filter((p) =>
      pdfPathMatchesBucketSelection(p, rootFolderName, selection)
    );
  }

  function countParserAvailableInSelection(pdfPaths, rootFolderName, selection) {
    let n = 0;
    for (const p of pdfPaths) {
      if (!pdfPathMatchesBucketSelection(p, rootFolderName, selection)) continue;
      const cat = immediateSubfolderCategory(p, rootFolderName);
      if (categoryFolderHasParser(cat)) n += 1;
    }
    return n;
  }

  function bucketLabel(bucketKey) {
    if (bucketKey === "") return "PDFs directly in this folder";
    return bucketKey;
  }

  /**
   * Check or uncheck every bucket checkbox for one category (exact `data-category` match).
   * @param {string} category
   * @param {boolean} checked
   */
  function setAllBucketsInCategoryChecked(category, checked) {
    const boxes = bucketSelectionCategoriesEl.querySelectorAll(
      "input[type=checkbox][data-category][data-bucket-key]"
    );
    for (const el of boxes) {
      if (!(el instanceof HTMLInputElement)) continue;
      if (el.getAttribute("data-category") !== category) continue;
      el.checked = checked;
    }
    syncProcessButton();
  }

  /**
   * @param {Map<string, { buckets: Map<string, { pdfCount: number }>, parserAvailable: boolean }>} hierarchy
   */
  function renderBucketSelectionPanel(hierarchy) {
    bucketSelectionCategoriesEl.innerHTML = "";
    if (!hierarchy.size) {
      bucketSelectionPanelEl.hidden = true;
      return;
    }

    bucketSelectionPanelEl.hidden = false;
    const names = sortCategoryNamesForDisplay(Array.from(hierarchy.keys()));

    for (const cat of names) {
      const meta = hierarchy.get(cat);
      if (!meta) continue;
      const entries = Array.from(meta.buckets.entries()).sort((a, b) => {
        const ak = a[0] === "" ? "\u0000" : a[0];
        const bk = b[0] === "" ? "\u0000" : b[0];
        return ak.localeCompare(bk, undefined, { sensitivity: "base" });
      });

      const card = document.createElement("div");
      card.className =
        "rounded-xl border border-slate-200 bg-white p-4 shadow-sm";

      const head = document.createElement("div");
      head.className =
        "flex flex-wrap items-center justify-between gap-2 gap-y-1";

      const title = document.createElement("div");
      title.className = "font-semibold text-slate-900";
      title.textContent = cat === "(root)" ? "Root of selection (no category folder)" : cat;

      const badge = document.createElement("span");
      if (meta.parserAvailable) {
        badge.className =
          "text-xs font-semibold uppercase tracking-wide text-emerald-800 bg-emerald-100 px-2 py-0.5 rounded-md";
        badge.textContent = "Parser available";
      } else {
        badge.className =
          "text-xs font-semibold uppercase tracking-wide text-amber-900 bg-amber-100 px-2 py-0.5 rounded-md";
        badge.textContent = "No parser yet";
      }

      head.appendChild(title);
      head.appendChild(badge);
      card.appendChild(head);

      const toolbar = document.createElement("div");
      toolbar.className =
        "mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-slate-100 pt-2";
      toolbar.setAttribute("role", "group");
      toolbar.setAttribute(
        "aria-label",
        cat === "(root)"
          ? "Bulk selection for root-level PDFs"
          : `Bulk selection for category ${cat}`
      );

      const mkBulkBtn = (label, bulk, titleText) => {
        const b = document.createElement("button");
        b.type = "button";
        b.textContent = label;
        b.setAttribute("data-bucket-bulk", bulk);
        b.setAttribute("data-category", cat);
        b.title = titleText;
        b.className =
          "text-xs font-semibold text-indigo-600 hover:text-indigo-800 " +
          "underline-offset-2 hover:underline focus-visible:outline " +
          "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-400 " +
          "rounded px-0.5 py-0.5";
        return b;
      };

      toolbar.appendChild(
        mkBulkBtn(
          "Select all",
          "all-on",
          `Check every bucket under “${cat === "(root)" ? "root" : cat}”.`
        )
      );
      toolbar.appendChild(
        mkBulkBtn(
          "Deselect all",
          "all-off",
          `Uncheck every bucket under “${cat === "(root)" ? "root" : cat}”.`
        )
      );
      card.appendChild(toolbar);

      const ul = document.createElement("ul");
      ul.className = "mt-3 space-y-2 text-sm";

      for (const [bkey, bmeta] of entries) {
        const li = document.createElement("li");
        li.className = "list-none";

        const cb = document.createElement("input");
        cb.type = "checkbox";
        cb.className =
          "mt-0.5 shrink-0 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500";
        cb.checked = true;
        cb.setAttribute("data-category", cat);
        cb.setAttribute("data-bucket-key", bkey);

        const lab = document.createElement("label");
        lab.className =
          "flex items-start gap-2 text-slate-700 cursor-pointer select-none flex-1";
        lab.appendChild(cb);
        const span = document.createElement("span");
        span.className = "pt-0.5";
        span.textContent = `${bucketLabel(bkey)} — ${bmeta.pdfCount} PDF${bmeta.pdfCount === 1 ? "" : "s"}`;
        lab.appendChild(span);

        li.appendChild(lab);
        ul.appendChild(li);
      }

      card.appendChild(ul);
      bucketSelectionCategoriesEl.appendChild(card);
    }
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
    !bucketSelectionPanelEl ||
    !bucketSelectionCategoriesEl
  ) {
    return;
  }

  bucketSelectionCategoriesEl.addEventListener("change", () => {
    syncProcessButton();
  });

  bucketSelectionCategoriesEl.addEventListener("click", (ev) => {
    const t = ev.target;
    if (!(t instanceof Element)) return;
    const btn = t.closest("button[data-bucket-bulk]");
    if (!btn || !bucketSelectionCategoriesEl.contains(btn)) return;
    const bulk = btn.getAttribute("data-bucket-bulk");
    const category = btn.getAttribute("data-category");
    if (category == null || (bulk !== "all-on" && bulk !== "all-off")) return;
    ev.preventDefault();
    setAllBucketsInCategoryChecked(category, bulk === "all-on");
  });

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
    const root = lastBatch.folder;
    const sel = readBucketCheckboxSelection();
    const selectedPaths = filterPdfPathsByBucketSelection(
      lastBatch.pdfPaths || [],
      root,
      sel
    );
    const supported = countParserAvailableInSelection(
      lastBatch.pdfPaths || [],
      root,
      sel
    );
    if (selectedPaths.length < 1) {
      processBtn.disabled = true;
      processBtn.title =
        "Select at least one bucket that contains PDFs to process.";
      return;
    }
    if (supported < 1) {
      processBtn.disabled = true;
      processBtn.title =
        "None of the selected buckets use a parser that is implemented yet (e.g. include a DC bucket).";
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
    renderBucketSelectionPanel(new Map());
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
      (lastBatch.pdfCount ?? 0) < 1
    ) {
      return null;
    }
    const sel = readBucketCheckboxSelection();
    const selectedPaths = filterPdfPathsByBucketSelection(
      lastBatch.pdfPaths || [],
      lastBatch.folder,
      sel
    );
    const supported = countParserAvailableInSelection(
      lastBatch.pdfPaths || [],
      lastBatch.folder,
      sel
    );
    if (selectedPaths.length < 1 || supported < 1) {
      return null;
    }

    const selection = readSelectionForApi();
    if (selection.length < 1) {
      return null;
    }

    const body = {
      root_folder: lastBatch.folder,
      upload_job_id: lastBatch.uploadJobId,
      selection,
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
    const sel = readBucketCheckboxSelection();
    const selectedPaths = lastBatch
      ? filterPdfPathsByBucketSelection(
          lastBatch.pdfPaths || [],
          lastBatch.folder,
          sel
        )
      : [];
    const supported = lastBatch
      ? countParserAvailableInSelection(
          lastBatch.pdfPaths || [],
          lastBatch.folder,
          sel
        )
      : 0;
    if (
      !lastBatch?.folder ||
      (lastBatch.pdfCount ?? 0) < 1 ||
      selectedPaths.length < 1 ||
      supported < 1
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
      const pdfCount = pdfPaths.length;
      fileCountEl.textContent = String(pdfCount);
      const hierarchy = scanFolderBucketHierarchy(files, displayRoot);
      renderBucketSelectionPanel(hierarchy);
      if (pdfCount < 1) {
        renderBucketSelectionPanel(new Map());
      }
      renderPreviewFromPaths(pdfPaths.slice(0, 10), 10);
      const sel0 = readBucketCheckboxSelection();
      const supportedPdfCount = countParserAvailableInSelection(
        pdfPaths,
        displayRoot,
        sel0
      );
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
        setStatus(
          "Upload complete — adjust bucket checkboxes if needed, then click “Process folder”."
        );
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
      renderBucketSelectionPanel(new Map());
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
