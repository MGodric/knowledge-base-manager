#!/usr/bin/env python3
"""Vendor dependency distribution, reproducibility, and safety test suite.

Standard library only. Validates V01–V11 requirements:
- V01: Pinned versions, upstream provenance, licenses, no forbidden binaries.
- V02: Integrity check, drift detection, static package version check, read-only verification.
- V03: Offline deterministic rebuild from cached artifacts, byte identity, zero CRLF.
- V04: Archive extraction safety (traversal, symlinks, device nodes, size limits, case collisions, cleanup).
- V05: Standalone Skill copy in Chinese and spaced path with -I -S -B.
- V06: Negative control (all 4 packages unimportable in -I -S) and positive source introspection.
- V07: Full CLI command cycle with external sources and source file SHA-256 preservation.
- V08: Regression asserting 6 existing core suites pass under isolated vendor mode.
- V09: External package conflicts (unloaded precedence, preloaded module/submodule, stub, no output dirs).
- V10: Structural manifest corruption, diagnostic envelope codes, help/resolve independence.
- V11: Idempotence, no bytecode generation, no output directories on dependency failure.
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile

# Invariant: Never create bytecode
sys.dont_write_bytecode = True

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

SKILL_DIR = PROJECT_ROOT / "knowledge-base-manager"
SCRIPTS_DIR = SKILL_DIR / "scripts"
VENDOR_TOOL = PROJECT_ROOT / "tools" / "vendor_dependencies.py"
TESTS_DIR = PROJECT_ROOT / "tests"
VENDOR_CACHE = Path(os.environ.get("KBM_VENDOR_CACHE_DIR") or (PROJECT_ROOT / ".local" / "vendor_cache"))


def _run_tool(args: list[str], cwd: Path = PROJECT_ROOT) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, "-B", "-X", "utf8", str(VENDOR_TOOL), *args]
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8")


def _run_isolated_cli(skill_root: Path, args: list[str], cwd: Path) -> tuple[int, dict, str]:
    cli_path = skill_root / "scripts" / "kb.py"
    cmd = [sys.executable, "-I", "-S", "-B", "-X", "utf8", str(cli_path), "--format", "json", *args]
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, encoding="utf-8")
    try:
        data = json.loads(res.stdout) if res.stdout.strip() else {}
    except Exception:
        data = {}
    return res.returncode, data, res.stderr


class TestV01SourceAndLicenses(unittest.TestCase):
    """V01: Pinned versions, licenses, and absence of compiled binaries."""

    def test_v01_manifest_contains_exact_versions_and_sha256(self) -> None:
        man_file = SKILL_DIR / "vendor" / "manifest.json"
        self.assertTrue(man_file.is_file())
        man = json.loads(man_file.read_bytes().decode("utf-8"))
        self.assertEqual(man.get("schema_version"), 1)

        expected_pkgs = {
            "pyyaml": "6.0.3",
            "markdown-it-py": "4.2.0",
            "mdit-py-plugins": "0.6.1",
            "mdurl": "0.1.2",
        }
        actual_pkgs = {p["canonical_name"]: p["version"] for p in man.get("packages", [])}
        self.assertEqual(actual_pkgs, expected_pkgs)

        for p in man.get("packages", []):
            self.assertTrue(p.get("artifact_filename"))
            self.assertTrue(p.get("artifact_sha256"))
            self.assertEqual(len(p["artifact_sha256"]), 64)
            self.assertTrue(p.get("license_files"))

    def test_v01_license_files_preserved_on_disk(self) -> None:
        lic_dir = SKILL_DIR / "vendor" / "licenses"
        self.assertTrue(lic_dir.is_dir())
        for expected in [
            "pyyaml/LICENSE",
            "markdown-it-py/LICENSE",
            "mdit-py-plugins/LICENSE",
            "mdurl/LICENSE",
        ]:
            self.assertTrue((lic_dir / expected).is_file(), f"Missing license file: {expected}")

        tp = SKILL_DIR / "vendor" / "THIRD_PARTY.md"
        self.assertTrue(tp.is_file())
        tp_text = tp.read_bytes().decode("utf-8")
        self.assertIn("PyYAML", tp_text)
        self.assertIn("markdown-it-py", tp_text)
        self.assertIn("mdit-py-plugins", tp_text)
        self.assertIn("mdurl", tp_text)

    def test_v01_no_forbidden_binaries_in_vendor(self) -> None:
        forbidden_exts = {".pyc", ".pyd", ".so", ".dll", ".dylib"}
        found = []
        for p in (SKILL_DIR / "vendor").rglob("*"):
            if p.is_file() and (p.suffix.lower() in forbidden_exts or "__pycache__" in p.parts):
                found.append(str(p.relative_to(SKILL_DIR / "vendor")))
        self.assertEqual(found, [], f"Forbidden binaries or bytecode found in vendor: {found}")


class TestV02IntegrityAndDrift(unittest.TestCase):
    """V02: Integrity checking, drift detection, and read-only enforcement."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="kb-v02-")
        self.tmp = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_v02_check_clean_vendor_passes(self) -> None:
        res = _run_tool(["--check"])
        self.assertEqual(res.returncode, 0, f"Vendor check failed:\n{res.stderr}")
        self.assertIn("Vendor check passed: 4 packages, 155 files verified", res.stdout)

    def test_v02_check_fails_on_deleted_file(self) -> None:
        disposable_vendor = self.tmp / "vendor"
        shutil.copytree(SKILL_DIR / "vendor", disposable_vendor)
        target = disposable_vendor / "yaml" / "loader.py"
        target.unlink()

        res = _run_tool(["--check", "--vendor-dir", str(disposable_vendor)])
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("Vendored file missing on disk: yaml/loader.py", res.stderr)

    def test_v02_check_fails_on_modified_file(self) -> None:
        disposable_vendor = self.tmp / "vendor"
        shutil.copytree(SKILL_DIR / "vendor", disposable_vendor)
        target = disposable_vendor / "yaml" / "loader.py"
        target.write_bytes(target.read_bytes() + b"\n# tampering\n")

        res = _run_tool(["--check", "--vendor-dir", str(disposable_vendor)])
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("Checksum mismatch for yaml/loader.py", res.stderr)

    def test_v02_check_fails_on_untracked_file(self) -> None:
        disposable_vendor = self.tmp / "vendor"
        shutil.copytree(SKILL_DIR / "vendor", disposable_vendor)
        (disposable_vendor / "yaml" / "extra.py").write_text("# untracked", encoding="utf-8")

        res = _run_tool(["--check", "--vendor-dir", str(disposable_vendor)])
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("Untracked file found in vendor directory", res.stderr)

    def test_v02_check_fails_on_forbidden_binary(self) -> None:
        disposable_vendor = self.tmp / "vendor"
        shutil.copytree(SKILL_DIR / "vendor", disposable_vendor)
        (disposable_vendor / "yaml" / "extension.pyd").write_bytes(b"\x00" * 16)

        res = _run_tool(["--check", "--vendor-dir", str(disposable_vendor)])
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("Forbidden binary or bytecode file found in vendor", res.stderr)

    def test_v02_check_fails_on_version_declaration_drift(self) -> None:
        disposable_reqs = self.tmp / "requirements.txt"
        disposable_reqs.write_text("PyYAML==9.9.9\nmarkdown-it-py==4.2.0\nmdit-py-plugins==0.6.1\nmdurl==0.1.2\n", encoding="utf-8")

        res = _run_tool(["--check", "--requirements", str(disposable_reqs)])
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("Version mismatch for 'pyyaml'", res.stderr)

    def test_v02_check_fails_when_both_declarations_changed_but_old_source_kept(self) -> None:
        # Both requirements.txt and manifest.json say 9.9.9, but files on disk are 0.1.2
        disposable_vendor = self.tmp / "vendor"
        shutil.copytree(SKILL_DIR / "vendor", disposable_vendor)
        man_path = disposable_vendor / "manifest.json"
        man = json.loads(man_path.read_bytes().decode("utf-8"))
        for p in man["packages"]:
            if p["canonical_name"] == "mdurl":
                p["version"] = "9.9.9"
        man_path.write_bytes((json.dumps(man, indent=2) + "\n").encode("utf-8"))

        disposable_reqs = self.tmp / "requirements.txt"
        req_text = (SKILL_DIR / "requirements.txt").read_text(encoding="utf-8").replace("mdurl==0.1.2", "mdurl==9.9.9")
        disposable_reqs.write_text(req_text, encoding="utf-8")

        res = _run_tool(["--check", "--vendor-dir", str(disposable_vendor), "--requirements", str(disposable_reqs)])
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("Source code version mismatch for 'mdurl'", res.stderr)

    def test_v02_check_fails_on_empty_import_roots(self) -> None:
        disposable_vendor = self.tmp / "vendor"
        shutil.copytree(SKILL_DIR / "vendor", disposable_vendor)
        man_path = disposable_vendor / "manifest.json"
        man = json.loads(man_path.read_bytes().decode("utf-8"))
        for p in man["packages"]:
            if p["canonical_name"] == "mdurl":
                p["import_roots"] = []
        man_path.write_bytes((json.dumps(man, indent=2) + "\n").encode("utf-8"))

        res = _run_tool(["--check", "--vendor-dir", str(disposable_vendor)])
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("missing or invalid 'import_roots'", res.stderr)

    def test_v02_check_fails_on_missing_import_root_directory(self) -> None:
        disposable_vendor = self.tmp / "vendor"
        shutil.copytree(SKILL_DIR / "vendor", disposable_vendor)
        man_path = disposable_vendor / "manifest.json"
        man = json.loads(man_path.read_bytes().decode("utf-8"))
        for p in man["packages"]:
            if p["canonical_name"] == "mdurl":
                p["import_roots"] = ["non_existent_pkg_root"]
        man_path.write_bytes((json.dumps(man, indent=2) + "\n").encode("utf-8"))

        res = _run_tool(["--check", "--vendor-dir", str(disposable_vendor)])
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("Import root directory 'non_existent_pkg_root'", res.stderr)

    def test_v02_check_fails_on_unextractable_static_version(self) -> None:
        disposable_vendor = self.tmp / "vendor"
        shutil.copytree(SKILL_DIR / "vendor", disposable_vendor)
        (disposable_vendor / "mdurl" / "__init__.py").write_text("# no version defined here\n", encoding="utf-8")

        res = _run_tool(["--check", "--vendor-dir", str(disposable_vendor)])
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("Unable to statically extract __version__", res.stderr)

    def test_v02_maintenance_modes_reject_malformed_manifest_without_traceback_or_side_effects(self) -> None:
        # Test check, fetch, and rebuild on malformed manifest: {"schema_version": 1, "packages": [{}]}
        malformed_man = self.tmp / "malformed_manifest.json"
        malformed_man.write_text(json.dumps({"schema_version": 1, "packages": [{}]}), encoding="utf-8")

        # 1. --check
        res_check = _run_tool(["--check", "--manifest", str(malformed_man)])
        self.assertNotEqual(res_check.returncode, 0)
        self.assertNotIn("Traceback", res_check.stderr)
        self.assertIn("Malformed manifest structure", res_check.stderr)

        # 2. --fetch: must not traceback, must not create cache directory
        fake_cache = self.tmp / "should_not_exist_cache"
        res_fetch = _run_tool(["--fetch", "--manifest", str(malformed_man), "--source-dir", str(fake_cache)])
        self.assertNotEqual(res_fetch.returncode, 0)
        self.assertNotIn("Traceback", res_fetch.stderr)
        self.assertFalse(fake_cache.exists(), "Cache directory created by --fetch on malformed manifest!")

        # 3. --rebuild: must not traceback, must not create output directory
        fake_out = self.tmp / "should_not_exist_out"
        res_rebuild = _run_tool(["--rebuild", "--manifest", str(malformed_man), "--source-dir", str(fake_cache), "--output", str(fake_out)])
        self.assertNotEqual(res_rebuild.returncode, 0)
        self.assertNotIn("Traceback", res_rebuild.stderr)
        self.assertFalse(fake_out.exists(), "Output directory created by --rebuild on malformed manifest!")

    def test_v02_check_is_read_only(self) -> None:
        def get_tree_state(base: Path) -> dict[str, tuple[int, int]]:
            return {
                str(p.relative_to(base)): (p.stat().st_size, p.stat().st_mtime_ns)
                for p in base.rglob("*") if p.is_file()
            }
        before = get_tree_state(SKILL_DIR / "vendor")
        res = _run_tool(["--check"])
        self.assertEqual(res.returncode, 0)
        after = get_tree_state(SKILL_DIR / "vendor")
        self.assertEqual(before, after)


