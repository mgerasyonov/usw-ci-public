from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import xml.etree.ElementTree as ET

ALLOWED_SUFFIXES = {".uidesc", ".png", ".jpg", ".jpeg", ".bmp", ".svg", ".json", ".sha256"}
ASSET_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".svg"}
FORBIDDEN_SUFFIXES = {".cpp", ".c", ".cc", ".cxx", ".h", ".hpp", ".hh", ".inl", ".cmake", ".cmd", ".ps1", ".bat", ".dll", ".exe", ".lib"}


class GuiPreflightError(RuntimeError):
    pass


def need(condition: bool, message: str) -> None:
    if not condition:
        raise GuiPreflightError(message)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_rel(value: str, label: str, allow_dot: bool = False) -> Path:
    need(isinstance(value, str) and value.strip(), f"{label}_MISSING")
    p = Path(value)
    need(not p.is_absolute(), f"{label}_MUST_BE_RELATIVE")
    need(".." not in p.parts, f"{label}_ESCAPES_ROOT")
    if not allow_dot:
        need(value not in {".", "./"}, f"{label}_MUST_NAME_CHILD")
    return p


def contained(root: Path, path: Path, label: str) -> None:
    need(os.path.commonpath([str(root), str(path)]) == str(root), f"{label}_ESCAPES_ROOT")


def parse_manifest(path: Path) -> dict[str, str]:
    rows: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        parts = raw.split("  ", 1)
        need(len(parts) == 2, f"MANIFEST_LINE_INVALID:{raw}")
        digest, rel = parts[0].strip().lower(), parts[1].strip().replace("\\", "/")
        need(len(digest) == 64 and all(c in "0123456789abcdef" for c in digest), f"MANIFEST_HASH_INVALID:{rel}")
        need(rel and not rel.startswith("/") and ".." not in Path(rel).parts, f"MANIFEST_PATH_INVALID:{rel}")
        need(rel not in rows, f"MANIFEST_DUPLICATE:{rel}")
        rows[rel] = digest
    return rows


