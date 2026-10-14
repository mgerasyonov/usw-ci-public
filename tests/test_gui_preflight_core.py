import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from gui_preflight_core import GuiPreflightError, validate_overlay


class GuiPreflightCoreTests(unittest.TestCase):
    def make_fixture(self):
        root = Path(tempfile.mkdtemp())
        product = root / "product"
        overlay = product / "overlay"
        overlay.mkdir(parents=True)

        uidesc = overlay / "gui.uidesc"
        uidesc.write_text('<root><control control-tag="gain"/></root>', encoding="utf-8")

        export = {
            "schema": 1,
            "dimensions": {
                "width": 1280, "height": 720,
                "min_width": 960, "min_height": 540,
                "max_width": 1600, "max_height": 900
            },
            "parameters": [{"control_tag": "gain", "param_id": 100}],
            "runtime_features": ["uidesc", "parameter_binding"],
            "assets": []
        }
        export_path = overlay / "export.json"
        export_path.write_text(json.dumps(export), encoding="utf-8")

        rows = []
        for name in ("gui.uidesc", "export.json"):
            p = overlay / name
            rows.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {name}")
        (overlay / "MANIFEST.sha256").write_text("\n".join(rows) + "\n", encoding="utf-8")

        contract = {
            "schema": 1,
            "runtime_id": "GENERIC_RUNTIME",
            "product_root": "product",
            "overlay_root": "overlay",
            "uidesc": "gui.uidesc",
            "export_contract": "export.json",
            "manifest": "MANIFEST.sha256"
        }
        baseline = {
            "schema": 1,
            "dimensions": {
                "width": 1280, "height": 720,
                "min_width": 800, "min_height": 450,
                "max_width": 1920, "max_height": 1080
            },
            "allowed_parameter_ids": [100, 101],
            "required_gui_parameter_ids": [100]
        }
        binding = {
            "schema": 1,
            "status": "QUALIFIED_CURRENT",
            "runtime_id": "GENERIC_RUNTIME",
            "supported_features": ["uidesc", "parameter_binding"]
        }
        return root, contract, baseline, binding, export_path

    def test_synthetic_overlay_passes(self):
        root, contract, baseline, binding, _ = self.make_fixture()
        out = validate_overlay(contract, baseline, binding, root)
        self.assertEqual(out["status"], "PASS")
        self.assertTrue(out["private_native_gate_still_required_for_release"])

    def test_new_parameter_fails_closed(self):
        root, contract, baseline, binding, export_path = self.make_fixture()
        export = json.loads(export_path.read_text(encoding="utf-8"))
        export["parameters"][0]["param_id"] = 999
        export_path.write_text(json.dumps(export), encoding="utf-8")
        overlay = root / "product" / "overlay"
        rows = []
        for name in ("gui.uidesc", "export.json"):
            p = overlay / name
            rows.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {name}")
        (overlay / "MANIFEST.sha256").write_text("\n".join(rows) + "\n", encoding="utf-8")

        with self.assertRaises(GuiPreflightError):
            validate_overlay(contract, baseline, binding, root)

    def test_unsupported_runtime_feature_fails_closed(self):
        root, contract, baseline, binding, export_path = self.make_fixture()
        export = json.loads(export_path.read_text(encoding="utf-8"))
        export["runtime_features"].append("unsupported_feature")
        export_path.write_text(json.dumps(export), encoding="utf-8")
        overlay = root / "product" / "overlay"
        rows = []
        for name in ("gui.uidesc", "export.json"):
            p = overlay / name
            rows.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {name}")
        (overlay / "MANIFEST.sha256").write_text("\n".join(rows) + "\n", encoding="utf-8")

        with self.assertRaises(GuiPreflightError):
            validate_overlay(contract, baseline, binding, root)


if __name__ == "__main__":
    unittest.main()