class TestV03DeterministicRebuild(unittest.TestCase):
    """V03: Offline deterministic rebuild from cached artifacts with pure LF serialization."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="kb-v03-")
        self.tmp = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_v03_rebuild_from_cache_byte_identical(self) -> None:
        if not VENDOR_CACHE.is_dir() or not any(VENDOR_CACHE.glob("*.whl")):
            self.fail(
                f"Required vendor cache missing at '{VENDOR_CACHE}'. "
                "Run 'python tools/vendor_dependencies.py --fetch' to prepare artifacts before running rebuild tests."
            )

        out_rebuilt = self.tmp / "rebuilt_vendor"
        res = _run_tool(["--rebuild", "--source-dir", str(VENDOR_CACHE), "--output", str(out_rebuilt)])
        self.assertEqual(res.returncode, 0, f"Rebuild failed:\n{res.stderr}")

        # Check line endings of rebuilt manifest: exactly 0 CRLFs
        rebuilt_man_bytes = (out_rebuilt / "manifest.json").read_bytes()
        self.assertEqual(rebuilt_man_bytes.count(b"\r\n"), 0, "Rebuilt manifest contains CRLF line endings!")

        # Compare files byte-for-byte with repo vendor
        repo_vendor = SKILL_DIR / "vendor"
        repo_files = {str(p.relative_to(repo_vendor)).replace("\\", "/"): p.read_bytes() for p in repo_vendor.rglob("*") if p.is_file()}
        rebuilt_files = {str(p.relative_to(out_rebuilt)).replace("\\", "/"): p.read_bytes() for p in out_rebuilt.rglob("*") if p.is_file()}

        self.assertEqual(set(repo_files.keys()), set(rebuilt_files.keys()))
        for rel_p, orig_bytes in repo_files.items():
            self.assertEqual(orig_bytes, rebuilt_files[rel_p], f"Byte difference in rebuilt file: {rel_p}")

    def test_v03_rebuild_refuses_existing_output_directory(self) -> None:
        existing_out = self.tmp / "existing_dir"
        existing_out.mkdir()
        res = _run_tool(["--rebuild", "--source-dir", str(VENDOR_CACHE), "--output", str(existing_out)])
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("already exists", res.stderr)

    def test_v03_rebuild_corrupted_cached_artifact_fails_and_cleans_up(self) -> None:
        # Self-contained fixture: create synthetic manifest and corrupted archive
        corrupt_cache = self.tmp / "corrupt_cache"
        corrupt_cache.mkdir()
        art_path = corrupt_cache / "pkg-1.0-py3-none-any.whl"
        art_path.write_bytes(b"corrupted content")

        man_data = {
            "schema_version": 1,
            "packages": [{
                "canonical_name": "pkg",
                "version": "1.0",
                "artifact_filename": "pkg-1.0-py3-none-any.whl",
                "artifact_sha256": "0" * 64,  # mismatched hash
                "artifact_type": "wheel",
                "artifact_url": "https://example.com/pkg.whl",
                "import_roots": ["pkg"],
                "license_files": ["pkg/LICENSE"],
                "extraction_mapping": {"pkg": "pkg"},
            }],
            "files": [],
        }
        man_path = self.tmp / "synthetic_manifest.json"
        man_path.write_bytes(json.dumps(man_data).encode("utf-8"))

        out_dir = self.tmp / "rebuild_corrupt_out"
        res = _run_tool(["--rebuild", "--manifest", str(man_path), "--source-dir", str(corrupt_cache), "--output", str(out_dir)])
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("corrupted", res.stderr.lower())
        self.assertFalse(out_dir.exists(), "Output directory was not cleaned up on rebuild failure!")

    def test_v03_rebuild_missing_cache_artifact_fails_and_cleans_up(self) -> None:
        empty_cache = self.tmp / "empty_cache"
        empty_cache.mkdir()
        out_dir = self.tmp / "rebuild_missing_out"
        res = _run_tool(["--rebuild", "--source-dir", str(empty_cache), "--output", str(out_dir)])
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("missing", res.stderr.lower())
        self.assertFalse(out_dir.exists())


class TestV04ArchiveSafetyFixtures(unittest.TestCase):
    """V04: Real archive fixtures for path traversal, symlinks, device nodes, size limits, and cleanup."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="kb-v04-")
        self.tmp = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _extract(self, art_path: Path, art_type: str, mapping: dict[str, str]) -> tuple[bool, str]:
        from tools.vendor_dependencies import extract_package
        out_dir = self.tmp / "extract_dest"
        out_dir.mkdir(parents=True, exist_ok=True)
        pkg_meta = {
            "canonical_name": "testpkg",
            "version": "1.0",
            "artifact_type": art_type,
            "extraction_mapping": mapping,
        }
        try:
            extract_package(art_path, pkg_meta, out_dir, {}, [0])
            return True, ""
        except Exception as e:
            return False, str(e)

    def test_v04_tar_posix_path_traversal_rejected(self) -> None:
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            ti = tarfile.TarInfo(name="pkg/../escape.py")
            ti.size = 4
            tar.addfile(ti, io.BytesIO(b"data"))
        art = self.tmp / "trav.tar.gz"
        art.write_bytes(buf.getvalue())
        ok, err = self._extract(art, "sdist", {"pkg": "testpkg"})
        self.assertFalse(ok)
        self.assertIn("path traversal", err.lower())

    def test_v04_tar_windows_path_traversal_rejected(self) -> None:
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            ti = tarfile.TarInfo(name="pkg\\..\\escape.py")
            ti.size = 4
            tar.addfile(ti, io.BytesIO(b"data"))
        art = self.tmp / "trav_win.tar.gz"
        art.write_bytes(buf.getvalue())
        ok, err = self._extract(art, "sdist", {"pkg": "testpkg"})
        self.assertFalse(ok)
        self.assertIn("path traversal", err.lower())

    def test_v04_wheel_posix_path_traversal_rejected(self) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w") as z:
            z.writestr("testpkg/../escape.py", b"data")
        art = self.tmp / "trav.whl"
        art.write_bytes(buf.getvalue())
        ok, err = self._extract(art, "wheel", {"testpkg": "testpkg"})
        self.assertFalse(ok)
        self.assertIn("path traversal", err.lower())

    def test_v04_wheel_windows_path_traversal_rejected(self) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w") as z:
            z.writestr("testpkg\\..\\escape.py", b"data")
        art = self.tmp / "trav_win.whl"
        art.write_bytes(buf.getvalue())
        ok, err = self._extract(art, "wheel", {"testpkg": "testpkg"})
        self.assertFalse(ok)
        self.assertIn("path traversal", err.lower())

    def test_v04_archive_absolute_path_rejected(self) -> None:
        from tools.vendor_dependencies import validate_member_path
        with self.assertRaises(ValueError):
            validate_member_path("/absolute/path.py")
        with self.assertRaises(ValueError):
            validate_member_path("C:\\windows\\system32")

    def test_v04_archive_reserved_device_name_rejected(self) -> None:
        from tools.vendor_dependencies import validate_member_path
        with self.assertRaises(ValueError):
            validate_member_path("aux.py")
        with self.assertRaises(ValueError):
            validate_member_path("con.txt")

    def test_v04_archive_symlink_rejected(self) -> None:
        # Tar symlink
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            ti = tarfile.TarInfo(name="pkg/link.py")
            ti.type = tarfile.SYMTYPE
            ti.linkname = "target.py"
            tar.addfile(ti)
        art = self.tmp / "symlink.tar.gz"
        art.write_bytes(buf.getvalue())
        ok, err = self._extract(art, "sdist", {"pkg": "testpkg"})
        self.assertFalse(ok)
        self.assertIn("non-regular", err.lower())

        # Wheel symlink
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w") as z:
            zi = zipfile.ZipInfo(filename="testpkg/link.py")
            zi.external_attr = 0o120777 << 16
            z.writestr(zi, b"target.py")
        art_whl = self.tmp / "symlink.whl"
        art_whl.write_bytes(buf.getvalue())
        ok, err = self._extract(art_whl, "wheel", {"testpkg": "testpkg"})
        self.assertFalse(ok)
        self.assertIn("symlink", err.lower())

    def test_v04_archive_device_node_rejected(self) -> None:
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            ti = tarfile.TarInfo(name="pkg/dev")
            ti.type = tarfile.FIFOTYPE
            tar.addfile(ti)
        art = self.tmp / "fifo.tar.gz"
        art.write_bytes(buf.getvalue())
        ok, err = self._extract(art, "sdist", {"pkg": "testpkg"})
        self.assertFalse(ok)
        self.assertIn("non-regular", err.lower())

    def test_v04_archive_case_collision_rejected(self) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w") as z:
            z.writestr("testpkg/File.py", b"data1")
            z.writestr("testpkg/file.py", b"data2")
        art = self.tmp / "case.whl"
        art.write_bytes(buf.getvalue())
        ok, err = self._extract(art, "wheel", {"testpkg": "testpkg"})
        self.assertFalse(ok)
        self.assertIn("case collision", err.lower())

    def test_v04_archive_duplicate_entry_rejected(self) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w") as z:
            z.writestr("testpkg/same.py", b"data1")
            z.writestr("testpkg/same.py", b"data2")
        art = self.tmp / "dup.whl"
        art.write_bytes(buf.getvalue())
        ok, err = self._extract(art, "wheel", {"testpkg": "testpkg"})
        self.assertFalse(ok)
        self.assertIn("duplicate destination", err.lower())

    def test_v04_archive_exceeds_single_file_size_limit(self) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as z:
            # 11 MiB uncompressed payload (single file limit is 10 MiB = 10485760 bytes)
            z.writestr("testpkg/large.py", b"\x00" * (11 * 1024 * 1024))
        art = self.tmp / "oversize_single.whl"
        art.write_bytes(buf.getvalue())
        ok, err = self._extract(art, "wheel", {"testpkg": "testpkg"})
        self.assertFalse(ok)
        self.assertIn("exceeds size limit", err.lower())

    def test_v04_archive_exceeds_total_payload_size_limit(self) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as z:
            # 6 files of 9 MiB each = 54 MiB total (total payload limit is 50 MiB = 52428800 bytes)
            for i in range(6):
                z.writestr(f"testpkg/file_{i}.py", b"\x00" * (9 * 1024 * 1024))
        art = self.tmp / "oversize_total.whl"
        art.write_bytes(buf.getvalue())
        ok, err = self._extract(art, "wheel", {"testpkg": "testpkg"})
        self.assertFalse(ok)
        self.assertIn("exceed limit", err.lower())


