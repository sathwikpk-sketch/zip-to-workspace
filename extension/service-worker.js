const HOST = "com.aidownload.workspace";
const DEFAULT_SETTINGS = { autoExtract: false };
let downloadQueue = Promise.resolve();
const inFlightDownloads = new Set();
const extractionRequests = new Map();

async function getSettings() {
  return chrome.storage.local.get(DEFAULT_SETTINGS);
}

function setBadge(text, color = "#2563eb") {
  chrome.action.setBadgeText({ text });
  chrome.action.setBadgeBackgroundColor({ color });
}

function nativeMessage(message) {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendNativeMessage(HOST, message, (response) => {
      const error = chrome.runtime.lastError;
      if (error) reject(new Error(error.message));
      else if (!response || typeof response !== "object") reject(new Error("The native companion returned no valid response. Check companion setup."));
      else resolve(response);
    });
  });
}

async function storeResult(result, path = result?.zip_path) {
  await chrome.storage.local.set({
    latestResult: result,
    processing: false,
    ...(path ? { latestZipPath: path } : {}),
    timestamp: Date.now()
  });
  if (result?.pending) setBadge("ZIP", "#475569");
  else setBadge(result?.ok ? "OK" : "!", result?.ok ? "#16a34a" : "#dc2626");
}

async function extractPath(path) {
  if (typeof path !== "string" || !/\.zip$/i.test(path)) {
    throw new Error("The selected download is not a ZIP file.");
  }
  // Prevent double-clicks or duplicate completion events from extracting the same path twice.
  if (extractionRequests.has(path)) return extractionRequests.get(path);
  const request = (async () => {
    await chrome.storage.local.set({ latestZipPath: path, processing: true });
    setBadge("...", "#64748b");
    try {
      const result = await nativeMessage({ action: "extract", zip_path: path });
      await storeResult({ ...result, zip_path: result?.zip_path || path }, path);
      return result;
    } catch (error) {
      const result = { ok: false, error: error.message || "Extraction failed.", zip_path: path };
      await storeResult(result, path);
      return result;
    }
  })();
  extractionRequests.set(path, request);
  try {
    return await request;
  } finally {
    extractionRequests.delete(path);
  }
}

async function handleDownloadChange(delta) {
  if (delta.state?.current !== "complete" || !Number.isInteger(delta.id)) return;
  if (inFlightDownloads.has(delta.id)) return;
  inFlightDownloads.add(delta.id);
  try {
    const items = await chrome.downloads.search({ id: delta.id });
    const item = items?.[0];
    if (!item || !/\.zip$/i.test(item.filename || "")) return;

    // Session storage survives service-worker suspension but is cleared between browser sessions.
    // Download IDs may be reused after a browser restart, so do not persist them indefinitely.
    const state = await chrome.storage.session.get({ handledDownloadIds: [] });
    const handled = Array.isArray(state.handledDownloadIds) ? state.handledDownloadIds : [];
    if (handled.includes(delta.id)) return;
    const nextHandled = [...handled, delta.id].slice(-200);
    await chrome.storage.session.set({ handledDownloadIds: nextHandled });
    await chrome.storage.local.set({ latestZipPath: item.filename });

    const { autoExtract } = await getSettings();
    if (autoExtract) {
      await extractPath(item.filename);
    } else {
      await storeResult({
        ok: true,
        pending: true,
        zip_path: item.filename,
        message: "ZIP download complete. Choose Extract when you are ready."
      }, item.filename);
    }
  } catch (error) {
    await storeResult({ ok: false, error: error.message || "Could not process the completed download." });
  } finally {
    inFlightDownloads.delete(delta.id);
  }
}

chrome.downloads.onChanged.addListener((delta) => {
  // Serialize events so a repeated completion event cannot start two extractions.
  downloadQueue = downloadQueue.then(() => handleDownloadChange(delta)).catch(async (error) => {
    await storeResult({ ok: false, error: error.message || "Download processing failed." });
  });
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  (async () => {
    try {
      if (message?.action === "extract-latest") {
        const data = await chrome.storage.local.get(["latestZipPath"]);
        if (!data.latestZipPath) throw new Error("No completed ZIP download is available. Download a ZIP first.");
        sendResponse(await extractPath(data.latestZipPath));
        return;
      }
      if (message?.action === "native-action") {
        if (!["open_folder", "open_vscode"].includes(message.nativeAction)) {
          throw new Error("Unsupported workspace action.");
        }
        if (typeof message.folderPath !== "string" || !message.folderPath) {
          throw new Error("No extracted workspace folder was provided.");
        }
        sendResponse(await nativeMessage({ action: message.nativeAction, folder_path: message.folderPath }));
        return;
      }
      sendResponse({ ok: false, error: "Unknown extension action." });
    } catch (error) {
      sendResponse({ ok: false, error: error.message || "The requested action failed." });
    }
  })();
  return true;
});
