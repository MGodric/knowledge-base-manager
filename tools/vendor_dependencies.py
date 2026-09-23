#!/usr/bin/env python3
"""Vendor dependency management and verification tool.

Standard library only. Manages vendored pure-Python dependencies for knowledge-base-manager.
Supported operations:
  --check: Verify that vendored files on disk match requirements and manifest (offline, read-only).
  --fetch: Download locked upstream artifacts into cache and verify checksums.
  --rebuild: Rebuild vendor directory from locked cached artifacts (offline).
  --refresh: Query PyPI for requirements, fetch artifacts, and generate a candidate vendor tree.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tarfile
import urllib.request
import zipfile
from typing import Any

# Prevent bytecode creation
sys.dont_write_bytecode = True

SCHEMA_VERSION = 1
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MiB per extracted file
MAX_TOTAL_BYTES = 50 * 1024 * 1024  # 50 MiB total extracted vendor payload
FORBIDDEN_EXTENSIONS = {".pyc", ".pyd", ".so", ".dll", ".dylib"}

WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}

DEFAULT_KNOWN_PACKAGES: dict[str, dict[str, Any]] = {
    "pyyaml": {
        "canonical_name": "pyyaml",
        "display_name": "PyYAML",
        "import_roots": ["yaml", "_yaml"],
        "artifact_type": "sdist",
        "extraction_mapping": {
            "pyyaml-{version}/lib/yaml": "yaml",
            "pyyaml-{version}/lib/_yaml": "_yaml",
            "pyyaml-{version}/LICENSE": "licenses/pyyaml/LICENSE",
        },
        "license_files": ["licenses/pyyaml/LICENSE"],
    },
    "markdown-it-py": {
        "canonical_name": "markdown-it-py",
        "display_name": "markdown-it-py",
        "import_roots": ["markdown_it"],
        "artifact_type": "wheel",
        "extraction_mapping": {
            "markdown_it": "markdown_it",
            "markdown_it_py-{version}.dist-info/licenses/LICENSE": "licenses/markdown-it-py/LICENSE",
            "markdown_it_py-{version}.dist-info/licenses/LICENSE.markdown-it": "licenses/markdown-it-py/LICENSE.markdown-it",
        },
        "license_files": [
            "licenses/markdown-it-py/LICENSE",
            "licenses/markdown-it-py/LICENSE.markdown-it",
        ],
    },
    "mdit-py-plugins": {
        "canonical_name": "mdit-py-plugins",
        "display_name": "mdit-py-plugins",
        "import_roots": ["mdit_py_plugins"],
        "artifact_type": "wheel",
        "extraction_mapping": {
            "mdit_py_plugins": "mdit_py_plugins",
            "mdit_py_plugins-{version}.dist-info/licenses/LICENSE": "licenses/mdit-py-plugins/LICENSE",
        },
        "license_files": ["licenses/mdit-py-plugins/LICENSE"],
    },
    "mdurl": {
        "canonical_name": "mdurl",
        "display_name": "mdurl",
        "import_roots": ["mdurl"],
        "artifact_type": "wheel",
        "extraction_mapping": {
            "mdurl": "mdurl",
            "mdurl-{version}.dist-info/LICENSE": "licenses/mdurl/LICENSE",
        },
        "license_files": ["licenses/mdurl/LICENSE"],
    },
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def parse_requirements(req_path: Path) -> dict[str, str]:
    """Parse pinned requirements file into {canonical_name: version}."""
    if not req_path.is_file():
        raise FileNotFoundError(f"Requirements file not found at: {req_path}")
    requirements: dict[str, str] = {}
    for line in req_path.read_text(encoding="utf-8").splitlines():
        clean = line.strip()
        if not clean or clean.startswith("#"):
            continue
        if clean.startswith("-r "):
            nested = req_path.parent / clean[3:].strip()
            requirements.update(parse_requirements(nested))
            continue
        if "==" not in clean:
            raise ValueError(f"Requirement must be pinned with '==': {line}")
        parts = clean.split("==", 1)
        name = parts[0].strip().lower()
        version = parts[1].strip()
        requirements[name] = version
    return requirements


def validate_member_path(name: str) -> None:
    """Validate archive member path against path traversal, absolute paths, and reserved names."""
    norm = name.replace("\\", "/")
    if norm.startswith("/") or (len(norm) >= 2 and norm[1] == ":"):
        raise ValueError(f"Illegal absolute path in archive member: {name}")
    parts = [p for p in norm.split("/") if p]
    if ".." in parts:
        raise ValueError(f"Illegal path traversal ('..') in archive member: {name}")
    for part in parts:
        stem = part.upper().split(".")[0]
        if stem in WINDOWS_RESERVED_NAMES:
            raise ValueError(f"Illegal reserved device name in archive member: {name}")


def extract_static_package_version(init_file: Path) -> str | None:
    """Statically extract __version__ from a package's __init__.py using AST parsing without importing."""
    if not init_file.is_file():
        return None
    try:
        content = init_file.read_bytes()
        tree = ast.parse(content, filename=str(init_file))
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "__version__":
                        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                            return node.value.value
                        elif hasattr(ast, "Str") and isinstance(node.value, ast.Str):
                            return node.value.s
    except Exception:
        pass
    return None


