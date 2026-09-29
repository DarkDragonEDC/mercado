import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import dependency_manager


class DependencyManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.requirements = self.directory / "requirements.txt"
        self.marker = self.directory / ".mkt_dependencies.ok"
        self.requirements.write_text("alpha==1.2.3\nbeta==4.5.6\n", encoding="utf-8")
        self.req_patch = patch.object(dependency_manager, "REQUIREMENTS_FILE", self.requirements)
        self.marker_patch = patch.object(dependency_manager, "MARKER_FILE", self.marker)
        self.req_patch.start()
        self.marker_patch.start()
        self.addCleanup(self.req_patch.stop)
        self.addCleanup(self.marker_patch.stop)

    @staticmethod
    def fake_version(name):
        return {"alpha": "1.2.3", "beta": "4.5.6"}[name]

    def test_valid_marker_skips_reinstallation(self):
        self.marker.write_text(json.dumps({
            "requirements_sha256": dependency_manager.requirements_hash(),
            "python": f"{dependency_manager.sys.version_info.major}.{dependency_manager.sys.version_info.minor}",
        }), encoding="utf-8")
        with patch.object(dependency_manager.importlib.metadata, "version", self.fake_version):
            valid, _ = dependency_manager.marker_is_valid()
        self.assertTrue(valid)

    def test_requirements_change_invalidates_marker(self):
        self.marker.write_text(json.dumps({
            "requirements_sha256": dependency_manager.requirements_hash(),
            "python": f"{dependency_manager.sys.version_info.major}.{dependency_manager.sys.version_info.minor}",
        }), encoding="utf-8")
        self.requirements.write_text("alpha==9.9.9\n", encoding="utf-8")
        valid, reason = dependency_manager.marker_is_valid()
        self.assertFalse(valid)
        self.assertIn("alterado", reason)

    def test_first_verification_creates_marker(self):
        import_names = {"alpha": "alpha", "beta": "beta"}
        with (
            patch.object(dependency_manager, "IMPORT_NAMES", import_names),
            patch.object(dependency_manager.importlib.metadata, "version", self.fake_version),
            patch.object(dependency_manager.importlib, "import_module"),
        ):
            valid, _ = dependency_manager.verify_imports_and_mark()
        self.assertTrue(valid)
        self.assertTrue(self.marker.exists())


class DependencyManifestTests(unittest.TestCase):
    def test_map_and_data_packages_are_not_required(self):
        requirements = (Path(__file__).resolve().parent / "requirements.txt").read_text(
            encoding="utf-8"
        ).lower()
        for package in ("scipy", "shapely", "scikit-image", "pandas"):
            self.assertNotIn(package, requirements)
        for package in ("scipy", "shapely"):
            self.assertNotIn(package, dependency_manager.IMPORT_NAMES)


if __name__ == "__main__":
    unittest.main()