class TestV05IsolatedDistributionCopy(unittest.TestCase):
    """V05: End-to-end acceptance of standalone Skill copy in Chinese and spaced path with -I -S."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="kb-v05-")
        self.tmp = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_v05_standalone_distribution_in_chinese_spaced_path(self) -> None:
        base = self.tmp / "知识库 分发 路径 with spaces"
        base.mkdir(parents=True)

        dist_skill = base / "knowledge-base-manager"
        shutil.copytree(SKILL_DIR, dist_skill, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        cli_path = dist_skill / "scripts" / "kb.py"

        # 1. --help exits 0 in isolated mode
        res_help = subprocess.run(
            [sys.executable, "-I", "-S", "-B", "-X", "utf8", str(cli_path), "--help"],
            capture_output=True, text=True, cwd=base, encoding="utf-8"
        )
        self.assertEqual(res_help.returncode, 0)
        self.assertIn("usage: kb", res_help.stdout)

        # 2. resolve works in isolated mode
        res_res = subprocess.run(
            [sys.executable, "-I", "-S", "-B", "-X", "utf8", str(cli_path), "--format", "json", "resolve", "--requested", str(base)],
            capture_output=True, text=True, cwd=base, encoding="utf-8"
        )
        self.assertEqual(res_res.returncode, 0)
        data = json.loads(res_res.stdout)
        self.assertEqual(data.get("command"), "resolve")


class TestV06NoExternalPackagesAndSourceIntrospection(unittest.TestCase):
    """V06: Negative control for all 4 packages under -I -S and positive source introspection."""

    def test_v06_negative_control_all_four_packages_unimportable_without_vendor(self) -> None:
        for mod in ["yaml", "markdown_it", "mdit_py_plugins", "mdurl"]:
            res = subprocess.run(
                [sys.executable, "-I", "-S", "-B", "-X", "utf8", "-c", f"import {mod}"],
                capture_output=True, text=True
            )
            self.assertNotEqual(res.returncode, 0, f"Module '{mod}' should NOT be importable in isolated mode (-I -S)")

    def test_v06_positive_introspection_all_four_packages_loaded_from_vendor(self) -> None:
        vendor_dir = SKILL_DIR / "vendor"
        code = f"""
