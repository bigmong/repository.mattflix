#!/usr/bin/env python3
"""Scans every top-level addon folder in this repo -- the local repository.mattflixhelper
meta-addon plus any other addon repos checked out alongside it (e.g. plugin.video.mattflixhelper,
fetched fresh by update_repo.yml on each rebuild) -- and rebuilds repo_output/: one zip + a
copy of addon.xml per addon, plus a combined addons.xml and addons.xml.md5. Run from the
repo root, after checking out each addon's source into its own top-level folder:

    python3 repo_generator.py

Adding a new addon later just means checking out its source into another top-level folder
(one more `actions/checkout` step in the workflow) -- this script picks it up automatically,
no changes needed here.
"""
from __future__ import annotations

import hashlib
import shutil
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "repo_output"

IGNORE_NAMES = {
    ".git", ".gitea", ".github", ".gitignore", ".gitmodules",
    ".DS_Store", "thumbs.db", ".idea", "venv", "repo_output", "__pycache__",
}


def find_addon_dirs() -> list[Path]:
    return sorted(
        p for p in ROOT.iterdir()
        if p.is_dir() and p.name not in IGNORE_NAMES and (p / "addon.xml").exists()
    )


def read_addon_id_version(addon_xml_path: Path) -> tuple[str, str]:
    root = ET.parse(addon_xml_path).getroot()
    return root.attrib["id"], root.attrib["version"]


def build_addon_zip(addon_dir: Path, addon_id: str, version: str) -> Path:
    """Zips every file under addon_dir (minus IGNORE_NAMES) into
    repo_output/<addon_id>/<addon_id>-<version>.zip, with every entry rooted at
    "<addon_id>/..." -- required by Kodi: extracting the zip must produce a folder named
    exactly like the addon id.
    """
    addon_out_dir = OUTPUT_DIR / addon_id
    addon_out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = addon_out_dir / f"{addon_id}-{version}.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in sorted(addon_dir.rglob("*")):
            if not file.is_file():
                continue
            if any(part in IGNORE_NAMES for part in file.relative_to(addon_dir).parts):
                continue
            rel = file.relative_to(addon_dir)
            zf.write(file, arcname=f"{addon_id}/{rel.as_posix()}")

    # Standard Kodi repo convention: a plain copy of addon.xml (+ icon/fanart) sits next
    # to the zip, used for browsing/changelog display before install.
    shutil.copy2(addon_dir / "addon.xml", addon_out_dir / "addon.xml")
    for extra in ("icon.png", "fanart.jpg", "changelog.txt"):
        p = addon_dir / extra
        if p.exists():
            shutil.copy2(p, addon_out_dir / extra)

    return zip_path


def build_addons_xml(addon_xml_paths: list[Path]) -> Path:
    lines = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>', "<addons>"]
    for p in addon_xml_paths:
        content_lines = [
            ln for ln in p.read_text(encoding="utf-8").splitlines() if not ln.strip().startswith("<?xml")
        ]
        lines.extend(content_lines)
    lines.append("</addons>")

    addons_xml_path = OUTPUT_DIR / "addons.xml"
    addons_xml_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return addons_xml_path


def build_checksum(addons_xml_path: Path) -> Path:
    md5 = hashlib.md5(addons_xml_path.read_bytes()).hexdigest()
    checksum_path = addons_xml_path.parent / "addons.xml.md5"
    checksum_path.write_text(md5, encoding="utf-8")
    return checksum_path


def main() -> None:
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True)

    addon_dirs = find_addon_dirs()
    if not addon_dirs:
        raise SystemExit("No addon folders with an addon.xml found -- nothing to build.")

    addon_xml_paths = []
    for addon_dir in addon_dirs:
        addon_id, version = read_addon_id_version(addon_dir / "addon.xml")
        print(f"Building {addon_id} v{version} (from {addon_dir.name}/)")
        zip_path = build_addon_zip(addon_dir, addon_id, version)
        print(f"  -> {zip_path.relative_to(ROOT)}")
        addon_xml_paths.append(OUTPUT_DIR / addon_id / "addon.xml")

    addons_xml_path = build_addons_xml(addon_xml_paths)
    checksum_path = build_checksum(addons_xml_path)
    print(f"  -> {addons_xml_path.relative_to(ROOT)}")
    print(f"  -> {checksum_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