def validate_overlay(contract: dict, baseline: dict, binding: dict, base_dir: Path) -> dict:
    need(contract.get("schema") == 1, "CONTRACT_SCHEMA_UNSUPPORTED")
    need(baseline.get("schema") == 1, "BASELINE_SCHEMA_UNSUPPORTED")
    need(binding.get("schema") == 1, "BINDING_SCHEMA_UNSUPPORTED")
    need(binding.get("status") == "QUALIFIED_CURRENT", "RUNTIME_NOT_QUALIFIED")
    need(contract.get("runtime_id") == binding.get("runtime_id"), "RUNTIME_ID_MISMATCH")

    product_root = (base_dir / safe_rel(contract.get("product_root", "."), "PRODUCT_ROOT", allow_dot=True)).resolve()
    overlay = (product_root / safe_rel(contract["overlay_root"], "OVERLAY_ROOT")).resolve()
    contained(base_dir.resolve(), product_root, "PRODUCT_ROOT")
    contained(product_root, overlay, "OVERLAY_ROOT")
    need(product_root.is_dir(), "PRODUCT_ROOT_MISSING")
    need(overlay.is_dir(), "OVERLAY_ROOT_MISSING")

    files = sorted(p for p in overlay.rglob("*") if p.is_file())
    need(files, "OVERLAY_EMPTY")
    rel_files = [p.relative_to(overlay).as_posix() for p in files]

    for p, rel in zip(files, rel_files):
        need(p.suffix.lower() not in FORBIDDEN_SUFFIXES, f"NATIVE_FILE_FORBIDDEN:{rel}")
        need(p.suffix.lower() in ALLOWED_SUFFIXES, f"OVERLAY_FILE_TYPE_FORBIDDEN:{rel}")

    manifest_rel = safe_rel(contract["manifest"], "MANIFEST")
    manifest_path = overlay / manifest_rel
    need(manifest_path.is_file(), "MANIFEST_MISSING")
    manifest = parse_manifest(manifest_path)
    payload = [r for r in rel_files if r != manifest_rel.as_posix()]
    need(set(manifest) == set(payload), "MANIFEST_COVERAGE_MISMATCH")
    for rel, digest in manifest.items():
        need(sha256_file(overlay / rel) == digest, f"MANIFEST_HASH_MISMATCH:{rel}")

    uidesc_rel = safe_rel(contract["uidesc"], "UIDESC")
    export_rel = safe_rel(contract["export_contract"], "EXPORT_CONTRACT")
    uidesc = overlay / uidesc_rel
    export_path = overlay / export_rel
    need(uidesc.is_file(), "UIDESC_MISSING")
    need(export_path.is_file(), "EXPORT_MISSING")

    tree = ET.parse(uidesc)
    export = json.loads(export_path.read_text(encoding="utf-8"))

    dims = export.get("dimensions") or {}
    bounds = baseline.get("dimensions") or {}
    for key in ("width", "height", "min_width", "min_height", "max_width", "max_height"):
        need(isinstance(dims.get(key), int) and dims[key] > 0, f"DIMENSION_INVALID:{key}")
        need(isinstance(bounds.get(key), int) and bounds[key] > 0, f"BASELINE_DIMENSION_INVALID:{key}")
    need(bounds["min_width"] <= dims["width"] <= bounds["max_width"], "WIDTH_OUTSIDE_BASELINE")
    need(bounds["min_height"] <= dims["height"] <= bounds["max_height"], "HEIGHT_OUTSIDE_BASELINE")

    allowed_ids = baseline.get("allowed_parameter_ids") or []
    required_ids = baseline.get("required_gui_parameter_ids") or []
    need(len(allowed_ids) == len(set(allowed_ids)), "BASELINE_PARAMETER_IDS_DUPLICATE")
    need(set(required_ids).issubset(set(allowed_ids)), "BASELINE_REQUIRED_IDS_NOT_ALLOWED")

    controls = export.get("parameters") or []
    tags, used_ids = set(), set()
    for item in controls:
        tag, pid = item.get("control_tag"), item.get("param_id")
        need(isinstance(tag, str) and tag, "CONTROL_TAG_INVALID")
        need(isinstance(pid, int), f"CONTROL_PARAM_ID_INVALID:{tag}")
        need(tag not in tags, f"CONTROL_TAG_DUPLICATE:{tag}")
        need(pid not in used_ids, f"CONTROL_PARAM_ID_DUPLICATE:{pid}")
        need(pid in allowed_ids, f"NEW_PARAMETER_ID_REQUIRES_PRIVATE_NATIVE_GATE:{pid}")
        tags.add(tag)
        used_ids.add(pid)
    need(set(required_ids).issubset(used_ids), "REQUIRED_GUI_PARAMETER_MISSING")

    uidesc_tags = {
        v
        for elem in tree.getroot().iter()
        for k, v in elem.attrib.items()
        if k in {"control-tag", "control_tag"}
    }
    need(tags.issubset(uidesc_tags), "EXPORT_CONTROL_TAG_NOT_IN_UIDESC")

    features = export.get("runtime_features") or []
    supported = set(binding.get("supported_features") or [])
    missing_features = sorted(set(features) - supported)
    need(not missing_features, "UNSUPPORTED_RUNTIME_FEATURE:" + ",".join(missing_features))

    assets = export.get("assets") or []
    for asset in assets:
        rel = safe_rel(asset, "ASSET")
        need(rel.suffix.lower() in ASSET_SUFFIXES, f"ASSET_TYPE_FORBIDDEN:{asset}")
        need((overlay / rel).is_file(), f"ASSET_MISSING:{asset}")

    return {
        "status": "PASS",
        "overlay_files_verified": len(files),
        "manifest_entries_verified": len(manifest),
        "parameter_bindings_verified": len(controls),
        "runtime_features_verified": sorted(features),
        "private_native_gate_still_required_for_release": True,
    }
