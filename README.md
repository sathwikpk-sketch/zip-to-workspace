# ZIP-to-Workspace

**Turn downloaded ZIP files into organized development workspaces.**

ZIP-to-Workspace is an open-source Chrome extension plus a local companion application. It is designed to reduce repetitive steps when developers download project archives from AI coding tools, GitHub, or other sources.

> **Status: Early beta / experimental.** This software has not yet been verified on every supported Windows, macOS, or Linux configuration. Use test projects first and report bugs. Do not treat extraction as a security scan: inspect downloaded code before running it.

## What it does

- Detects completed `.zip` downloads in Chrome.
- Lets you disable or enable automatic extraction.
- Extracts into a configured local workspace.
- Attempts to identify common project types.
- Offers actions to open an extracted folder or open it in a supported code editor.
- Processes archives locally; no project upload service is included.

## How it works

1. The Chrome Manifest V3 extension observes completed downloads.
2. The extension sends a small request to a registered Chrome Native Messaging host.
3. The local Python companion validates and extracts the archive.
4. The extension shows the result and provides optional open-folder/editor actions.

The companion extracts files as data. It does **not** run project scripts, install dependencies, or execute extracted code.

## Current scope

- **Primary target:** Google Chrome on Windows.
- **Companion runtime:** Python 3.10 or newer.
- **Editor:** VS Code, Cursor, or VSCodium may be opened when a supported executable can be located.
- **Other platforms:** setup scripts are included for macOS and Linux, but those combinations should be considered experimental until independently tested.

## Requirements

- Google Chrome 102 or newer.
- Python 3.10 or newer.
- A writable workspace directory.
- Optional: VS Code, Cursor, or VSCodium.

## Development installation

### 1. Download the repository

Clone this repository or download the source ZIP and extract it to a permanent directory. Do not move the directory after registering the companion unless you rerun setup.

### 2. Load the extension

1. Open `chrome://extensions`.
2. Enable **Developer mode**.
3. Select **Load unpacked**.
4. Choose this repository's `extension/` directory.
5. Copy the extension ID displayed by Chrome.

### 3. Register the companion

**Windows (primary target):**

Open PowerShell in `companion/` and run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\setup.ps1
```

Enter the extension ID and workspace directory when prompted. The script copies `host.py` to a stable per-user application directory and registers the native host for the current Windows user. Keep the extension folder at a permanent path; if you move it or reload it with a different ID, rerun setup with the current extension ID. Restart Chrome afterwards. To unregister the companion later, run `companion\uninstall.ps1` from PowerShell from the repository root. It does not delete your workspace.

**macOS / Linux (experimental):**

```bash
cd companion
chmod +x setup.sh
./setup.sh
```

Enter the extension ID and workspace directory. Restart Chrome afterwards. On Linux, the included script targets Google Chrome's standard per-user configuration path; Chromium-based distributions may use a different path. To unregister the companion later, run `./uninstall.sh` from `companion/`. It does not delete your workspace.

### 4. Test safely

Start with a ZIP containing a few harmless text files or a toy project. Keep **Auto-extract ZIPs disabled** until you have verified the workspace destination and behavior. Enable it in the extension popup only if you want it.

## Security notes

ZIP archives are untrusted input. This project includes checks for unsafe paths, symbolic links and special filesystem entries, excessive entry counts, oversized files, suspicious compression ratios, duplicate/conflicting paths, and Windows-reserved filenames. These checks reduce risk but do not guarantee that every malicious archive or local attack is prevented.

- Review code before running it.
- Do not install dependencies or execute scripts from an archive solely because extraction succeeded.
- Use a workspace directory that you control.
- Do not use this beta as the only protection for sensitive or production systems.
- Report security issues privately using `SECURITY.md`.

## Privacy

Archive extraction and project detection run locally in the companion. The extension uses Chrome storage for settings and the latest result. The companion writes a local diagnostic log under its application configuration directory. The project does not intentionally upload ZIP contents or project files to a remote service. See `PRIVACY.md` for details.

## Testing

Run the Python unit tests from the repository root:

```bash
python -m unittest discover -s tests -v
```

Check the JavaScript syntax (Node.js required):

```bash
node --check extension/service-worker.js
node --check extension/popup.js
```

The tests do not replace end-to-end testing in Chrome on a clean Windows machine. Native messaging, Windows registry setup, editor launch, and installer/uninstaller behavior must be verified on the target OS before a stable release.

## Known limitations

- The project is an early beta, not a production-certified security product.
- The extension does not scan extracted files for malware.
- Project type detection is heuristic and may not recognize every repository layout.
- ZIP files containing unsafe or non-portable paths may be rejected.
- Opening an editor depends on the editor being installed and discoverable.
- There is no automatic dependency installation, code execution, cloud sync, or remote upload.
- Native host registration must match the extension ID shown by Chrome.

## Contributing

Please read `CONTRIBUTING.md` before opening a pull request. Bug reports should include reproduction steps, operating system, Python version, Chrome version, and relevant error messages. Do not attach private project archives or secrets to public issues.

## License

Released under the MIT License. See `LICENSE`.
