import hashlib
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from unittest.mock import MagicMock

import app_paths
import update_client
from coordinate_system import load_settings, save_settings
from update_manager import (
    is_update_available,
    parse_manifest,
    verify_package,
    version_tuple,
)
from updater import UpdateError, apply_update, extract_payload


class PersistentPathTests(unittest.TestCase):
    def test_legacy_settings_are_copied_without_removing_source(self):
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as data_dir:
            source = Path(source_dir)
            legacy = source / "offsets.json"
            legacy.write_text('{"lucro": 25}', encoding="utf-8")
            with patch.dict(os.environ, {app_paths.DATA_DIR_ENV: data_dir}):
                migrated = app_paths.migrate_legacy_state(source)
                target = Path(data_dir) / "offsets.json"
                self.assertEqual(target.read_text(encoding="utf-8"), '{"lucro": 25}')
                self.assertEqual(migrated["offsets.json"].resolve(), target.resolve())
            self.assertTrue(legacy.exists())

    def test_existing_user_settings_are_never_overwritten(self):
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as data_dir:
            Path(source_dir, "offsets.json").write_text('{"value": 1}', encoding="utf-8")
            target = Path(data_dir, "offsets.json")
            target.write_text('{"value": 2}', encoding="utf-8")
            with patch.dict(os.environ, {app_paths.DATA_DIR_ENV: data_dir}):
                migrated = app_paths.migrate_legacy_state(Path(source_dir))
            self.assertEqual(migrated, {})
            self.assertEqual(target.read_text(encoding="utf-8"), '{"value": 2}')

    def test_relative_offsets_path_is_redirected_to_user_data(self):
        with tempfile.TemporaryDirectory() as data_dir:
            with patch.dict(os.environ, {app_paths.DATA_DIR_ENV: data_dir}):
                save_settings("offsets.json", {"value": 7})
                self.assertEqual(load_settings("offsets.json"), {"value": 7})
                self.assertTrue(Path(data_dir, "offsets.json").exists())

    def test_legacy_calibration_assets_are_migrated_without_overwrite(self):
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as data_dir:
            source = Path(source_dir)
            (source / "assets").mkdir()
            (source / "assets" / "pedido_usuario.png").write_bytes(b"legacy")
            target_dir = Path(data_dir) / "calibration_assets"
            target_dir.mkdir()
            (target_dir / "aviso_sim.png").write_bytes(b"keep-user")
            (source / "assets" / "aviso_sim.png").write_bytes(b"packaged")

            with patch.dict(os.environ, {app_paths.DATA_DIR_ENV: data_dir}):
                migrated = app_paths.migrate_legacy_calibration_assets(source)

            self.assertEqual(
                b"legacy", (target_dir / "pedido_usuario.png").read_bytes()
            )
            self.assertEqual(b"keep-user", (target_dir / "aviso_sim.png").read_bytes())
            self.assertIn("pedido_usuario.png", migrated)
            self.assertNotIn("aviso_sim.png", migrated)

    def test_clean_preset_launcher_never_copies_or_removes_real_offsets(self):
        script = (
            Path(__file__).resolve().parent / "TESTAR_PRESET_COMO_NOVO_USUARIO.ps1"
        ).read_text(encoding="utf-8")
        copy_lines = [line for line in script.splitlines() if "Copy-Item" in line]

        self.assertIn("$env:MKT_DATA_DIR = $testProfile", script)
        self.assertIn("[guid]::NewGuid()", script)
        self.assertFalse(any("offsets.json" in line for line in copy_lines))
        self.assertNotIn("Remove-Item", script)


