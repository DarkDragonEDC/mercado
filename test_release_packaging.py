import tempfile
import unittest
from pathlib import Path

from release_packaging import (
    ReleasePackagingError,
    stage_certified_preset_assets,
    validate_packaged_presets,
)


class CertifiedPresetPackagingTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parent
        self.presets = self.root / "presets"

    def test_staging_copies_every_certified_template_in_its_declared_path(self):
        with tempfile.TemporaryDirectory() as directory:
            package_root = Path(directory)
            destination = package_root / "assets"

            copied = stage_certified_preset_assets(
                self.root, self.presets, destination
            )

            self.assertEqual(7, len(copied))
            expected = (
                destination
                / "albion-1920x1080-dpi96-ptbr-buy-v1"
                / "pedido_usuario.png"
            )
            self.assertTrue(expected.is_file())
            self.assertEqual(
                ("albion-1920x1080-dpi96-ptbr-buy-v1",),
                validate_packaged_presets(
                    self.presets, asset_root=package_root
                ),
            )

    def test_artifact_validation_fails_when_one_template_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            package_root = Path(directory)
            destination = package_root / "assets"
            stage_certified_preset_assets(self.root, self.presets, destination)
            (
                destination
                / "albion-1920x1080-dpi96-ptbr-buy-v1"
                / "fechar.png"
            ).unlink()

            with self.assertRaisesRegex(ReleasePackagingError, "Template ausente"):
                validate_packaged_presets(self.presets, asset_root=package_root)

    def test_build_validates_staging_and_compiled_app(self):
        script = (self.root / "build_release.ps1").read_text(encoding="utf-8")
        self.assertIn('release_packaging.py") stage', script)
        self.assertIn('release_packaging.py") validate', script)
        self.assertIn('--asset-root $CompiledApp', script)


if __name__ == "__main__":
    unittest.main()
