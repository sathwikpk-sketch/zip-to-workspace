# Testing and verification status

## Checks run during this revision

The following checks were run in a Linux development container with Python 3.13 and Node.js available:

- Python unit tests: **23 passed**.
- Python compilation: `python -m py_compile companion/host.py tests/test_host.py` passed.
- JavaScript syntax: `node --check extension/service-worker.js` and `node --check extension/popup.js` passed.
- Extension manifest JSON parsing passed.
- Bash syntax checks for `companion/setup.sh` and `companion/uninstall.sh` passed.
- Native-messaging subprocess smoke test passed: framed request, companion configuration, ZIP extraction, wrapper-folder flattening, response framing, and Node.js project detection.
- ZIP security regression tests cover traversal, absolute paths, symbolic links, reserved Windows filenames, duplicate/case-colliding paths, file/directory conflicts, entry-count limits, compression-ratio limits, corrupted payload cleanup, and malformed archives.

## Not yet verified end-to-end

These are still required before calling the project stable:

- Run the PowerShell setup and uninstall scripts on a real Windows machine.
- Register the native host in Chrome and test actual extension-to-host communication.
- Test the full UI flow in Chrome on a clean Windows profile.
- Verify opening folders and editors on systems with and without VS Code/Cursor/VSCodium.
- Test macOS and Linux installation scripts on their target systems; these platforms remain experimental.
- Confirm GitHub Actions and CodeQL complete successfully after the repository is pushed.

## Release guidance

Treat this as an experimental beta. A passing unit suite does not prove the installer, browser integration, or every archive edge case is safe. Use harmless test ZIPs first and inspect extracted code before running it.