def generate_third_party_notice(packages: list[dict[str, Any]]) -> str:
    """Generate deterministic THIRD_PARTY.md content with LF line endings."""
    lines: list[str] = [
        "# Third-Party Software Notices and Licenses",
        "",
        "This directory contains pure-Python third-party packages bundled with the `knowledge-base-manager` Skill.",
        "All bundled packages retain their original upstream source code, copyright notices, and license terms.",
        "",
        "## Bundled Packages",
        "",
    ]
    for pkg in sorted(packages, key=lambda x: x["canonical_name"]):
        disp = pkg.get("display_name") or pkg["canonical_name"]
        lines.append(f"### {disp}")
        lines.append(f"- Version: {pkg['version']}")
        if "upstream_url" in pkg:
            lines.append(f"- Upstream: {pkg['upstream_url']}")
        lines.append("- License: MIT License")
        lic_links = [f"[{lic}]({lic})" for lic in pkg.get("license_files", [])]
        if lic_links:
            lines.append(f"- License File{'s' if len(lic_links) > 1 else ''}: {', '.join(lic_links)}")
        lines.append(f"- Source Artifact: {pkg['artifact_filename']} (SHA-256: {pkg['artifact_sha256']})")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def extract_package(
    artifact_path: Path,
    pkg_meta: dict[str, Any],
    output_dir: Path,
    seen_destinations: dict[str, str],
    total_bytes_holder: list[int],
) -> list[dict[str, Any]]:
    """Extract files for a package according to mapping and safety limits."""
    art_data = artifact_path.read_bytes()
    canonical = pkg_meta["canonical_name"]
    version = pkg_meta["version"]
    raw_mapping = pkg_meta["extraction_mapping"]

    # Resolve version placeholders in mapping
    mapping: dict[str, str] = {}
    for src_pat, dst_pat in raw_mapping.items():
        mapping[src_pat.replace("{version}", version)] = dst_pat.replace("{version}", version)

    extracted_records: list[dict[str, Any]] = []

    if pkg_meta["artifact_type"] == "sdist":
        with tarfile.open(fileobj=io.BytesIO(art_data), mode="r:gz") as tar:
            for member in tar.getmembers():
                validate_member_path(member.name)
                if not member.isreg():
                    if member.issym() or member.islnk() or member.isfifo() or member.isdev() or member.ischr() or member.isblk():
                        raise ValueError(f"Illegal non-regular archive member in {canonical}: {member.name}")
                    continue
                if member.size > MAX_FILE_SIZE:
                    raise ValueError(f"Archive member exceeds size limit ({member.size} > {MAX_FILE_SIZE}): {member.name}")

                for src_prefix, dst_prefix in mapping.items():
                    if member.name == src_prefix:
                        rel_dest = dst_prefix
                    elif member.name.startswith(src_prefix + "/"):
                        sub = member.name[len(src_prefix) + 1:]
                        rel_dest = f"{dst_prefix}/{sub}"
                    else:
                        continue

                    rel_dest = rel_dest.replace("\\", "/")
                    dest_path = (output_dir / Path(rel_dest)).resolve()
                    if not dest_path.is_relative_to(output_dir.resolve()):
                        raise ValueError(f"Path traversal detected: {rel_dest} escapes destination directory")

                    dest_lower = rel_dest.lower()
                    if dest_lower in seen_destinations:
                        if seen_destinations[dest_lower] != rel_dest:
                            raise ValueError(f"Case collision during extraction: {rel_dest} vs {seen_destinations[dest_lower]}")
                        raise ValueError(f"Duplicate destination file during extraction: {rel_dest}")
                    seen_destinations[dest_lower] = rel_dest

                    content = tar.extractfile(member).read()
                    if len(content) > MAX_FILE_SIZE:
                        raise ValueError(f"Unpacked content exceeds size limit: {rel_dest}")
                    total_bytes_holder[0] += len(content)
                    if total_bytes_holder[0] > MAX_TOTAL_BYTES:
                        raise ValueError(f"Total extracted vendor bytes exceed limit ({total_bytes_holder[0]} > {MAX_TOTAL_BYTES})")

                    dest_file = output_dir / Path(rel_dest)
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    dest_file.write_bytes(content)

                    extracted_records.append({
                        "path": rel_dest,
                        "size": len(content),
                        "sha256": sha256_bytes(content),
                        "package": canonical,
                    })
                    break

    elif pkg_meta["artifact_type"] == "wheel":
        with zipfile.ZipFile(io.BytesIO(art_data)) as z:
            for zinfo in z.infolist():
                name = zinfo.filename
                validate_member_path(name)
                if zinfo.is_dir():
                    continue
                # Reject symlinks in wheel
                if (zinfo.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError(f"Illegal symlink in wheel {canonical}: {name}")
                if zinfo.file_size > MAX_FILE_SIZE:
                    raise ValueError(f"Wheel member exceeds size limit ({zinfo.file_size} > {MAX_FILE_SIZE}): {name}")

                for src_prefix, dst_prefix in mapping.items():
                    if name == src_prefix:
                        rel_dest = dst_prefix
                    elif name.startswith(src_prefix + "/"):
                        sub = name[len(src_prefix) + 1:]
                        rel_dest = f"{dst_prefix}/{sub}"
                    else:
                        continue

                    rel_dest = rel_dest.replace("\\", "/")
                    dest_path = (output_dir / Path(rel_dest)).resolve()
                    if not dest_path.is_relative_to(output_dir.resolve()):
                        raise ValueError(f"Path traversal detected: {rel_dest} escapes destination directory")

                    dest_lower = rel_dest.lower()
                    if dest_lower in seen_destinations:
                        if seen_destinations[dest_lower] != rel_dest:
                            raise ValueError(f"Case collision during extraction: {rel_dest} vs {seen_destinations[dest_lower]}")
                        raise ValueError(f"Duplicate destination file during extraction: {rel_dest}")
                    seen_destinations[dest_lower] = rel_dest

                    content = z.read(zinfo)
                    if len(content) > MAX_FILE_SIZE:
                        raise ValueError(f"Unpacked content exceeds size limit: {rel_dest}")
                    total_bytes_holder[0] += len(content)
                    if total_bytes_holder[0] > MAX_TOTAL_BYTES:
                        raise ValueError(f"Total extracted vendor bytes exceed limit ({total_bytes_holder[0]} > {MAX_TOTAL_BYTES})")

                    dest_file = output_dir / Path(rel_dest)
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    dest_file.write_bytes(content)

                    extracted_records.append({
                        "path": rel_dest,
                        "size": len(content),
                        "sha256": sha256_bytes(content),
                        "package": canonical,
                    })
                    break
    else:
        raise ValueError(f"Unsupported artifact type: {pkg_meta['artifact_type']}")

    return extracted_records


def query_pypi_release(package: str, version: str, artifact_type: str) -> dict[str, Any]:
    """Query PyPI API for the exact specified version and artifact type."""
    url = f"https://pypi.org/pypi/{package}/{version}/json"
    req = urllib.request.Request(url, headers={"User-Agent": "kb-vendor-tool/1.0"})
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    urls = data.get("urls", [])
    selected = None
    for r in urls:
        fn = r["filename"]
        pt = r["packagetype"]
        if artifact_type == "sdist" and pt == "sdist":
            selected = r
            break
        elif artifact_type == "wheel" and pt == "bdist_wheel" and fn.endswith("py3-none-any.whl"):
            selected = r
            break

    if not selected:
        raise RuntimeError(f"No suitable {artifact_type} found on PyPI for {package}=={version}")

    info = data.get("info", {})
    home_page = info.get("home_page") or info.get("project_urls", {}).get("Homepage") or info.get("project_url")

    return {
        "filename": selected["filename"],
        "url": selected["url"],
        "size": selected["size"],
        "sha256": selected["digests"]["sha256"],
        "upstream_url": home_page or f"https://pypi.org/project/{package}/",
    }


def validate_manifest_structure(manifest: Any, require_files: bool = False) -> tuple[bool, list[str]]:
    """Validate that manifest has valid JSON object structure, required schema, and required fields.

    Returns (True, []) on success, or (False, [error_messages]) on structural failure.
    """
    errors: list[str] = []
    if not isinstance(manifest, dict):
        return False, [f"Manifest root must be a JSON object, got {type(manifest).__name__}"]

    if manifest.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"Invalid or unsupported schema_version: expected {SCHEMA_VERSION}, got {manifest.get('schema_version')}")

    packages_list = manifest.get("packages")
    if not isinstance(packages_list, list):
        errors.append(f"'packages' must be a list, got {type(packages_list).__name__}")
        return False, errors

    if len(packages_list) == 0:
        errors.append("'packages' list must not be empty")

    seen_names: set[str] = set()
    for idx, pkg in enumerate(packages_list):
        if not isinstance(pkg, dict):
            errors.append(f"Package entry #{idx} must be a JSON object, got {type(pkg).__name__}")
            continue

        required_str_fields = [
            "canonical_name",
            "version",
            "artifact_filename",
            "artifact_url",
            "artifact_sha256",
            "artifact_type",
        ]
        for f in required_str_fields:
            val = pkg.get(f)
            if not isinstance(val, str) or not val.strip():
                errors.append(f"Package entry #{idx} missing or invalid string field '{f}'")

        roots = pkg.get("import_roots")
        if not isinstance(roots, list) or len(roots) == 0 or not all(isinstance(r, str) and r.strip() for r in roots):
            errors.append(f"Package entry #{idx} missing or invalid 'import_roots' (must be a non-empty list of strings)")

        mapping = pkg.get("extraction_mapping")
        if not isinstance(mapping, dict) or len(mapping) == 0 or not all(isinstance(k, str) and isinstance(v, str) for k, v in mapping.items()):
            errors.append(f"Package entry #{idx} missing or invalid 'extraction_mapping' (must be a non-empty dict of strings)")

        licenses = pkg.get("license_files")
        if not isinstance(licenses, list) or len(licenses) == 0 or not all(isinstance(l, str) and l.strip() for l in licenses):
            errors.append(f"Package entry #{idx} missing or invalid 'license_files' (must be a non-empty list of strings)")

        cname = pkg.get("canonical_name")
        if isinstance(cname, str) and cname.strip():
            cname_lower = cname.lower()
            if cname_lower in seen_names:
                errors.append(f"Duplicate package entry in manifest: '{cname_lower}'")
            seen_names.add(cname_lower)

    if require_files:
        files_list = manifest.get("files")
        if not isinstance(files_list, list):
            errors.append(f"'files' must be a list, got {type(files_list).__name__}")
        else:
            seen_paths: set[str] = set()
            for f_idx, f in enumerate(files_list):
                if not isinstance(f, dict):
                    errors.append(f"File entry #{f_idx} must be a JSON object, got {type(f).__name__}")
                    continue
                for f_field in ["path", "sha256", "package"]:
                    val = f.get(f_field)
                    if not isinstance(val, str) or not val.strip():
                        errors.append(f"File entry #{f_idx} missing or invalid string field '{f_field}'")
                size = f.get("size")
                if not isinstance(size, int) or size < 0:
                    errors.append(f"File entry #{f_idx} missing or invalid integer field 'size'")
                fpath = f.get("path")
                if isinstance(fpath, str):
                    if fpath in seen_paths:
                        errors.append(f"Duplicate file path in manifest 'files': '{fpath}'")
                    seen_paths.add(fpath)

    return len(errors) == 0, errors