class UpdateContractTests(unittest.TestCase):
    def manifest(self, content: bytes = b"pacote"):
        return parse_manifest(
            {
                "version": "2.8.0",
                "channel": "stable",
                "downloadUrl": "https://updates.example.com/mkt-2.8.0.zip",
                "sha256": hashlib.sha256(content).hexdigest(),
                "size": len(content),
                "mandatory": False,
                "minimumVersion": "2.7.1",
                "signature": "assinatura-servidor",
                "releaseNotes": ["Atualizador visual com progresso real."],
            }
        )

    def test_semantic_versions_are_compared_numerically(self):
        self.assertEqual(version_tuple("2.10.0"), (2, 10, 0))
        self.assertTrue(is_update_available("2.7.1", self.manifest()))

    def test_manifest_rejects_non_https_download(self):
        payload = {
            "version": "2.8.0",
            "channel": "stable",
            "downloadUrl": "http://updates.example.com/update.zip",
            "sha256": "0" * 64,
            "size": 1,
            "mandatory": False,
        }
        with self.assertRaises(ValueError):
            parse_manifest(payload)

    def test_manifest_accepts_short_release_notes_only(self):
        manifest = self.manifest()
        self.assertEqual(
            manifest.release_notes,
            ("Atualizador visual com progresso real.",),
        )
        payload = {
            "version": "2.8.0",
            "channel": "stable",
            "downloadUrl": "https://updates.example.com/mkt-2.8.0.zip",
            "sha256": "0" * 64,
            "size": 1,
            "mandatory": False,
            "releaseNotes": ["x" * 181],
        }
        with self.assertRaises(ValueError):
            parse_manifest(payload)

    def test_update_client_rejects_download_from_untrusted_host(self):
        payload = {
            "version": "2.8.0",
            "channel": "stable",
            "downloadUrl": "https://malicioso.example/update.zip",
            "sha256": "0" * 64,
            "size": 1,
            "mandatory": False,
        }
        response = MagicMock()
        response.headers = {}
        response.read.return_value = __import__("json").dumps(payload).encode("utf-8")
        response.__enter__.return_value = response
        with patch("update_client.urllib.request.urlopen", return_value=response):
            with self.assertRaisesRegex(ValueError, "nao autorizado"):
                update_client.fetch_available_update()

    def test_update_client_rejects_another_github_repository(self):
        payload = {
            "version": "2.8.0",
            "channel": "stable",
            "downloadUrl": (
                "https://github.com/outro/projeto/releases/download/v2.8.0/"
                "MKT_Update_2.8.0.zip"
            ),
            "sha256": "0" * 64,
            "size": 1,
            "mandatory": False,
        }
        response = MagicMock()
        response.headers = {}
        response.read.return_value = __import__("json").dumps(payload).encode("utf-8")
        response.__enter__.return_value = response
        with patch("update_client.urllib.request.urlopen", return_value=response):
            with self.assertRaisesRegex(ValueError, "nao autorizado"):
                update_client.fetch_available_update()

    def test_update_client_rejects_mismatched_versioned_asset(self):
        payload = {
            "version": "2.8.0",
            "channel": "stable",
            "downloadUrl": (
                "https://github.com/luizphotoshop25-prog/AlbionMKT-Releases/"
                "releases/download/v2.7.9/MKT_Update_2.7.9.zip"
            ),
            "sha256": "0" * 64,
            "size": 1,
            "mandatory": False,
        }
        response = MagicMock()
        response.headers = {}
        response.read.return_value = __import__("json").dumps(payload).encode("utf-8")
        response.__enter__.return_value = response
        with patch("update_client.urllib.request.urlopen", return_value=response):
            with self.assertRaisesRegex(ValueError, "nao autorizado"):
                update_client.fetch_available_update()

    def test_update_client_returns_none_for_current_version(self):
        payload = {
            "version": update_client.APP_VERSION,
            "channel": "stable",
            "downloadUrl": (
                "https://github.com/luizphotoshop25-prog/AlbionMKT-Releases/"
                f"releases/download/v{update_client.APP_VERSION}/"
                f"MKT_Update_{update_client.APP_VERSION}.zip"
            ),
            "sha256": "0" * 64,
            "size": 1,
            "mandatory": False,
        }
        response = MagicMock()
        response.headers = {}
        response.read.return_value = __import__("json").dumps(payload).encode("utf-8")
        response.__enter__.return_value = response
        with patch("update_client.urllib.request.urlopen", return_value=response):
            self.assertIsNone(update_client.fetch_available_update())

    def test_update_endpoint_uses_the_owned_github_release(self):
        self.assertEqual(
            update_client.UPDATE_ENDPOINT,
            "https://github.com/luizphotoshop25-prog/AlbionMKT-Releases/"
            "releases/latest/download/latest.json",
        )

    def test_bundled_updater_refreshes_the_external_updater(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            application = root / "app"
            bundled_dir = application / "updater"
            bundled_dir.mkdir(parents=True)
            bundled = bundled_dir / "MKTUpdater.exe"
            bundled.write_bytes(b"new-updater")
            persistent = root / "persistent"
            persistent.mkdir()
            old = persistent / "MKTUpdater.exe"
            old.write_bytes(b"old-updater")

            with patch("update_client.application_dir", return_value=application), patch(
                "update_client.updater_dir", return_value=persistent
            ):
                resolved = update_client._installed_updater()

            self.assertEqual(resolved, old)
            self.assertEqual(old.read_bytes(), b"new-updater")

    def test_package_requires_exact_size_and_sha256(self):
        content = b"pacote"
        manifest = self.manifest(content)
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory, "update.zip")
            package.write_bytes(content)
            self.assertTrue(verify_package(package, manifest))
            package.write_bytes(content + b"alterado")
            self.assertFalse(verify_package(package, manifest))


class ExternalUpdaterTests(unittest.TestCase):
    def test_update_replaces_app_and_keeps_previous_version(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install = root / "MKT"
            install.mkdir()
            (install / "MKT.exe").write_bytes(b"old")
            (install / "old.txt").write_text("old", encoding="utf-8")
            package = root / "update.zip"
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("app/MKT.exe", b"new")
                archive.writestr("app/new.txt", "new")
                archive.writestr(
                    "app/assets/certified-preset/reference.png", b"reference"
                )

            backup = apply_update(package, install)

            self.assertEqual((install / "MKT.exe").read_bytes(), b"new")
            self.assertEqual((install / "new.txt").read_text(encoding="utf-8"), "new")
            self.assertEqual(
                (install / "assets/certified-preset/reference.png").read_bytes(),
                b"reference",
            )
            self.assertEqual((backup / "MKT.exe").read_bytes(), b"old")

    def test_package_without_main_executable_never_touches_installation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install = root / "MKT"
            install.mkdir()
            (install / "MKT.exe").write_bytes(b"old")
            package = root / "invalid.zip"
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("app/readme.txt", "missing exe")

            with self.assertRaises(UpdateError):
                apply_update(package, install)

            self.assertEqual((install / "MKT.exe").read_bytes(), b"old")

    def test_zip_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "unsafe.zip"
            destination = root / "extract"
            destination.mkdir()
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("../outside.txt", "unsafe")

            with self.assertRaises(UpdateError):
                extract_payload(package, destination)
            self.assertFalse((root / "outside.txt").exists())


if __name__ == "__main__":
    unittest.main()
