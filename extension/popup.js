const $ = (id) => document.getElementById(id);
let latestResult = null;

function setError(message) {
  const box = $("errorBox");
  box.textContent = message || "";
  box.classList.toggle("hidden", !message);
}

function showResult(result, processing = false) {
  latestResult = result || null;

  const kindBadge = $("kindTag") || $("kindBadge");
  const timeBadge = $("timeBadge");
  const pathContainer = $("pathContainer");
  const pathText = $("pathText");

  if (processing) {
    kindBadge.className = "badge";
    kindBadge.textContent = "WORKING";
    $("resultTitle").textContent = "Extracting ZIP Archive...";
    $("resultMessage").textContent = "Validating structure and unpacking files...";
    pathContainer.classList.add("hidden");
  } else if (result?.ok) {
    if (result.pending) {
      kindBadge.className = "badge";
      kindBadge.textContent = "DOWNLOADED";
      $("resultTitle").textContent = "ZIP Download Complete";
      $("resultMessage").textContent = result.message || "Ready for manual extraction.";
    } else {
      kindBadge.className = result.project_type ? "badge project" : "badge success";
      kindBadge.textContent = result.project_type ? result.project_type.toUpperCase() : "EXTRACTED";
      $("resultTitle").textContent = result.project_type ? `${result.project_type} Ready` : "Extraction Complete";
      $("resultMessage").textContent = result.message || "Files are extracted and ready.";
    }
    if (result.output_path || result.zip_path) {
      pathText.textContent = result.output_path || result.zip_path;
      pathContainer.classList.remove("hidden");
    } else {
      pathContainer.classList.add("hidden");
    }
  } else if (result?.ok === false) {
    kindBadge.className = "badge error";
    kindBadge.textContent = "ERROR";
    $("resultTitle").textContent = "Extraction Issue";
    $("resultMessage").textContent = result.error || "Failed to extract ZIP file.";
    if (result.zip_path) {
      pathText.textContent = result.zip_path;
      pathContainer.classList.remove("hidden");
    } else {
      pathContainer.classList.add("hidden");
    }
  } else {
    kindBadge.className = "badge";
    kindBadge.textContent = "READY";
    $("resultTitle").textContent = "No Recent Extraction";
    $("resultMessage").textContent = "Download a ZIP file in Chrome to auto-extract into your workspace.";
    pathContainer.classList.add("hidden");
  }

  $("extractBtn").classList.toggle("hidden", !(result?.pending || result?.ok === false));
  $("openFolderBtn").classList.toggle("hidden", !(result?.ok && result?.output_path && !result.pending));
  $("openCodeBtn").classList.toggle("hidden", !(result?.ok && result?.output_path && !result.pending));

  if (result?.project_type) {
    $("openCodeBtn").textContent = `Open in VS Code (${result.project_type})`;
  } else {
    $("openCodeBtn").textContent = "Open in VS Code / Cursor";
  }

  setError(result?.ok === false ? result.error : "");
}

async function refresh() {
  const data = await chrome.storage.local.get({ autoExtract: false, latestResult: null, processing: false, timestamp: null });
  $("autoExtract").checked = data.autoExtract;
  showResult(data.latestResult, data.processing);
  const timeBadge = $("timeBadge");
  timeBadge.textContent = data.timestamp ? new Date(data.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "";
}

$("autoExtract").addEventListener("change", async (e) => {
  await chrome.storage.local.set({ autoExtract: e.target.checked });
});

$("extractBtn").addEventListener("click", async () => {
  setError("");
  showResult(latestResult, true);
  chrome.runtime.sendMessage({ action: "extract-latest" }, (res) => {
    if (chrome.runtime.lastError) setError(chrome.runtime.lastError.message);
    else showResult(res);
  });
});

async function triggerNativeAction(action) {
  if (!latestResult?.output_path) return;
  setError("");
  chrome.runtime.sendMessage({
    action: "native-action",
    nativeAction: action,
    folderPath: latestResult.output_path
  }, (res) => {
    if (chrome.runtime.lastError) setError(chrome.runtime.lastError.message);
    else if (!res?.ok) setError(res?.error || "Unable to complete native action.");
  });
}

$("openFolderBtn").addEventListener("click", () => triggerNativeAction("open_folder"));
$("openCodeBtn").addEventListener("click", () => triggerNativeAction("open_vscode"));

$("copyPathBtn").addEventListener("click", () => {
  const path = $("pathText").textContent;
  if (path) {
    navigator.clipboard.writeText(path).then(() => {
      const btn = $("copyPathBtn");
      btn.style.color = "#22c55e";
      setTimeout(() => { btn.style.color = ""; }, 1200);
    }).catch(() => setError("Could not copy the path. Select and copy it manually."));
  }
});

$("refreshBtn").addEventListener("click", refresh);

chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "local") refresh();
});

refresh();
