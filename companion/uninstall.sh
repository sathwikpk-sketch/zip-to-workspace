#!/usr/bin/env bash
set -euo pipefail
: "${HOME:?HOME must be set to uninstall the companion for the current user}"
if [[ "$(uname -s)" == "Darwin" ]]; then
  app_dir="$HOME/Library/Application Support/AI-Download-to-Workspace"
  manifest="$HOME/Library/Application Support/Google/Chrome/NativeMessagingHosts/com.aidownload.workspace.json"
else
  app_dir="$HOME/.config/ai-download-to-workspace"
  manifest="$HOME/.config/google-chrome/NativeMessagingHosts/com.aidownload.workspace.json"
fi
rm -f "$manifest"
rm -rf "$app_dir"
printf 'Companion removed. Your workspace folder was not deleted. Remove the extension from chrome://extensions separately.\n'
