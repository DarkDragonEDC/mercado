from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import license_manager as gate


class FakeResponse:
    def __init__(self, status: int, payload):
        self.status_code = status
        self._payload = payload

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class LicenseContractTests(unittest.TestCase):
    def call(self, payload, status=200):
        with patch.object(gate.requests, "post", return_value=FakeResponse(status, payload)) as post:
            result = gate.request_license("validate", "KEY-TESTE", "a" * 64)
        sent = post.call_args.kwargs["json"]
        self.assertEqual(set(sent), {"key", "hwid", "appVersion"})
        self.assertEqual(post.call_args.args[0], gate.VALIDATE_URL)
        return result

    def test_ok_without_modules_is_accepted(self):
        result = self.call({"valid": True, "code": "OK", "expiresAt": "2030-01-01T00:00:00Z"})
        self.assertEqual(result.expires_at, "2030-01-01T00:00:00Z")

    def test_expected_module_is_accepted(self):
        result = self.call({"valid": True, "code": "OK", "modules": ["purchase_orders"]})
        self.assertEqual(result.modules, ("purchase_orders",))

    def test_sales_module_is_accepted(self):
        result = self.call({"valid": True, "code": "OK", "modules": ["sales_orders"]})
        self.assertEqual(result.modules, ("sales_orders",))

    def test_missing_module_is_blocked(self):
        with self.assertRaises(gate.LicenseError) as raised:
            self.call({"valid": True, "code": "OK", "modules": ["another_app"]})
        self.assertEqual(raised.exception.code, "MODULE_NOT_ALLOWED")

    def test_all_documented_codes_are_mapped(self):
        for code in (
            "INVALID_KEY", "REVOKED", "EXPIRED", "HWID_REQUIRED",
            "NOT_ACTIVATED", "DEVICE_LIMIT", "MODULE_NOT_ALLOWED",
            "RATE_LIMIT", "SERVER_ERROR",
        ):
            with self.subTest(code=code), patch.object(
                gate.requests, "post", return_value=FakeResponse(403, {"valid": False, "code": code})
            ):
                with self.assertRaises(gate.LicenseError) as raised:
                    gate.request_license("activate", "KEY-TESTE", "b" * 64)
                self.assertEqual(raised.exception.code, code)
                self.assertEqual(raised.exception.message, gate.ERROR_MESSAGES[code])

    def test_network_failure_is_temporary(self):
        with patch.object(gate.requests, "post", side_effect=gate.requests.ConnectionError()):
            with self.assertRaises(gate.LicenseError) as raised:
                gate.request_license("validate", "KEY-TESTE", "c" * 64)
        self.assertTrue(raised.exception.temporary)

    def test_persistence_contains_only_allowed_fields(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
            gate, "license_path", return_value=Path(directory) / "license.json"
        ):
            gate.save_license("KEY-TESTE", "2030-01-01T00:00:00Z")
            data = json.loads((Path(directory) / "license.json").read_text(encoding="utf-8"))
            self.assertEqual(
                set(data), {"key", "lastValidatedAt", "expiresAt", "appVersion"}
            )
            self.assertEqual(gate.load_license(), data)

    def test_hwid_is_sha256_of_combined_identifiers(self):
        with patch.object(gate, "_machine_guid", return_value="GUID-1234"), patch.object(
            gate, "_cim_identifiers", return_value={"BiosSerial": "BIOS-5678"}
        ):
            first = gate.get_stable_hwid()
            second = gate.get_stable_hwid()
        self.assertRegex(first, r"^[0-9a-f]{64}$")
        self.assertEqual(first, second)

    def test_hwid_requires_multiple_identifiers(self):
        with patch.object(gate, "_machine_guid", return_value="GUID-1234"), patch.object(
            gate, "_cim_identifiers", return_value={}
        ):
            with self.assertRaises(gate.HwidError):
                gate.get_stable_hwid()

    def test_tk_callback_keeps_exception_after_except_scope(self):
        callbacks = []
        root = Mock()
        root.after.side_effect = lambda _delay, callback: callbacks.append(callback)
        received = []

        try:
            raise gate.LicenseError("INVALID_KEY", "Key invalida")
        except gate.LicenseError as exc:
            gate.run_on_tk(root, received.append, exc)

        callbacks.pop()()
        self.assertEqual(received[0].code, "INVALID_KEY")

    def test_activation_request_leaves_processing_state_on_api_error(self):
        finished = threading.Event()
        window = gate.ActivationWindow.__new__(gate.ActivationWindow)
        window.root = Mock()
        window.root.after.side_effect = lambda _delay, callback: callback()
        window.hwid = "d" * 64
        window.status = Mock()
        window.expiration = Mock()
        window._set_processing = Mock()
        original_show_error = window._show_error

        def show_error_and_finish(error):
            original_show_error(error)
            finished.set()

        window._show_error = show_error_and_finish
        failure = gate.LicenseError("INVALID_KEY", gate.ERROR_MESSAGES["INVALID_KEY"])
        with patch.object(gate, "request_license", side_effect=failure):
            window._request("activate", "KEY-TESTE")
            self.assertTrue(finished.wait(2), "callback de erro nao foi executado")

        window._set_processing.assert_any_call(False)
        window.status.config.assert_called_with(
            text=gate.ERROR_MESSAGES["INVALID_KEY"], fg="#d33b3b"
        )

    def test_result_to_key_info_preserves_modules(self):
        result = gate.LicenseResult(
            key="KEY-TESTE-1234",
            expires_at="2030-01-01T00:00:00Z",
            remaining_seconds=3600,
            newly_activated=False,
            modules=(gate.PURCHASE_MODULE_ID, gate.SALES_MODULE_ID),
            raw={},
        )
        key_info = gate.result_to_key_info(result)
        self.assertEqual(
            key_info["modules"],
            [gate.PURCHASE_MODULE_ID, gate.SALES_MODULE_ID],
        )
        self.assertTrue(key_info["modulesEnforced"])

    def test_purchase_only_key_grants_only_purchase(self):
        key_info = {"modules": [gate.PURCHASE_MODULE_ID]}
        self.assertTrue(gate.has_module_access(key_info, gate.PURCHASE_MODULE_ID))
        self.assertFalse(gate.has_module_access(key_info, gate.SALES_MODULE_ID))
        self.assertFalse(
            gate.has_all_module_access(
                key_info, gate.PURCHASE_MODULE_ID, gate.SALES_MODULE_ID
            )
        )

    def test_complete_key_grants_purchase_and_sales(self):
        key_info = {
            "modules": [gate.PURCHASE_MODULE_ID, gate.SALES_MODULE_ID]
        }
        self.assertTrue(
            gate.has_all_module_access(
                key_info, gate.PURCHASE_MODULE_ID, gate.SALES_MODULE_ID
            )
        )

    def test_legacy_key_without_modules_remains_compatible(self):
        key_info = {"modules": None}
        self.assertTrue(gate.has_module_access(key_info, gate.PURCHASE_MODULE_ID))
        self.assertTrue(gate.has_module_access(key_info, gate.SALES_MODULE_ID))

    def test_legacy_result_without_modules_does_not_enforce_separation(self):
        result = self.call({"valid": True, "code": "OK"})
        key_info = gate.result_to_key_info(result)
        self.assertFalse(key_info["modulesEnforced"])


if __name__ == "__main__":
    unittest.main()
