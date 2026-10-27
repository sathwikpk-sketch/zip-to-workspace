#!/usr/bin/env python3
"""Chrome Native Messaging host for ZIP-to-Workspace.

The host extracts archives as data only. It never executes project files.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import stat
import struct
import subprocess
import sys
import zipfile
import zlib
import unicodedata
from pathlib import Path
from typing import Any

if sys.platform == "win32":
    import msvcrt

APP_NAME = "AI-Download-to-Workspace"
if sys.platform == "win32":
    _base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData/Local"))
    APP_DIR = _base / APP_NAME
elif sys.platform == "darwin":
    APP_DIR = Path.home() / "Library" / "Application Support" / APP_NAME
else:
    APP_DIR = Path.home() / ".config" / "ai-download-to-workspace"
CONFIG_PATH = APP_DIR / "config.json"
LOG_PATH = APP_DIR / "companion.log"

MAX_MESSAGE_BYTES = 1 * 1024 * 1024
MAX_ENTRIES = 20_000
MAX_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024  # 2 GiB total
MAX_SINGLE_FILE_BYTES = 512 * 1024 * 1024          # 512 MiB per file
MAX_COMPRESSION_RATIO = 1_000

PROJECT_MARKERS = [
    ("Next.js project", ("next.config.js", "next.config.mjs", "next.config.ts")),
    ("React project", ("src/app.tsx", "src/app.jsx", "vite.config.ts", "vite.config.js")),
    ("Django project", ("manage.py",)),
    ("Node.js project", ("package.json",)),
    ("Python project", ("pyproject.toml", "requirements.txt", "setup.py", "pipfile", "pipfile.lock")),
    ("Rust project", ("cargo.toml",)),
    ("Go project", ("go.mod",)),
    ("Flutter project", ("pubspec.yaml",)),
    ("C#/.NET project", (".sln", ".csproj")),
    ("Java/Kotlin project", ("pom.xml", "build.gradle", "build.gradle.kts")),
    ("Docker project", ("docker-compose.yml", "compose.yml", "dockerfile")),
    ("Web project", ("index.html",)),
]

_WINDOWS_INVALID = set('<>:"|?*')
_WINDOWS_RESERVED = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])$", re.IGNORECASE)


def _is_windows_reserved(part: str) -> bool:
    # Windows treats device names as reserved even when followed by an extension.
    normalized = part.rstrip(" .")
    base = normalized.split(".", 1)[0].rstrip(" ")
    return bool(_WINDOWS_RESERVED.fullmatch(base))


def log_debug(message: str) -> None:
    # Keep untrusted paths/errors on one log line to avoid forged log entries.
    message = str(message).replace("\r", " ").replace("\n", " ")
    try:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as stream:
            stream.write(f"[{os.getpid()}] {message}\n")
    except OSError:
        pass


def read_message() -> dict[str, Any] | None:
    header = sys.stdin.buffer.read(4)
    if not header:
        return None
    if len(header) != 4:
        raise ValueError("Invalid native-messaging message header.")
    length = struct.unpack("<I", header)[0]
    if length > MAX_MESSAGE_BYTES:
        raise ValueError("Incoming message exceeds the 1 MiB limit.")
    payload = sys.stdin.buffer.read(length)
    if len(payload) != length:
        raise ValueError("Incomplete native-messaging payload.")
    message = json.loads(payload.decode("utf-8"))
    if not isinstance(message, dict):
        raise ValueError("Native-messaging message must be a JSON object.")
    return message


def write_message(message: dict[str, Any]) -> None:
    # ASCII escaping also handles unusual filesystem paths containing surrogate escapes.
    payload = json.dumps(message, ensure_ascii=True).encode("utf-8")
    if len(payload) > MAX_MESSAGE_BYTES:
        payload = json.dumps({"ok": False, "error": "Response exceeded message size limit."}).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("<I", len(payload)))
    sys.stdout.buffer.write(payload)
    sys.stdout.buffer.flush()


def load_config() -> Path:
    if not CONFIG_PATH.is_file():
        raise RuntimeError("Companion is not configured. Run the setup script again.")
    with CONFIG_PATH.open("r", encoding="utf-8-sig") as stream:
        config = json.load(stream)
    if not isinstance(config, dict) or not isinstance(config.get("extract_dir"), str) or not config["extract_dir"].strip():
        raise RuntimeError("The configured workspace directory is missing or invalid.")
    root = Path(config["extract_dir"]).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    if not root.is_dir():
        raise RuntimeError("The configured workspace path is not a directory.")
    return root


def _validate_member_parts(member_name: str) -> list[str]:
    if not isinstance(member_name, str) or not member_name or "\x00" in member_name:
        raise ValueError("Archive contains an empty or invalid entry name.")
    name = member_name.replace("\\", "/")
    if name.startswith("/") or re.match(r"^[A-Za-z]:", name) or name.startswith("//"):
        raise ValueError(f"Archive contains an absolute path: {member_name!r}")
    parts = [part for part in name.split("/") if part not in ("", ".")]
    if not parts or any(part == ".." for part in parts):
        raise ValueError(f"Archive contains an unsafe path: {member_name!r}")
    for part in parts:
        if any(ord(char) < 32 for char in part):
            raise ValueError(f"Archive path contains a control character: {member_name!r}")
        if any(char in _WINDOWS_INVALID for char in part) or part.endswith((".", " ")):
            raise ValueError(f"Archive path is not portable to Windows: {member_name!r}")
        if _is_windows_reserved(part):
            raise ValueError(f"Archive uses a reserved Windows filename: {member_name!r}")
    return parts


def safe_member_path(root: Path, member_name: str) -> Path:
    parts = _validate_member_parts(member_name)
    resolved_root = root.resolve()
    target = root.joinpath(*parts).resolve()
    try:
        target.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"Archive entry escapes the destination folder: {member_name!r}") from exc
    return target


def unique_destination(root: Path, stem: str) -> Path:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", stem).strip(" .")
    if not cleaned or _is_windows_reserved(cleaned):
        cleaned = "extracted-workspace"
    # Keep the directory name portable and leave room for duplicate suffixes.
    cleaned = cleaned[:100].rstrip(" .") or "extracted-workspace"
    candidate = root / cleaned
    index = 2
    while candidate.exists():
        candidate = root / f"{cleaned} ({index})"
        index += 1
    return candidate


def detect_project(folder: Path) -> str | None:
    ignored_dirs = {".git", "node_modules", "__pycache__", ".next", "dist", "build", "vendor"}

    def detect_direct(candidate: Path) -> str | None:
        names: set[str] = set()
        try:
            for path in candidate.iterdir():
                names.add(path.name.lower())
                if path.is_dir() and path.name.lower() not in ignored_dirs:
                    try:
                        for child in path.iterdir():
                            names.add(f"{path.name.lower()}/{child.name.lower()}")
                    except OSError:
                        continue
        except OSError:
            return None
        for project_type, markers in PROJECT_MARKERS:
            for marker in markers:
                marker_lower = marker.lower()
                if marker_lower in names or (marker_lower.startswith(".") and any(name.endswith(marker_lower) for name in names)):
                    return project_type
        return None

    direct = detect_direct(folder)
    if direct:
        return direct

    # If the archive contains several sibling projects, avoid guessing which one is primary.
    try:
        children = [p for p in folder.iterdir() if p.is_dir() and p.name.lower() not in ignored_dirs]
    except OSError:
        return None
    matches = [(child, detect_direct(child)) for child in children]
    matches = [(child, kind) for child, kind in matches if kind]
    if len(matches) == 1:
        return matches[0][1]
    return None


def _check_archive(archive: zipfile.ZipFile) -> tuple[list[zipfile.ZipInfo], list[tuple[zipfile.ZipInfo, list[str]]], str | None]:
    infos = archive.infolist()
    if len(infos) > MAX_ENTRIES:
        raise ValueError(f"Archive contains too many entries (limit: {MAX_ENTRIES}).")
    total = 0
    normalized: list[tuple[zipfile.ZipInfo, list[str]]] = []
    for info in infos:
        parts = _validate_member_parts(info.filename.rstrip("/\\") if info.is_dir() else info.filename)
        if info.flag_bits & 0x1:
            raise ValueError("Encrypted ZIP entries are not supported.")
        if info.file_size < 0 or info.file_size > MAX_SINGLE_FILE_BYTES:
            raise ValueError(f"Archive entry exceeds the per-file size limit: {info.filename!r}")
        total += info.file_size
        if total > MAX_UNCOMPRESSED_BYTES:
            raise ValueError("Archive expands beyond the 2 GiB safety limit.")
        if info.file_size > 1_000_000:
            if info.compress_size == 0 or info.file_size / max(info.compress_size, 1) > MAX_COMPRESSION_RATIO:
                raise ValueError(f"Archive entry has a suspicious compression ratio: {info.filename!r}")
        unix_mode = (info.external_attr >> 16) & 0xFFFF
        kind = stat.S_IFMT(unix_mode)
        if kind == stat.S_IFLNK:
            raise ValueError(f"Symbolic links are not supported: {info.filename!r}")
        if kind not in (0, stat.S_IFREG, stat.S_IFDIR):
            raise ValueError(f"Special filesystem entries are not supported: {info.filename!r}")
        if info.is_dir() and info.file_size:
            raise ValueError(f"Directory entry unexpectedly contains data: {info.filename!r}")
        normalized.append((info, parts))

    top_levels = {parts[0] for _, parts in normalized if parts}
    strip_prefix = None
    if len(top_levels) == 1:
        candidate = next(iter(top_levels))
        if all(info.is_dir() or len(parts) >= 2 for info, parts in normalized):
            strip_prefix = candidate

    # Detect duplicate and file/directory-prefix collisions before writing anything.
    # Case-folding is conservative and avoids collisions on Windows and common macOS filesystems.
    seen_explicit: dict[str, bool] = {}
    display_paths: dict[str, str] = {}
    for info, original_parts in normalized:
        parts = list(original_parts)
        if strip_prefix and parts and parts[0] == strip_prefix:
            parts = parts[1:]
        if not parts:  # The wrapper directory itself is removed.
            continue
        key_parts = [unicodedata.normalize("NFC", part).casefold() for part in parts]
        is_directory = info.is_dir() or info.filename.endswith(("/", "\\"))
        for index in range(1, len(key_parts) + 1):
            prefix_key = "/".join(key_parts[:index])
            prefix_display = "/".join(parts[:index])
            previous_display = display_paths.get(prefix_key)
            if previous_display is not None and previous_display != prefix_display:
                raise ValueError(f"Archive contains case-colliding paths: {previous_display!r} and {prefix_display!r}")
            display_paths[prefix_key] = prefix_display
            if index < len(key_parts) and seen_explicit.get(prefix_key) is False:
                raise ValueError(f"Archive path conflicts with a file: {prefix_display!r}")
        key = "/".join(key_parts)
        if key in seen_explicit:
            raise ValueError(f"Archive contains duplicate or conflicting paths: {'/'.join(parts)!r}")
        # A file may not replace a directory that already has descendants.
        if not is_directory and any(existing.startswith(key + "/") for existing in seen_explicit):
            raise ValueError(f"Archive file conflicts with an existing directory: {'/'.join(parts)!r}")
        seen_explicit[key] = is_directory

    return infos, normalized, strip_prefix


def extract_zip(zip_path: str, output_root: Path) -> dict[str, Any]:
    if not isinstance(zip_path, str) or not zip_path.strip():
        raise ValueError("No ZIP file path was supplied.")
    source = Path(zip_path).expanduser().resolve()
    if source.suffix.lower() != ".zip":
        raise ValueError("Only .zip archives are supported.")
    if not source.is_file():
        raise FileNotFoundError(f"ZIP file not found: {source}")
    output_root = output_root.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(source, "r") as archive:
            _, normalized, strip_prefix = _check_archive(archive)
            destination = unique_destination(output_root, source.stem)
            destination.mkdir(parents=False, exist_ok=False)
            try:
                actual_total = 0
                for info, original_parts in normalized:
                    parts = list(original_parts)
                    if strip_prefix and parts and parts[0] == strip_prefix:
                        parts = parts[1:]
                    if not parts:
                        continue
                    relative_name = "/".join(parts)
                    target = safe_member_path(destination, relative_name)

                    if info.is_dir() or info.filename.endswith(("/", "\\")):
                        target.mkdir(parents=True, exist_ok=True)
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    actual_file = 0
                    with archive.open(info, "r") as src, target.open("xb") as dst:
                        while True:
                            chunk = src.read(1024 * 1024)
                            if not chunk:
                                break
                            actual_file += len(chunk)
                            actual_total += len(chunk)
                            if actual_file > MAX_SINGLE_FILE_BYTES:
                                raise ValueError(f"Extracted file exceeded the per-file size limit: {relative_name!r}")
                            if actual_total > MAX_UNCOMPRESSED_BYTES:
                                raise ValueError("Archive expanded beyond the total extraction size limit.")
                            dst.write(chunk)
                    if actual_file != info.file_size:
                        raise ValueError(f"Archive entry size did not match its directory metadata: {relative_name!r}")
            except Exception:
                shutil.rmtree(destination, ignore_errors=True)
                raise
    except (zipfile.BadZipFile, zlib.error, EOFError, struct.error) as exc:
        raise ValueError("The downloaded file is not a valid ZIP archive or is corrupted.") from exc
    except OSError as exc:
        raise RuntimeError(f"Could not read or extract the archive: {exc}") from exc

    project_type = detect_project(destination)
    return {
        "ok": True,
        "zip_path": str(source),
        "output_path": str(destination),
        "project_type": project_type,
        "message": f"Successfully extracted into {destination.name}.",
    }


def validate_output_folder(folder_path: str, output_root: Path) -> Path:
    if not isinstance(folder_path, str) or not folder_path.strip():
        raise ValueError("No workspace folder was supplied.")
    folder = Path(folder_path).expanduser().resolve()
    try:
        folder.relative_to(output_root.resolve())
    except ValueError as exc:
        raise ValueError("Access is restricted to folders inside the configured workspace.") from exc
    if not folder.is_dir():
        raise FileNotFoundError("The requested workspace folder does not exist.")
    return folder


def _open_file_manager(folder: Path) -> None:
    if sys.platform == "win32":
        os.startfile(str(folder))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(folder)], close_fds=True)
    else:
        subprocess.Popen(["xdg-open", str(folder)], close_fds=True)


def _find_editor() -> str | None:
    candidates: list[Path] = []
    if sys.platform == "win32":
        local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
        program_files = Path(os.environ.get("ProgramFiles", "C:/Program Files"))
        candidates.extend([
            local / "Programs/Microsoft VS Code/Code.exe",
            program_files / "Microsoft VS Code/Code.exe",
            local / "Programs/Cursor/Cursor.exe",
            program_files / "Cursor/Cursor.exe",
        ])
        for name in ("Code.exe", "Cursor.exe", "VSCodium.exe"):
            found = shutil.which(name)
            if found:
                candidates.append(Path(found))
    else:
        for name in ("code", "cursor", "codium"):
            found = shutil.which(name)
            if found:
                candidates.append(Path(found))
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


def handle_action(message: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(message, dict):
        raise ValueError("Request must be a JSON object.")
    action = message.get("action")
    if not isinstance(action, str):
        raise ValueError("Request action is missing or invalid.")
    output_root = load_config()

    if action == "extract":
        return extract_zip(message.get("zip_path", ""), output_root)
    if action in ("open_folder", "open_vscode"):
        folder = validate_output_folder(message.get("folder_path", ""), output_root)
        if action == "open_folder":
            _open_file_manager(folder)
            return {"ok": True, "message": "Opened folder in the system file manager."}
        editor = _find_editor()
        if not editor:
            return {"ok": False, "error": "VS Code, Cursor, or VSCodium was not found. Install an editor or add its executable to PATH."}
        subprocess.Popen([editor, str(folder)], close_fds=True)
        return {"ok": True, "message": f"Opened workspace with {Path(editor).stem}."}
    return {"ok": False, "error": "Unknown companion action."}


def main() -> None:
    if sys.platform == "win32":
        # Chrome native messaging uses a binary length-prefixed stdio protocol.
        msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
        msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
    while True:
        try:
            message = read_message()
        except Exception as exc:
            # A broken frame cannot be safely resynchronized; report once and terminate.
            log_debug(f"Invalid native message: {type(exc).__name__}: {exc}")
            try:
                write_message({"ok": False, "error": str(exc) or "Invalid native-messaging request."})
            except Exception as write_exc:
                log_debug(f"Could not write native response: {type(write_exc).__name__}: {write_exc}")
            break
        if message is None:
            break
        try:
            result = handle_action(message)
        except Exception as exc:  # Send errors to the extension, never to protocol stdout.
            log_debug(f"Request failed: {type(exc).__name__}: {exc}")
            result = {"ok": False, "error": str(exc) or "The companion could not complete the request."}
        try:
            write_message(result)
        except Exception as exc:
            log_debug(f"Could not write native response: {type(exc).__name__}: {exc}")
            break


if __name__ == "__main__":
    main()
