import io
import json
import stat
import struct
import sys
import tempfile
import unittest
import zipfile
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "companion"))
import host  # noqa: E402


class ArchiveExtractionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.output = self.root / "workspace"
        self.output.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def make_zip(self, name, entries):
        archive_path = self.root / name
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for filename, content in entries:
                zf.writestr(filename, content)
        return archive_path

    def test_extracts_and_flattens_single_wrapper(self):
        archive = self.make_zip("project-main.zip", [
            ("project-main/", ""),
            ("project-main/package.json", '{"name":"sample"}'),
            ("project-main/src/index.js", "console.log('safe')"),
        ])
        result = host.extract_zip(str(archive), self.output)
        extracted = Path(result["output_path"])
        self.assertTrue(result["ok"])
        self.assertTrue((extracted / "package.json").is_file())
        self.assertFalse((extracted / "project-main").exists())
        self.assertEqual(result["project_type"], "Node.js project")

    def test_second_extraction_does_not_overwrite(self):
        archive = self.make_zip("sample.zip", [("readme.txt", "hello")])
        first = Path(host.extract_zip(str(archive), self.output)["output_path"])
        second = Path(host.extract_zip(str(archive), self.output)["output_path"])
        self.assertNotEqual(first, second)
        self.assertTrue(first.is_dir())
        self.assertTrue(second.is_dir())

    def test_rejects_parent_traversal(self):
        archive = self.make_zip("bad.zip", [("../escape.txt", "no")])
        with self.assertRaises(ValueError):
            host.extract_zip(str(archive), self.output)
        self.assertFalse((self.root / "escape.txt").exists())
        self.assertEqual(list(self.output.iterdir()), [])

    def test_rejects_absolute_path(self):
        archive = self.make_zip("bad.zip", [("/tmp/escape.txt", "no")])
        with self.assertRaises(ValueError):
            host.extract_zip(str(archive), self.output)

    def test_rejects_windows_reserved_filename(self):
        archive = self.make_zip("bad.zip", [("CON.txt", "no")])
        with self.assertRaises(ValueError):
            host.extract_zip(str(archive), self.output)

    def test_rejects_duplicate_paths(self):
        archive = self.make_zip("bad.zip", [("same.txt", "one"), ("same.txt", "two")])
        with self.assertRaises(ValueError):
            host.extract_zip(str(archive), self.output)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_rejects_corrupt_zip(self):
        archive = self.root / "broken.zip"
        archive.write_bytes(b"not a zip archive")
        with self.assertRaises(ValueError):
            host.extract_zip(str(archive), self.output)

    def test_rejects_non_zip(self):
        file_path = self.root / "file.txt"
        file_path.write_text("not zip")
        with self.assertRaises(ValueError):
            host.extract_zip(str(file_path), self.output)

    def test_detects_dotnet_solution(self):
        folder = self.root / "dotnet"
        folder.mkdir()
        (folder / "Sample.sln").write_text("solution")
        self.assertEqual(host.detect_project(folder), "C#/.NET project")


    def test_rejects_case_insensitive_path_collision(self):
        archive = self.make_zip("bad.zip", [("Folder/a.txt", "one"), ("folder/b.txt", "two")])
        with self.assertRaises(ValueError):
            host.extract_zip(str(archive), self.output)
        self.assertEqual(list(self.output.iterdir()), [])


    def test_rejects_unicode_normalization_collision(self):
        archive = self.make_zip("unicode.zip", [("caf\u00e9.txt", "one"), ("cafe\u0301.txt", "two")])
        with self.assertRaises(ValueError):
            host.extract_zip(str(archive), self.output)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_rejects_file_directory_prefix_conflict(self):
        archive = self.make_zip("bad.zip", [("project", "file"), ("project/main.py", "code")])
        with self.assertRaises(ValueError):
            host.extract_zip(str(archive), self.output)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_rejects_symlink_entry(self):
        archive_path = self.root / "symlink.zip"
        info = zipfile.ZipInfo("link")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        with zipfile.ZipFile(archive_path, "w") as zf:
            zf.writestr(info, "../../outside")
        with self.assertRaises(ValueError):
            host.extract_zip(str(archive_path), self.output)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_native_message_round_trip(self):
        payload = b'{"action":"test"}'
        stream = io.BytesIO(struct.pack("<I", len(payload)) + payload)
        with mock.patch.object(host.sys, "stdin", mock.Mock(buffer=stream)):
            self.assertEqual(host.read_message(), {"action": "test"})

    def test_rejects_oversized_native_message(self):
        stream = io.BytesIO(struct.pack("<I", host.MAX_MESSAGE_BYTES + 1))
        with mock.patch.object(host.sys, "stdin", mock.Mock(buffer=stream)):
            with self.assertRaises(ValueError):
                host.read_message()


    def test_rejects_too_many_entries(self):
        archive = self.make_zip("many.zip", [("one.txt", "1"), ("two.txt", "2")])
        with mock.patch.object(host, "MAX_ENTRIES", 1):
            with self.assertRaises(ValueError):
                host.extract_zip(str(archive), self.output)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_rejects_high_compression_ratio(self):
        archive = self.make_zip("ratio.zip", [("zeros.bin", "0" * 2_000_000)])
        with mock.patch.object(host, "MAX_COMPRESSION_RATIO", 2):
            with self.assertRaises(ValueError):
                host.extract_zip(str(archive), self.output)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_does_not_guess_between_multiple_projects(self):
        folder = self.root / "multi"
        (folder / "frontend").mkdir(parents=True)
        (folder / "backend").mkdir()
        (folder / "frontend" / "package.json").write_text("{}")
        (folder / "backend" / "requirements.txt").write_text("flask")
        self.assertIsNone(host.detect_project(folder))

    def test_prefers_django_over_generic_python_marker(self):
        folder = self.root / "django"
        folder.mkdir()
        (folder / "manage.py").write_text("# django")
        (folder / "requirements.txt").write_text("django")
        self.assertEqual(host.detect_project(folder), "Django project")


    def test_corrupt_payload_cleans_partial_output(self):
        archive = self.make_zip("payload.zip", [("data.bin", "A" * 20_000)])
        # Corrupt one byte in the stored/deflated member payload while leaving the directory intact.
        with zipfile.ZipFile(archive, "r") as zf:
            info = zf.getinfo("data.bin")
        raw = bytearray(archive.read_bytes())
        name_length = int.from_bytes(raw[info.header_offset + 26:info.header_offset + 28], "little")
        extra_length = int.from_bytes(raw[info.header_offset + 28:info.header_offset + 30], "little")
        payload_offset = info.header_offset + 30 + name_length + extra_length
        raw[payload_offset + 1] ^= 0xFF
        archive.write_bytes(raw)
        with self.assertRaises(ValueError):
            host.extract_zip(str(archive), self.output)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_rejects_reserved_filename_with_spaces_before_extension(self):
        archive = self.make_zip("bad.zip", [("CON .txt", "no")])
        with self.assertRaises(ValueError):
            host.extract_zip(str(archive), self.output)


    def test_main_terminates_after_invalid_frame(self):
        incoming = io.BytesIO(struct.pack("<I", host.MAX_MESSAGE_BYTES + 1))
        outgoing = io.BytesIO()
        fake_stdin = mock.Mock(buffer=incoming)
        fake_stdout = mock.Mock(buffer=outgoing)
        with mock.patch.object(host.sys, "stdin", fake_stdin), \
             mock.patch.object(host.sys, "stdout", fake_stdout), \
             mock.patch.object(host.sys, "platform", "linux"), \
             mock.patch.object(host, "log_debug"):
            host.main()
        raw = outgoing.getvalue()
        size = struct.unpack("<I", raw[:4])[0]
        response = json.loads(raw[4:4 + size])
        self.assertFalse(response["ok"])
        self.assertIn("1 MiB limit", response["error"])

    def test_open_folder_restricted_to_workspace(self):
        outside = self.root / "outside"
        outside.mkdir()
        with self.assertRaises(ValueError):
            host.validate_output_folder(str(outside), self.output)


if __name__ == "__main__":
    unittest.main()