def cmd_check(vendor_dir: Path, requirements_path: Path, manifest_path: Path) -> int:
    """Offline read-only check of vendor tree against requirements and manifest."""
    errors: list[str] = []

    if not requirements_path.is_file():
        print(f"[ERROR] Requirements file missing: {requirements_path}", file=sys.stderr)
        return 1

    try:
        reqs = parse_requirements(requirements_path)
    except Exception as e:
        print(f"[ERROR] Failed to parse requirements: {e}", file=sys.stderr)
        return 1

    if not vendor_dir.is_dir():
        print(f"[ERROR] Vendor directory missing: {vendor_dir}", file=sys.stderr)
        return 1

    if not manifest_path.is_file():
        print(f"[ERROR] Manifest file missing: {manifest_path}", file=sys.stderr)
        return 1

    try:
        manifest = json.loads(manifest_path.read_bytes().decode("utf-8"))
    except Exception as e:
        print(f"[ERROR] Malformed manifest JSON: {e}", file=sys.stderr)
        return 1

    valid, struct_errs = validate_manifest_structure(manifest, require_files=True)
    if not valid:
        print(f"[ERROR] Malformed manifest structure ({len(struct_errs)} error(s)):", file=sys.stderr)
        for err in struct_errs:
            print(f"  - {err}", file=sys.stderr)
        return 1

    packages_list = manifest["packages"]
    manifest_pkgs: dict[str, dict[str, Any]] = {}
    for p in packages_list:
        cname = str(p["canonical_name"]).lower()
        manifest_pkgs[cname] = p

    for req_name, req_ver in reqs.items():
        if req_name not in manifest_pkgs:
            errors.append(f"Required package '{req_name}' missing from vendor manifest")
        elif manifest_pkgs[req_name]["version"] != req_ver:
            errors.append(f"Version mismatch for '{req_name}': required {req_ver}, manifest has {manifest_pkgs[req_name]['version']}")

    for man_name, p in manifest_pkgs.items():
        if man_name not in reqs:
            errors.append(f"Extraneous package in manifest not in requirements: '{man_name}' ({p['version']})")

    # Static package version verification from source files on disk
    for man_name, p in manifest_pkgs.items():
        expected_ver = str(p.get("version"))
        roots = p.get("import_roots")
        if not isinstance(roots, list) or len(roots) == 0:
            errors.append(f"Package '{man_name}' has missing or empty 'import_roots' in manifest")
            continue

        # Determine primary canonical version root (yaml for pyyaml, roots[0] for others)
        primary_root = "yaml" if man_name == "pyyaml" and "yaml" in roots else roots[0]
        root_dir = vendor_dir / primary_root
        if not root_dir.is_dir():
            errors.append(f"Import root directory '{primary_root}' for package '{man_name}' does not exist in vendor directory")
            continue

        init_file = root_dir / "__init__.py"
        if not init_file.is_file():
            errors.append(f"Package entrypoint missing at '{primary_root}/__init__.py' for package '{man_name}'")
            continue

        static_ver = extract_static_package_version(init_file)
        if static_ver is None:
            errors.append(f"Unable to statically extract __version__ from '{primary_root}/__init__.py' for package '{man_name}'")
        elif static_ver != expected_ver:
            errors.append(
                f"Source code version mismatch for '{man_name}': manifest declared {expected_ver}, "
                f"static source in {primary_root}/__init__.py has {static_ver}"
            )

    # Check files in manifest
    files_list = manifest["files"]
    manifest_files: dict[str, dict[str, Any]] = {f["path"]: f for f in files_list}

    for rel_path, meta in manifest_files.items():
        full_path = vendor_dir / Path(rel_path)
        if not full_path.is_file():
            errors.append(f"Vendored file missing on disk: {rel_path}")
            continue
        st = full_path.stat()
        if st.st_size != meta["size"]:
            errors.append(f"File size mismatch for {rel_path}: expected {meta['size']}, on disk {st.st_size}")
        actual_hash = sha256_file(full_path)
        if actual_hash != meta["sha256"]:
            errors.append(f"Checksum mismatch for {rel_path}: expected {meta['sha256']}, on disk {actual_hash}")

    # Check files on disk
    for p in vendor_dir.rglob("*"):
        if not p.is_file():
            continue
        rel = str(p.relative_to(vendor_dir)).replace("\\", "/")
        if rel == "manifest.json":
            continue
        if p.suffix.lower() in FORBIDDEN_EXTENSIONS or "__pycache__" in p.parts:
            errors.append(f"Forbidden binary or bytecode file found in vendor: {rel}")
        if rel not in manifest_files:
            errors.append(f"Untracked file found in vendor directory: {rel}")

    # Verify THIRD_PARTY.md exists
    if "THIRD_PARTY.md" not in manifest_files:
        errors.append("THIRD_PARTY.md missing from manifest files list")

    if errors:
        print(f"[FAILED] Vendor check found {len(errors)} error(s):", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print(f"[PASS] Vendor check passed: {len(manifest_pkgs)} packages, {len(manifest_files)} files verified.")
    return 0


def cmd_fetch(manifest_path: Path, source_dir: Path) -> int:
    """Download locked upstream artifacts into source_dir and verify checksums."""
    if not manifest_path.is_file():
        print(f"[ERROR] Manifest file missing: {manifest_path}", file=sys.stderr)
        return 1

    try:
        manifest = json.loads(manifest_path.read_bytes().decode("utf-8"))
    except Exception as e:
        print(f"[ERROR] Failed to read manifest: {e}", file=sys.stderr)
        return 1

    valid, struct_errs = validate_manifest_structure(manifest, require_files=False)
    if not valid:
        print(f"[ERROR] Malformed manifest: {'; '.join(struct_errs)}", file=sys.stderr)
        return 1

    source_dir.mkdir(parents=True, exist_ok=True)

    for pkg in manifest.get("packages", []):
        filename = pkg["artifact_filename"]
        target_path = source_dir / filename
        expected_hash = pkg["artifact_sha256"]

        if target_path.is_file():
            actual_hash = sha256_file(target_path)
            if actual_hash == expected_hash:
                print(f"Reusing verified cached artifact: {filename}")
                continue
            else:
                print(f"[ERROR] Corrupted cached file {filename}: hash {actual_hash} != {expected_hash}", file=sys.stderr)
                return 1

        print(f"Downloading {filename} from {pkg['artifact_url']}...")
        req = urllib.request.Request(pkg["artifact_url"], headers={"User-Agent": "kb-vendor-tool/1.0"})
        data = urllib.request.urlopen(req).read()
        dl_hash = sha256_bytes(data)
        if dl_hash != expected_hash:
            print(f"[ERROR] Checksum mismatch for downloaded {filename}: {dl_hash} != {expected_hash}", file=sys.stderr)
            return 1
        target_path.write_bytes(data)

    print(f"[PASS] All artifacts successfully fetched/verified in {source_dir}.")
    return 0


def cmd_rebuild(manifest_path: Path, source_dir: Path, output_dir: Path) -> int:
    """Offline rebuild of vendor directory from cached artifacts according to manifest."""
    if output_dir.exists():
        print(f"[ERROR] Output directory '{output_dir}' already exists. Rebuild requires non-existent destination.", file=sys.stderr)
        return 1

    if not manifest_path.is_file():
        print(f"[ERROR] Manifest file missing: {manifest_path}", file=sys.stderr)
        return 1

    try:
        manifest = json.loads(manifest_path.read_bytes().decode("utf-8"))
    except Exception as e:
        print(f"[ERROR] Failed to read original manifest: {e}", file=sys.stderr)
        return 1

    valid, struct_errs = validate_manifest_structure(manifest, require_files=False)
    if not valid:
        print(f"[ERROR] Malformed original manifest: {'; '.join(struct_errs)}", file=sys.stderr)
        return 1

    packages = manifest.get("packages", [])

    # Verify all artifacts present and valid before touching output
    for pkg in packages:
        art_path = source_dir / pkg["artifact_filename"]
        if not art_path.is_file():
            print(f"[ERROR] Required cached artifact missing: {art_path}", file=sys.stderr)
            return 1
        h = sha256_file(art_path)
        if h != pkg["artifact_sha256"]:
            print(f"[ERROR] Cached artifact corrupted: {pkg['artifact_filename']} (hash {h} != {pkg['artifact_sha256']})", file=sys.stderr)
            return 1

    output_dir.mkdir(parents=True)
    seen_destinations: dict[str, str] = {}
    total_bytes = [0]
    all_extracted_files: list[dict[str, Any]] = []

    try:
        for pkg in packages:
            art_path = source_dir / pkg["artifact_filename"]
            recs = extract_package(art_path, pkg, output_dir, seen_destinations, total_bytes)
            all_extracted_files.extend(recs)

        # Write THIRD_PARTY.md
        tp_text = generate_third_party_notice(packages)
        tp_bytes = tp_text.encode("utf-8")
        tp_path = output_dir / "THIRD_PARTY.md"
        tp_path.write_bytes(tp_bytes)
        all_extracted_files.append({
            "path": "THIRD_PARTY.md",
            "size": len(tp_bytes),
            "sha256": sha256_bytes(tp_bytes),
            "package": "meta",
        })

        # Sort files list
        sorted_files = sorted(all_extracted_files, key=lambda x: x["path"])

        new_manifest = {
            "schema_version": SCHEMA_VERSION,
            "packages": sorted(packages, key=lambda x: x["canonical_name"]),
            "files": sorted_files,
        }

        # Validate against original manifest files
        orig_files = {f["path"]: (f["size"], f["sha256"]) for f in manifest.get("files", [])}
        new_files = {f["path"]: (f["size"], f["sha256"]) for f in sorted_files}
        if orig_files != new_files:
            print("[ERROR] Rebuilt files do not match manifest file records exactly.", file=sys.stderr)
            shutil.rmtree(output_dir)
            return 1

        manifest_text = json.dumps(new_manifest, indent=2, ensure_ascii=False) + "\n"
        (output_dir / "manifest.json").write_bytes(manifest_text.encode("utf-8"))

    except Exception as e:
        print(f"[ERROR] Rebuild failed: {e}", file=sys.stderr)
        shutil.rmtree(output_dir, ignore_errors=True)
        return 1

    print(f"[PASS] Rebuilt vendor directory at {output_dir}: {len(sorted_files)} files, {sum(f['size'] for f in sorted_files)} bytes.")
    return 0


def cmd_refresh(requirements_path: Path, source_dir: Path, output_dir: Path) -> int:
    """Query PyPI for required packages, fetch artifacts, and generate vendor tree."""
    if output_dir.exists():
        print(f"[ERROR] Output directory '{output_dir}' already exists. Refresh requires non-existent destination.", file=sys.stderr)
        return 1

    reqs = parse_requirements(requirements_path)
    source_dir.mkdir(parents=True, exist_ok=True)

    packages_spec: list[dict[str, Any]] = []

    for name, version in reqs.items():
        base_spec = DEFAULT_KNOWN_PACKAGES.get(name)
        if not base_spec:
            print(f"[ERROR] Unknown package not in default spec: {name}", file=sys.stderr)
            return 1

        art_type = base_spec["artifact_type"]
        print(f"Querying PyPI for {name}=={version} ({art_type})...")
        pypi_info = query_pypi_release(name, version, art_type)

        spec = {
            "canonical_name": name,
            "display_name": base_spec.get("display_name", name),
            "version": version,
            "import_roots": base_spec["import_roots"],
            "artifact_filename": pypi_info["filename"],
            "artifact_url": pypi_info["url"],
            "artifact_bytes": pypi_info["size"],
            "artifact_sha256": pypi_info["sha256"],
            "artifact_type": art_type,
            "upstream_url": pypi_info["upstream_url"],
            "extraction_mapping": base_spec["extraction_mapping"],
            "license_files": base_spec["license_files"],
        }
        packages_spec.append(spec)

        # Download if needed
        cached_file = source_dir / pypi_info["filename"]
        if cached_file.is_file():
            h = sha256_file(cached_file)
            if h == pypi_info["sha256"]:
                print(f"Reusing cached artifact: {pypi_info['filename']}")
                continue

        print(f"Downloading {pypi_info['filename']}...")
        req = urllib.request.Request(pypi_info["url"], headers={"User-Agent": "kb-vendor-tool/1.0"})
        content = urllib.request.urlopen(req).read()
        h = sha256_bytes(content)
        if h != pypi_info["sha256"]:
            print(f"[ERROR] Downloaded hash mismatch for {pypi_info['filename']}", file=sys.stderr)
            return 1
        cached_file.write_bytes(content)

    output_dir.mkdir(parents=True)
    seen_destinations: dict[str, str] = {}
    total_bytes = [0]
    all_extracted_files: list[dict[str, Any]] = []

    try:
        for pkg in packages_spec:
            art_path = source_dir / pkg["artifact_filename"]
            recs = extract_package(art_path, pkg, output_dir, seen_destinations, total_bytes)
            all_extracted_files.extend(recs)

        # Write THIRD_PARTY.md
        tp_text = generate_third_party_notice(packages_spec)
        tp_bytes = tp_text.encode("utf-8")
        tp_path = output_dir / "THIRD_PARTY.md"
        tp_path.write_bytes(tp_bytes)
        all_extracted_files.append({
            "path": "THIRD_PARTY.md",
            "size": len(tp_bytes),
            "sha256": sha256_bytes(tp_bytes),
            "package": "meta",
        })

        sorted_files = sorted(all_extracted_files, key=lambda x: x["path"])

        manifest = {
            "schema_version": SCHEMA_VERSION,
            "packages": sorted(packages_spec, key=lambda x: x["canonical_name"]),
            "files": sorted_files,
        }

        manifest_text = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
        (output_dir / "manifest.json").write_bytes(manifest_text.encode("utf-8"))

    except Exception as e:
        print(f"[ERROR] Refresh generation failed: {e}", file=sys.stderr)
        shutil.rmtree(output_dir, ignore_errors=True)
        return 1

    print(f"[PASS] Refresh completed at {output_dir}: {len(sorted_files)} files, {sum(f['size'] for f in sorted_files)} bytes.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Vendor dependency management for knowledge-base-manager")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="Verify vendored files on disk against requirements and manifest")
    group.add_argument("--fetch", action="store_true", help="Fetch locked upstream artifacts into source cache")
    group.add_argument("--rebuild", action="store_true", help="Rebuild vendor directory from locked cached artifacts")
    group.add_argument("--refresh", action="store_true", help="Query PyPI, fetch artifacts, and generate vendor candidate tree")

    repo_root = Path(__file__).resolve().parent.parent
    default_skill_dir = repo_root / "knowledge-base-manager"

    parser.add_argument("--skill-dir", type=Path, default=default_skill_dir, help="Knowledge base manager Skill directory")
    parser.add_argument("--vendor-dir", type=Path, default=None, help="Vendor directory (defaults to <skill-dir>/vendor)")
    parser.add_argument("--requirements", type=Path, default=None, help="Path to requirements.txt (defaults to <skill-dir>/requirements.txt)")
    parser.add_argument("--manifest", type=Path, default=None, help="Path to manifest.json (defaults to <vendor-dir>/manifest.json)")
    parser.add_argument("--source-dir", type=Path, default=None, help="Directory for cached artifacts")
    parser.add_argument("--output", type=Path, default=None, help="Output directory for generated vendor tree")

    args = parser.parse_args(argv)

    skill_dir = args.skill_dir.resolve()
    vendor_dir = (args.vendor_dir or (skill_dir / "vendor")).resolve()
    req_path = (args.requirements or (skill_dir / "requirements.txt")).resolve()
    manifest_path = (args.manifest or (vendor_dir / "manifest.json")).resolve()

    if args.check:
        return cmd_check(vendor_dir=vendor_dir, requirements_path=req_path, manifest_path=manifest_path)

    if args.fetch:
        if not args.source_dir:
            print("[ERROR] --source-dir is required for --fetch", file=sys.stderr)
            return 2
        return cmd_fetch(manifest_path=manifest_path, source_dir=args.source_dir.resolve())

    if args.rebuild:
        if not args.source_dir or not args.output:
            print("[ERROR] --source-dir and --output are required for --rebuild", file=sys.stderr)
            return 2
        return cmd_rebuild(manifest_path=manifest_path, source_dir=args.source_dir.resolve(), output_dir=args.output.resolve())

    if args.refresh:
        if not args.source_dir or not args.output:
            print("[ERROR] --source-dir and --output are required for --refresh", file=sys.stderr)
            return 2
        return cmd_refresh(requirements_path=req_path, source_dir=args.source_dir.resolve(), output_dir=args.output.resolve())

    return 0


if __name__ == "__main__":
    sys.exit(main())
