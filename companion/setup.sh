#!/usr/bin/env bash
set -euo pipefail
: "${HOME:?HOME must be set to install the companion for the current user}"

printf '\nZIP-to-Workspace companion setup\n\n'
read -r -p 'Chrome Extension ID from chrome://extensions: ' extension_id
extension_id="$(printf '%s' "$extension_id" | tr -d '[:space:]')"
if [[ ! "$extension_id" =~ ^[a-p]{32}$ ]]; then
  echo 'Invalid extension ID. Expected 32 lowercase letters from a through p.' >&2
  exit 1
fi

if [[ "$(uname -s)" == "Darwin" ]]; then
  default_workspace="$HOME/AI-Workspace"
  app_dir="$HOME/Library/Application Support/AI-Download-to-Workspace"
  manifest_dir="$HOME/Library/Application Support/Google/Chrome/NativeMessagingHosts"
else
  default_workspace="$HOME/AI-Workspace"
  app_dir="$HOME/.config/ai-download-to-workspace"
  manifest_dir="$HOME/.config/google-chrome/NativeMessagingHosts"
fi
read -r -p "Workspace directory [$default_workspace]: " workspace
workspace="${workspace:-$default_workspace}"
if [[ "$workspace" == "~" ]]; then
  workspace="$HOME"
elif [[ "$workspace" == "~"/* ]]; then
  workspace="$HOME/${workspace#\~/}"
fi
mkdir -p "$workspace" "$app_dir" "$manifest_dir"
workspace="$(cd "$workspace" && pwd -P)"

python_bin="$(command -v python3 || true)"
if [[ -z "$python_bin" ]]; then
  echo 'Python 3 was not found. Install Python 3.10 or newer and retry.' >&2
  exit 1
fi
if ! "$python_bin" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
  echo 'Python 3.10 or newer is required. Install a supported Python version and retry.' >&2
  exit 1
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
source_host="$script_dir/host.py"
if [[ ! -f "$source_host" ]]; then echo 'host.py was not found beside setup.sh.' >&2; exit 1; fi
installed_host="$app_dir/host.py"
cp "$source_host" "$installed_host"
chmod 700 "$installed_host"

"$python_bin" - "$app_dir/config.json" "$manifest_dir/com.aidownload.workspace.json" "$workspace" "$python_bin" "$installed_host" "$extension_id" <<'PY'
import json, os, sys
config_path, manifest_path, workspace, python_bin, host_path, extension_id = sys.argv[1:]
with open(config_path, "w", encoding="utf-8") as f:
    json.dump({"extract_dir": workspace}, f, indent=2)
with open(manifest_path, "w", encoding="utf-8") as f:
    json.dump({
        "name": "com.aidownload.workspace",
        "description": "ZIP-to-Workspace local companion",
        "path": os.path.abspath(python_bin),
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{extension_id}/"],
        "arguments": [os.path.abspath(host_path)],
    }, f, indent=2)
PY
chmod 600 "$app_dir/config.json" "$manifest_dir/com.aidownload.workspace.json"
printf '\nSetup completed.\nWorkspace: %s\nHost: %s\nManifest: %s\nRestart Chrome before testing.\n' "$workspace" "$installed_host" "$manifest_dir/com.aidownload.workspace.json"