import sys
from pathlib import Path
sys.dont_write_bytecode = True
vendor = Path({repr(str(vendor_dir))}).resolve()
sys.path.insert(0, str(vendor))

import yaml, markdown_it, mdit_py_plugins, mdurl

mods = [('yaml', yaml), ('markdown_it', markdown_it), ('mdit_py_plugins', mdit_py_plugins), ('mdurl', mdurl)]
for name, m in mods:
    m_path = Path(m.__file__).resolve()
    assert m_path.is_relative_to(vendor), f"{{name}} loaded from {{m_path}}, not vendor {{vendor}}"

assert yaml.__with_libyaml__ is False, "yaml.__with_libyaml__ must be False"
print("PASS: All four modules loaded from vendor, C-extension disabled.")
"""
        res = subprocess.run(
            [sys.executable, "-I", "-S", "-B", "-X", "utf8", "-c", code],
            capture_output=True, text=True, encoding="utf-8"
        )
        self.assertEqual(res.returncode, 0, f"Introspection failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}")
        self.assertIn("PASS", res.stdout)


class TestV07FullCommandLifecycleAndSourceHashPreservation(unittest.TestCase):
    """V07: Full CLI lifecycle with external sources and source file SHA-256 preservation."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="kb-v07-")
        self.tmp = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_v07_full_command_cycle_with_external_source_and_hash_preservation(self) -> None:
        base = self.tmp / "test_env_with_spaces"
        base.mkdir()

        # Copy only knowledge-base-manager directory
        dist_skill = base / "knowledge-base-manager"
        shutil.copytree(SKILL_DIR, dist_skill, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        cli_path = dist_skill / "scripts" / "kb.py"

        # 1. Create external project with source file
        ext_project = base / "external_project"
        ext_src = ext_project / "src" / "module.py"
        ext_src.parent.mkdir(parents=True)
        ext_src.write_text("def hello(): return 'external code'\n", encoding="utf-8")

        # 2. Create valid knowledge base with registered external source
        kb_dir = base / "sample_kb"
        content_dir = kb_dir / "content"
        content_dir.mkdir(parents=True)
        (kb_dir / "kb.yaml").write_text("schema_version: 1\ncontent_dir: content\nentrypoint: content/index.md\n", encoding="utf-8")

        ext_uri = ext_src.as_uri()
        note_content = (
            "# Main Knowledge Note\n\n"
            "Here is an offline formula: $E = mc^2$.\n\n"
            f"[External Source]({ext_uri}) <!-- kb-external-local -->\n"
            "project-id: test-ext-proj; project-relative source: src/module.py; verified: 2026-09-22; revision: rev-1\n"
        )
        (content_dir / "index.md").write_text(note_content, encoding="utf-8")

        # Record SHA-256 snapshot of all KB files before any operation
        import hashlib
        def get_kb_hashes() -> dict[str, str]:
            hashes = {}
            for p in sorted(kb_dir.rglob("*")):
                if p.is_file():
                    rel = str(p.relative_to(kb_dir)).replace("\\", "/")
                    hashes[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
            return hashes

        initial_kb_hashes = get_kb_hashes()

        def run_cmd(args: list[str]) -> dict:
            cmd = [sys.executable, "-I", "-S", "-B", "-X", "utf8", str(cli_path), "--format", "json", *args]
            res = subprocess.run(cmd, cwd=base, capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(res.returncode, 0, f"Command {args} failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}")
            return json.loads(res.stdout)

        # 1. resolve
        r_resolve = run_cmd(["resolve", "--requested", str(kb_dir)])
        self.assertEqual(r_resolve["status"], "resolved")

        # 2. inspect
        r_inspect = run_cmd(["inspect", "--root", str(kb_dir)])
        self.assertEqual(r_inspect["status"], "ok")

        # 3. search
        r_search = run_cmd(["search", "--root", str(kb_dir), "--query", "formula"])
        self.assertEqual(r_search["status"], "ok")
        self.assertEqual(r_search["data"]["total"], 1)

        # 4. read
        r_read = run_cmd(["read", "--root", str(kb_dir), "--path", "index.md"])
        self.assertEqual(r_read["status"], "ok")
        self.assertIn("Main Knowledge Note", r_read["data"]["text"])

        # 5. audit
        r_audit = run_cmd(["audit", "--root", str(kb_dir)])
        self.assertEqual(r_audit["status"], "ok")
        self.assertEqual(r_audit["data"]["errors"], 0)

        # 6. build-static
        html_dir = base / "static_html_output"
        r_build = run_cmd(["build-static", "--root", str(kb_dir), "--destination", str(html_dir)])
        self.assertEqual(r_build["status"], "success")
        self.assertTrue((html_dir / "index.html").is_file())

        # 7. backup plan
        backup_dir = base / "backup_archive"
        r_plan = run_cmd(["backup", "--root", str(kb_dir), "--destination", str(backup_dir)])
        self.assertEqual(r_plan["status"], "plan")
        digest = r_plan["data"]["plan"]["plan_digest"]

        # 8. backup execute
        r_exec = run_cmd(["backup", "--root", str(kb_dir), "--destination", str(backup_dir), "--execute", "--confirmed-plan-digest", digest])
        self.assertEqual(r_exec["status"], "created")
        bundle = backup_dir / "portable-kb"
        self.assertTrue((bundle / "backup-manifest.json").is_file())

        # 9. verify-backup
        r_verify = run_cmd(["verify-backup", "--bundle", str(bundle)])
        self.assertEqual(r_verify["status"], "valid")

        # 10. restore execute
        restored_dir = base / "restored_kb"
        r_restore = run_cmd(["restore", "--bundle", str(bundle), "--destination", str(restored_dir), "--execute"])
        self.assertEqual(r_restore["status"], "restored")

        # 11. audit restored kb
        r_restored_audit = run_cmd(["audit", "--root", str(restored_dir)])
        self.assertEqual(r_restored_audit["status"], "ok")
        self.assertEqual(r_restored_audit["data"]["errors"], 0)

        # Invariant: Verify original knowledge base files are 100% byte-identical
        final_kb_hashes = get_kb_hashes()
        self.assertEqual(initial_kb_hashes, final_kb_hashes, "Live knowledge base files were modified during operations!")


class TestV08RegressionExistingSuites(unittest.TestCase):
    """V08: Regression asserting 6 existing core suites pass under isolated vendor mode."""

    def test_v08_six_core_suites_pass_under_isolated_vendor(self) -> None:
        vendor_dir = SKILL_DIR / "vendor"
        code = f"""
import sys
from pathlib import Path
sys.dont_write_bytecode = True
sys.path[:0] = [{repr(str(vendor_dir))}, {repr(str(SCRIPTS_DIR))}]
import yaml, markdown_it, mdit_py_plugins, mdurl
assert Path(yaml.__file__).resolve().is_relative_to(Path({repr(str(vendor_dir))}).resolve())
assert yaml.__with_libyaml__ is False
import runpy
target = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(target.parent))
sys.argv = [str(target), *sys.argv[2:]]
runpy.run_path(str(target), run_name='__main__')
"""
        suites = ["parser", "query", "audit", "workflow", "backup", "static"]
        for name in suites:
            suite_file = TESTS_DIR / f"test-kb-python-{name}.py"
            cmd = [sys.executable, "-I", "-S", "-B", "-X", "utf8", "-c", code, str(suite_file)]
            res = subprocess.run(cmd, capture_output=True, text=True, cwd=PROJECT_ROOT, encoding="utf-8")
            self.assertEqual(res.returncode, 0, f"Suite {name} failed under vendor in isolated mode:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}")


class TestV09ExternalEnvironmentConflicts(unittest.TestCase):
    """V09: Conflict detection and precedence against external modules."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="kb-v09-")
        self.tmp = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_v09_unloaded_external_sys_path_vendor_takes_precedence(self) -> None:
        # Create a fake external 'yaml' package on sys.path, but do not import it before cli.main
        fake_site = self.tmp / "fake_site"
        (fake_site / "yaml").mkdir(parents=True)
        (fake_site / "yaml" / "__init__.py").write_text("__version__ = '0.0.1_external'\n__with_libyaml__ = False\n", encoding="utf-8")

        # Create a valid fixture KB
        sample_kb = self.tmp / "sample_kb"
        (sample_kb / "content").mkdir(parents=True)
        (sample_kb / "kb.yaml").write_text("schema_version: 1\ncontent_dir: content\nentrypoint: content/index.md\n", encoding="utf-8")
        (sample_kb / "content" / "index.md").write_text("# Test\n", encoding="utf-8")

        code = f"""
import sys
from pathlib import Path
sys.dont_write_bytecode = True
# Add fake site-packages to sys.path
sys.path.insert(0, {repr(str(fake_site))})
scripts = Path({repr(str(SCRIPTS_DIR))})
sys.path.insert(0, str(scripts))

from kb_core.cli import main
rc = main(['--format', 'json', 'inspect', '--root', {repr(str(sample_kb))}])
import yaml
vendor_resolved = Path({repr(str(SKILL_DIR / 'vendor'))}).resolve()
assert Path(yaml.__file__).resolve().is_relative_to(vendor_resolved), f"yaml was loaded from {{yaml.__file__}}!"
assert yaml.__version__ == '6.0.3', f"yaml version was {{yaml.__version__}}!"
sys.exit(rc)
"""
        cmd = [sys.executable, "-B", "-X", "utf8", "-c", code]
        res = subprocess.run(cmd, capture_output=True, text=True, cwd=self.tmp, encoding="utf-8")
        self.assertEqual(res.returncode, 0, f"Failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}")

    def test_v09_preloaded_external_top_level_fails_with_conflict(self) -> None:
        code = f"""
import sys, yaml
from pathlib import Path
scripts = Path({repr(str(SCRIPTS_DIR))})
sys.path.insert(0, str(scripts))
from kb_core.cli import main
sys.exit(main(['--format', 'json', 'inspect', '--root', {repr(str(self.tmp))}]))
"""
        cmd = [sys.executable, "-B", "-X", "utf8", "-c", code]
        res = subprocess.run(cmd, capture_output=True, text=True, cwd=self.tmp, encoding="utf-8")
        self.assertEqual(res.returncode, 3)
        data = json.loads(res.stdout)
        self.assertEqual(data.get("status"), "failed")
        self.assertTrue(any(d.get("code") == "DEPENDENCY_CONFLICT" for d in data.get("diagnostics", [])))

    def test_v09_preloaded_external_submodule_fails_with_conflict(self) -> None:
        code = f"""
import sys, yaml.scanner
from pathlib import Path
scripts = Path({repr(str(SCRIPTS_DIR))})
sys.path.insert(0, str(scripts))
from kb_core.cli import main
sys.exit(main(['--format', 'json', 'inspect', '--root', {repr(str(self.tmp))}]))
"""
        cmd = [sys.executable, "-B", "-X", "utf8", "-c", code]
        res = subprocess.run(cmd, capture_output=True, text=True, cwd=self.tmp, encoding="utf-8")
        self.assertEqual(res.returncode, 3)
        data = json.loads(res.stdout)
        self.assertEqual(data.get("status"), "failed")
        self.assertTrue(any(d.get("code") == "DEPENDENCY_CONFLICT" for d in data.get("diagnostics", [])))

    def test_v09_conflict_without_file_attribute_fails_with_conflict(self) -> None:
        code = f"""
import sys, types
from pathlib import Path
# Insert a module stub without __file__ attribute into sys.modules['yaml']
stub = types.ModuleType('yaml')
sys.modules['yaml'] = stub

scripts = Path({repr(str(SCRIPTS_DIR))})
sys.path.insert(0, str(scripts))
from kb_core.cli import main
sys.exit(main(['--format', 'json', 'inspect', '--root', {repr(str(self.tmp))}]))
"""
        cmd = [sys.executable, "-B", "-X", "utf8", "-c", code]
        res = subprocess.run(cmd, capture_output=True, text=True, cwd=self.tmp, encoding="utf-8")
        self.assertEqual(res.returncode, 3)
        data = json.loads(res.stdout)
        self.assertEqual(data.get("status"), "failed")
        self.assertTrue(any(d.get("code") == "DEPENDENCY_CONFLICT" for d in data.get("diagnostics", [])))

    def test_v09_conflict_creates_no_output_directory(self) -> None:
        target_out = self.tmp / "should_not_exist_out"
        code = f"""
import sys, yaml
from pathlib import Path
scripts = Path({repr(str(SCRIPTS_DIR))})
sys.path.insert(0, str(scripts))
from kb_core.cli import main
sys.exit(main(['--format', 'json', 'build-static', '--root', {repr(str(self.tmp))}, '--destination', {repr(str(target_out))}]))
"""
        cmd = [sys.executable, "-B", "-X", "utf8", "-c", code]
        res = subprocess.run(cmd, capture_output=True, text=True, cwd=self.tmp, encoding="utf-8")
        self.assertEqual(res.returncode, 3)
        self.assertFalse(target_out.exists(), "Output directory was created despite dependency conflict!")


class TestV10MissingAndInvalidDiagnostics(unittest.TestCase):
    """V10: Diagnostic envelopes, exit code 3, and help/resolve independence."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="kb-v10-")
        self.tmp = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_v10_vendor_dir_missing_returns_dependency_missing(self) -> None:
        skill_copy = self.tmp / "skill_no_vendor"
        shutil.copytree(SKILL_DIR, skill_copy, ignore=shutil.ignore_patterns("vendor", "__pycache__", "*.pyc"))
        rc, data, _ = _run_isolated_cli(skill_copy, ["inspect", "--root", str(self.tmp)], self.tmp)
        self.assertEqual(rc, 3)
        self.assertEqual(data.get("status"), "failed")
        self.assertTrue(any(d.get("code") == "DEPENDENCY_MISSING" for d in data.get("diagnostics", [])))

    def test_v10_manifest_missing_returns_dependency_missing(self) -> None:
        skill_copy = self.tmp / "skill_no_man"
        shutil.copytree(SKILL_DIR, skill_copy, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        (skill_copy / "vendor" / "manifest.json").unlink()
        rc, data, _ = _run_isolated_cli(skill_copy, ["inspect", "--root", str(self.tmp)], self.tmp)
        self.assertEqual(rc, 3)
        self.assertTrue(any(d.get("code") == "DEPENDENCY_MISSING" for d in data.get("diagnostics", [])))

    def test_v10_entrypoint_missing_returns_dependency_missing(self) -> None:
        skill_copy = self.tmp / "skill_missing_entry"
        shutil.copytree(SKILL_DIR, skill_copy, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        (skill_copy / "vendor" / "yaml" / "__init__.py").unlink()
        rc, data, _ = _run_isolated_cli(skill_copy, ["inspect", "--root", str(self.tmp)], self.tmp)
        self.assertEqual(rc, 3)
        self.assertTrue(any(d.get("code") == "DEPENDENCY_MISSING" for d in data.get("diagnostics", [])))

    def test_v10_corrupted_json_returns_dependency_invalid(self) -> None:
        skill_copy = self.tmp / "skill_bad_json"
        shutil.copytree(SKILL_DIR, skill_copy, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        (skill_copy / "vendor" / "manifest.json").write_text("{invalid json", encoding="utf-8")
        rc, data, _ = _run_isolated_cli(skill_copy, ["inspect", "--root", str(self.tmp)], self.tmp)
        self.assertEqual(rc, 3)
        self.assertTrue(any(d.get("code") == "DEPENDENCY_INVALID" for d in data.get("diagnostics", [])))

    def test_v10_structural_manifest_list_returns_dependency_invalid(self) -> None:
        skill_copy = self.tmp / "skill_list_man"
        shutil.copytree(SKILL_DIR, skill_copy, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        (skill_copy / "vendor" / "manifest.json").write_text("[]", encoding="utf-8")
        rc, data, _ = _run_isolated_cli(skill_copy, ["inspect", "--root", str(self.tmp)], self.tmp)
        self.assertEqual(rc, 3)
        self.assertTrue(any(d.get("code") == "DEPENDENCY_INVALID" for d in data.get("diagnostics", [])))

    def test_v10_structural_manifest_packages_null_returns_dependency_invalid(self) -> None:
        skill_copy = self.tmp / "skill_null_pkgs"
        shutil.copytree(SKILL_DIR, skill_copy, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        (skill_copy / "vendor" / "manifest.json").write_text('{"schema_version": 1, "packages": null}', encoding="utf-8")
        rc, data, _ = _run_isolated_cli(skill_copy, ["inspect", "--root", str(self.tmp)], self.tmp)
        self.assertEqual(rc, 3)
        self.assertTrue(any(d.get("code") == "DEPENDENCY_INVALID" for d in data.get("diagnostics", [])))

    def test_v10_structural_manifest_malformed_package_returns_dependency_invalid(self) -> None:
        skill_copy = self.tmp / "skill_malformed_pkg"
        shutil.copytree(SKILL_DIR, skill_copy, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        (skill_copy / "vendor" / "manifest.json").write_text('{"schema_version": 1, "packages": [{}]}', encoding="utf-8")
        rc, data, _ = _run_isolated_cli(skill_copy, ["inspect", "--root", str(self.tmp)], self.tmp)
        self.assertEqual(rc, 3)
        self.assertTrue(any(d.get("code") == "DEPENDENCY_INVALID" for d in data.get("diagnostics", [])))

    def test_v10_structural_manifest_bad_schema_returns_dependency_invalid(self) -> None:
        skill_copy = self.tmp / "skill_bad_schema"
        shutil.copytree(SKILL_DIR, skill_copy, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        (skill_copy / "vendor" / "manifest.json").write_text('{"schema_version": 99, "packages": []}', encoding="utf-8")
        rc, data, _ = _run_isolated_cli(skill_copy, ["inspect", "--root", str(self.tmp)], self.tmp)
        self.assertEqual(rc, 3)
        self.assertTrue(any(d.get("code") == "DEPENDENCY_INVALID" for d in data.get("diagnostics", [])))

    def test_v10_structural_manifest_duplicate_package_returns_dependency_invalid(self) -> None:
        skill_copy = self.tmp / "skill_dup_pkg"
        shutil.copytree(SKILL_DIR, skill_copy, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        dup_content = '{"schema_version": 1, "packages": [{"canonical_name": "pyyaml", "version": "6.0.3"}, {"canonical_name": "pyyaml", "version": "6.0.3"}]}'
        (skill_copy / "vendor" / "manifest.json").write_text(dup_content, encoding="utf-8")
        rc, data, _ = _run_isolated_cli(skill_copy, ["inspect", "--root", str(self.tmp)], self.tmp)
        self.assertEqual(rc, 3)
        self.assertTrue(any(d.get("code") == "DEPENDENCY_INVALID" for d in data.get("diagnostics", [])))

    def test_v10_manifest_version_mismatch_returns_dependency_invalid(self) -> None:
        skill_copy = self.tmp / "skill_bad_ver"
        shutil.copytree(SKILL_DIR, skill_copy, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        man_path = skill_copy / "vendor" / "manifest.json"
        man = json.loads(man_path.read_bytes().decode("utf-8"))
        for p in man["packages"]:
            if p["canonical_name"] == "pyyaml":
                p["version"] = "99.0.0"
        man_path.write_bytes((json.dumps(man, indent=2) + "\n").encode("utf-8"))
        rc, data, _ = _run_isolated_cli(skill_copy, ["inspect", "--root", str(self.tmp)], self.tmp)
        self.assertEqual(rc, 3)
        self.assertTrue(any(d.get("code") == "DEPENDENCY_INVALID" for d in data.get("diagnostics", [])))

    def test_v10_help_and_resolve_independent_of_vendor(self) -> None:
        skill_copy = self.tmp / "skill_no_vendor_help"
        shutil.copytree(SKILL_DIR, skill_copy, ignore=shutil.ignore_patterns("vendor", "__pycache__", "*.pyc"))
        cli_path = skill_copy / "scripts" / "kb.py"

        res_help = subprocess.run(
            [sys.executable, "-I", "-S", "-B", "-X", "utf8", str(cli_path), "--help"],
            capture_output=True, text=True, cwd=self.tmp, encoding="utf-8"
        )
        self.assertEqual(res_help.returncode, 0)
        self.assertIn("usage: kb", res_help.stdout)

        res_res = subprocess.run(
            [sys.executable, "-I", "-S", "-B", "-X", "utf8", str(cli_path), "--format", "json", "resolve", "--requested", str(self.tmp)],
            capture_output=True, text=True, cwd=self.tmp, encoding="utf-8"
        )
        self.assertEqual(res_res.returncode, 0)
        data = json.loads(res_res.stdout)
        self.assertEqual(data.get("command"), "resolve")


class TestV11IdempotenceAndSideEffects(unittest.TestCase):
    """V11: Idempotent initialization, bytecode suppression, and failure containment."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="kb-v11-")
        self.tmp = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_v11_idempotent_initialization(self) -> None:
        code = f"""
import sys
from pathlib import Path
sys.dont_write_bytecode = True
scripts = Path({repr(str(SCRIPTS_DIR))})
sys.path.insert(0, str(scripts))
from kb_core.runtime_dependencies import ensure_runtime_dependencies

ok1, env1 = ensure_runtime_dependencies()
assert ok1 and env1 is None
len1 = len(sys.path)
path1 = list(sys.path)

ok2, env2 = ensure_runtime_dependencies()
assert ok2 and env2 is None
len2 = len(sys.path)
path2 = list(sys.path)

assert len1 == len2, f"sys.path changed: {{len1}} vs {{len2}}"
assert path1 == path2, "sys.path contents or order changed on second initialization!"
print("PASS: ensure_runtime_dependencies is strictly idempotent.")
"""
        cmd = [sys.executable, "-B", "-X", "utf8", "-c", code]
        res = subprocess.run(cmd, capture_output=True, text=True, cwd=self.tmp, encoding="utf-8")
        self.assertEqual(res.returncode, 0, f"Failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}")
        self.assertIn("PASS", res.stdout)

    def test_v11_no_bytecode_written(self) -> None:
        pyc_files = list((SKILL_DIR / "vendor").rglob("*.pyc")) + list((SKILL_DIR / "vendor").rglob("__pycache__"))
        self.assertEqual(pyc_files, [], f"Bytecode found in vendor tree: {pyc_files}")

    def test_v11_failure_modes_create_no_output_directories(self) -> None:
        # Broken vendor attempting write commands: build-static, backup, restore
        skill_copy = self.tmp / "skill_broken"
        shutil.copytree(SKILL_DIR, skill_copy, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        (skill_copy / "vendor" / "manifest.json").write_text("[]", encoding="utf-8")

        # 1. build-static
        target_html = self.tmp / "target_html_out"
        rc, _, _ = _run_isolated_cli(skill_copy, ["build-static", "--root", str(self.tmp), "--destination", str(target_html)], self.tmp)
        self.assertEqual(rc, 3)
        self.assertFalse(target_html.exists(), "build-static output directory created when dependency check failed!")

        # 2. backup
        target_backup = self.tmp / "target_backup_out"
        rc, _, _ = _run_isolated_cli(skill_copy, ["backup", "--root", str(self.tmp), "--destination", str(target_backup), "--execute"], self.tmp)
        self.assertEqual(rc, 3)
        self.assertFalse(target_backup.exists(), "backup destination directory created when dependency check failed!")

        # 3. restore
        target_restore = self.tmp / "target_restore_out"
        fake_bundle = self.tmp / "fake_bundle_dir"
        rc, _, _ = _run_isolated_cli(skill_copy, ["restore", "--bundle", str(fake_bundle), "--destination", str(target_restore), "--execute"], self.tmp)
        self.assertEqual(rc, 3)
        self.assertFalse(target_restore.exists(), "restore destination directory created when dependency check failed!")


if __name__ == "__main__":
    unittest.main()
