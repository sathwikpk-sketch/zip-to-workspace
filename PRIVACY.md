# Privacy

## Local processing

- The extension observes Chrome download state to identify completed `.zip` downloads.
- The extension stores the auto-extract setting, latest ZIP path, latest result, processing state, and timestamp in `chrome.storage.local`.
- A bounded list of handled Chrome download IDs is kept in `chrome.storage.session` and cleared when the browser session ends.
- The companion reads a local configuration file containing the workspace directory.
- The companion extracts files locally and may open the file manager or an installed editor when requested.
- The companion writes diagnostic messages to a local log file. Log entries may include error messages and local paths.

## Remote data

The project source does not intentionally upload archive contents, filenames, workspace contents, or logs to a project-operated server. The extension uses local system fonts and does not load a remote font service. Chrome and installed editors may have independent telemetry and privacy practices.

## User controls

Auto-extraction is disabled by default. Users can enable it in the extension popup. Users can remove the extension from `chrome://extensions` and unregister the companion using the provided uninstall script.

## Data deletion

Extension state can be cleared by removing the extension or clearing its data in Chrome. The companion log and configuration are stored in its local application directory. The uninstaller removes companion configuration and log files but does not delete the user's workspace directory.

Update this policy if telemetry, remote services, analytics, or additional data collection are introduced.
