#!/usr/bin/env python3
"""Generates a Kodi-installable repository structure for each Kodi-version folder that
exists at the repo root (KODI_VERSIONS below). 
Existing zips are never rebuilt or removed, only new/changed addon versions get a fresh
zip, and addons.xml/addons.xml.md5 are updated in place. Run from the repo root, after
updating submodules:

    git submodule update --init --recursive --remote
    python3 repo_generator.py

Layout:
    repo/                 -- version-agnostic: the repository.mattflixhelper meta-addon
                              itself, plus any addon with no Kodi-version constraints
    omega/                -- addons built for Kodi Omega (20.9.1+), e.g.
                              plugin.video.mattflix.helper as a git submodule

Adding a Kodi-version folder later (e.g. "piers") is just: add it to KODI_VERSIONS below,
`git submodule add <url> piers/<addon-id>`, and add a matching <dir minversion="..."> block
to repo/repository.mattflixhelper/addon.xml.
"""
from __future__ import annotations

import hashlib
import shutil
import zipfile
from pathlib import Path
from xml.etree import ElementTree

KODI_VERSIONS = ["repo", "omega"]
IGNORE = {".git", ".gitea", ".github", ".gitignore", ".gitmodules", ".DS_Store", "thumbs.db", ".idea", "venv"}

ROOT = Path(__file__).resolve().parent


def _create_zip(release_path: Path, zips_path: Path, addon_id: str, version: str) -> None:
    """Zips release_path/addon_id into zips_path/addon_id/<addon_id>-<version>.zip, with
    every entry rooted at "<addon_id>/..." -- required by Kodi. Skipped if that exact
    version's zip already exists, so older versions are never rebuilt or lost.
    """
    addon_folder = release_path / addon_id
    zip_folder = zips_path / addon_id
    zip_folder.mkdir(parents=True, exist_ok=True)

    final_zip = zip_folder / f"{addon_id}-{version}.zip"
    if final_zip.exists():
        return

    with zipfile.ZipFile(final_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in sorted(addon_folder.rglob("*")):
            if not file.is_file():
                continue
            if any(part in IGNORE or part == "__pycache__" for part in file.relative_to(addon_folder).parts):
                continue
            zf.write(file, arcname=f"{addon_id}/{file.relative_to(addon_folder).as_posix()}")

    print(f"Zip created for {addon_id} ({version})")


def _copy_meta_files(release_path: Path, zips_path: Path, addon_id: str) -> None:
    """Copies addon.xml plus any asset files it references (icon, fanart, etc.) next to
    the zip -- standard Kodi repo convention, used for browsing/changelog before install.
    """
    addon_folder = release_path / addon_id
    tree = ElementTree.parse(addon_folder / "addon.xml")
    copy_files = ["addon.xml"]
    for ext in tree.getroot().findall("extension"):
        if ext.get("point") not in ("xbmc.addon.metadata", "kodi.addon.metadata"):
            continue
        assets = ext.find("assets")
        if assets is None:
            continue
        copy_files.extend(asset.text for asset in assets if asset.text)

    dest_folder = zips_path / addon_id
    for name in copy_files:
        src = addon_folder / name
        if not src.exists():
            continue
        dest = dest_folder / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)


def _remove_binaries(release_path: Path) -> None:
    for pyc in release_path.rglob("*.pyc"):
        pyc.unlink(missing_ok=True)
    for pycache in release_path.rglob("__pycache__"):
        shutil.rmtree(pycache, ignore_errors=True)


def _addon_dirs(release_path: Path) -> list[Path]:
    return sorted(
        p for p in release_path.iterdir()
        if p.is_dir() and p.name not in ("zips", *IGNORE) and not p.name.startswith(".") and (p / "addon.xml").exists()
    )


def generate(release_path: Path) -> None:
    zips_path = release_path / "zips"
    addons_xml_path = zips_path / "addons.xml"
    md5_path = zips_path / "addons.xml.md5"
    zips_path.mkdir(parents=True, exist_ok=True)

    _remove_binaries(release_path)

    if addons_xml_path.exists():
        addons_tree = ElementTree.parse(addons_xml_path)
        addons_root = addons_tree.getroot()
    else:
        addons_root = ElementTree.Element("addons")
        addons_tree = ElementTree.ElementTree(addons_root)

    changed = False
    for addon_dir in _addon_dirs(release_path):
        try:
            addon_root = ElementTree.parse(addon_dir / "addon.xml").getroot()
        except ElementTree.ParseError as e:
            print(f"Excluding {addon_dir.name}: {e}")
            continue

        addon_id = addon_root.get("id")
        version = addon_root.get("version")

        existing = addons_root.find(f"addon[@id='{addon_id}']")
        if existing is not None and existing.get("version") == version:
            continue  # already up to date, nothing to do for this addon

        if existing is not None:
            index = list(addons_root).index(existing)
            addons_root.remove(existing)
            addons_root.insert(index, addon_root)
        else:
            addons_root.append(addon_root)
        changed = True

        _create_zip(release_path, zips_path, addon_id, version)
        _copy_meta_files(release_path, zips_path, addon_id)
        print(f"  {release_path.name}: {addon_id} -> v{version}")

    if not changed:
        print(f"{release_path.name}: nothing changed")
        return

    addons_root[:] = sorted(addons_root, key=lambda a: a.get("id"))
    addons_tree.write(addons_xml_path, encoding="utf-8", xml_declaration=True)

    md5 = hashlib.md5(addons_xml_path.read_bytes()).hexdigest()
    md5_path.write_text(md5, encoding="utf-8")
    print(f"  -> {addons_xml_path.relative_to(ROOT)}")
    print(f"  -> {md5_path.relative_to(ROOT)}")


def main() -> None:
    for version in KODI_VERSIONS:
        release_path = ROOT / version
        if not release_path.exists():
            continue
        print(f"== {version} ==")
        generate(release_path)


if __name__ == "__main__":
    main()
