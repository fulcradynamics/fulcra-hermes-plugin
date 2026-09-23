"""Adapter regressions. No SDK, network, or real credentials are needed."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load_tools():
    spec = importlib.util.spec_from_file_location("context_adapter", ROOT / "tools.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AdapterTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.managed_bin = Path(temporary.name) / "managed bin"
        self.managed_bin.mkdir()
        # Stub only Hermes's path provider; executable lookup uses real files.
        managed_uv = types.ModuleType("hermes_cli.managed_uv")
        managed_uv.managed_uv_path = lambda: self.managed_bin / "uv"
        modules = patch.dict(sys.modules, {"hermes_cli.managed_uv": managed_uv})
        modules.start()
        self.addCleanup(modules.stop)

    def test_auth_unexpected_errors_are_safe_and_success_output_is_bounded(self):
        tools = load_tools()
        for handler, args in ((tools.fulcra_get_auth_url, {}), (tools.fulcra_submit_device_code, {"device_code": "fixture"})):
            with patch.object(tools, "_run_cli", side_effect=OSError("private-secret")):
                result = handler(args)
            self.assertNotIn("private-secret", result)
            self.assertTrue(result.startswith("Error"))
            with patch.object(tools, "_run_cli", return_value="x" * 40000):
                result = handler(args)
            self.assertLessEqual(len(result), 24000)

    def test_empty_read_streams_and_silent_mutation_are_successful(self):
        tools = load_tools()
        with patch.object(tools, "_runtime_context", return_value=(True, {"PATH": "/bin"})), \
             patch("shutil.which", return_value="/bin/uv"), \
             patch("subprocess.run", return_value=subprocess.CompletedProcess([], 0, "", "")):
            for argv in (["catalog", "--name", "none"], ["get-records", "HeartRate", "1 day"],
                         ["share", "list-incoming"], ["file", "list", "/"], ["file", "delete", "/fixture"]):
                with self.subTest(argv=argv):
                    self.assertEqual(tools._run_cli(argv), "")
            self.assertIn("empty response", tools.fulcra_get_auth_url({}))

    def test_raw_cli_diagnostics_never_expose_credentials(self):
        tools = load_tools()
        for diagnostic in ('Authorization: Bearer secret-token', '{"refresh_token":"secret-refresh"}',
                           'https://example.test?token=secret-query', 'No credentials found secret-extra',
                           'HTTP Error 403 secret-denied'):
            with self.subTest(diagnostic=diagnostic), \
                 patch.object(tools, "_runtime_context", return_value=(True, {"PATH": "/bin"})), \
                 patch("shutil.which", return_value="/bin/uv"), \
                 patch("subprocess.run", return_value=subprocess.CompletedProcess([], 1, "", diagnostic)):
                result = tools.fulcra_get_data_catalog({})
            self.assertNotIn("secret-", result)
            self.assertIn("Error", result)
            self.assertLess(len(result), 1000)

    def test_catalog_filters_and_bounded_json(self):
        tools = load_tools()
        with patch.object(tools, "_run_cli", return_value='{"id":"one"}\n{"id":"two"}') as run:
            result = json.loads(tools.fulcra_get_data_catalog({"name": "Mood", "recordable_only": True, "limit": 1}))
        self.assertEqual(run.call_args.args[0], ["catalog", "--name", "Mood", "--recordable-only"])
        self.assertEqual(result, {"items": [{"id": "one"}], "returned": 1, "available": 2, "truncated": True})
        for args in ({"unknown": True}, {"data_type": "--help"}, {"name": "bad\u0000"}, {"limit": True}):
            with self.subTest(args=args), patch.object(tools, "_run_cli") as run:
                self.assertTrue(tools.fulcra_get_data_catalog(args).startswith("Error"))
                run.assert_not_called()

    def test_catalog_runs_pinned_cli_in_isolation(self):
        tools = load_tools()
        result = subprocess.CompletedProcess([], 0, '[{"id":"fixture"}]\n', '')
        with patch.object(tools, "_runtime_context", create=True, return_value=(True, {"PATH": "/bin"})), \
             patch("shutil.which", return_value="/bin/uv") as which, \
             patch("subprocess.run", return_value=result) as run:
            self.assertEqual(json.loads(tools.fulcra_get_data_catalog({})), json.loads(result.stdout))
        which.assert_called_once_with("uv", path=os.pathsep.join(("/bin", str(self.managed_bin))))
        command = run.call_args.args[0]
        self.assertEqual(command, ["/bin/uv", "tool", "run", "--isolated", "--no-config", "--from", "fulcra-api==0.1.42", "fulcra-api", "catalog"])
        self.assertFalse(run.call_args.kwargs.get("shell", False))
        self.assertGreater(run.call_args.kwargs["timeout"], 0)

    def test_managed_uv_is_found_outside_path(self):
        managed_bin = self.managed_bin
        uv = managed_bin / ("uv.exe" if os.name == "nt" else "uv")
        uv.touch()
        uv.chmod(0o755)  # Discovery fixture only; subprocess execution is mocked.
        tools = load_tools()
        parent_path = os.environ.get("PATH")
        for path in ("", str(managed_bin.parent / "absent"), str(managed_bin)):
            env = {"PATH": path}
            with self.subTest(path=path), \
                 patch.object(tools, "_runtime_context", return_value=(True, env)), \
                 patch("subprocess.run", return_value=subprocess.CompletedProcess([], 0, "[]", "")) as run:
                self.assertEqual(tools._run_cli(["catalog"]), "[]")
            self.assertEqual(run.call_args.args[0][0], str(uv))
            child_path = run.call_args.kwargs["env"]["PATH"]
            expected = path if path == str(managed_bin) else os.pathsep.join(filter(None, (path, str(managed_bin))))
            self.assertEqual(child_path, expected)
            self.assertEqual(env["PATH"], path)
            self.assertEqual(os.environ.get("PATH"), parent_path)

    def test_authentication_uses_noninteractive_cli(self):
        tools = load_tools()
        with patch.object(tools, "_run_cli", return_value="Web auth URL: https://example.test\n- Device code: fixture") as run:
            output = tools.fulcra_get_auth_url({})
        run.assert_called_once_with(["auth", "login", "--get-auth-url"])
        self.assertIn("fulcra_auth_device", output)
        self.assertIn("Wait for the user", output)

    def test_device_code_is_passed_as_a_single_argument(self):
        tools = load_tools()
        device_code = "fixture; not-a-shell-command"
        with patch.object(tools, "_run_cli", return_value="Authorization successful!") as run:
            output = tools.fulcra_submit_device_code({"device_code": device_code})
        run.assert_called_once_with(
            ["auth", "login", "--device-code", device_code, "--poll-timeout", "900", "--poll-interval", "5"],
            timeout=1080,
        )
        self.assertIn("successful", output)

    def test_invalid_device_code_does_not_launch_a_process(self):
        tools = load_tools()
        for value in (None, "", "   ", 5, [], "bad\x00code", "--help"):
            with self.subTest(value=value), patch.object(tools, "_run_cli") as run:
                self.assertTrue(tools.fulcra_submit_device_code({"device_code": value}).startswith("Error:"))
                run.assert_not_called()

    def test_uv_environment_isolation(self):
        tools = load_tools()
        env = {"PATH": "/bin", "HOME": "/home/fixture", "VIRTUAL_ENV": "/hermes/venv",
               "PYTHONPATH": "/hermes", "UV_PROJECT_ENVIRONMENT": "/hermes/venv", "UV_FROM": "untrusted"}
        with patch.object(tools, "_runtime_context", return_value=(True, env)), \
             patch("shutil.which", side_effect=lambda name, **kw: "/bin/uv" if name == "uv" else None), \
             patch("subprocess.run", return_value=subprocess.CompletedProcess([], 0, "{}", "")) as run:
            self.assertEqual(tools._run_cli(["catalog"]), "{}")
        self.assertEqual(run.call_args.args[0][:3], ["/bin/uv", "tool", "run"])
        child = run.call_args.kwargs["env"]
        for key in ("VIRTUAL_ENV", "PYTHONPATH", "UV_PROJECT_ENVIRONMENT", "UV_FROM"):
            self.assertNotIn(key, child)
        self.assertEqual(child["HOME"], env["HOME"])
        self.assertEqual(child["PYTHONIOENCODING"], "utf-8")
        self.assertEqual(run.call_args.kwargs["stdin"], subprocess.DEVNULL)
        self.assertEqual(env["UV_FROM"], "untrusted")

    def test_missing_uv_is_actionable(self):
        tools = load_tools()
        with patch.object(tools, "_runtime_context", return_value=(True, {})), \
             patch("shutil.which", return_value=None), patch("subprocess.run") as run:
            result = tools.fulcra_get_data_catalog({})
        self.assertIn("Install uv", result)
        run.assert_not_called()

    def test_lazy_install_opt_out_never_launches_uv(self):
        tools = load_tools()
        with patch.object(tools, "_runtime_context", return_value=(False, {})), patch("subprocess.run") as run:
            self.assertIn("allow_lazy_installs", tools.fulcra_get_auth_url({}))
        run.assert_not_called()

    def test_timeout_does_not_leak_command_or_partial_output(self):
        tools = load_tools()
        error = subprocess.TimeoutExpired(["uv", "sensitive-command"], 1, output="sensitive-output")
        with patch.object(tools, "_runtime_context", return_value=(True, {"PATH": "/bin"})), \
             patch("shutil.which", return_value="/bin/uv"), patch("subprocess.run", side_effect=error):
            output = tools.fulcra_get_data_catalog({})
        self.assertIn("timed out", output)
        self.assertNotIn("sensitive", output)

    def test_cli_failure_is_bounded_and_device_code_redacted(self):
        tools = load_tools()
        result = subprocess.CompletedProcess([], 1, "", "fixture-device " + "x" * 5000)
        with patch.object(tools, "_runtime_context", return_value=(True, {"PATH": "/bin"})), \
             patch("shutil.which", return_value="/bin/uv"), patch("subprocess.run", return_value=result):
            output = tools.fulcra_submit_device_code({"device_code": "fixture-device"})
        self.assertIn("[redacted]", output)
        self.assertLess(len(output), 2500)
        self.assertNotIn("fixture-device", output)

    def test_empty_success_is_an_error(self):
        tools = load_tools()
        with patch.object(tools, "_runtime_context", return_value=(True, {"PATH": "/bin"})), \
             patch("shutil.which", return_value="/bin/uv"), \
             patch("subprocess.run", return_value=subprocess.CompletedProcess([], 0, "", "")):
            self.assertIn("empty response", tools.fulcra_get_auth_url({}))

    def test_catalog_rejects_non_json_output(self):
        tools = load_tools()
        with patch.object(tools, "_run_cli", return_value="not json"):
            self.assertTrue(tools.fulcra_get_data_catalog({}).startswith("Error"))

    def test_catalog_normalizes_json_lines_and_empty_catalog(self):
        tools = load_tools()
        for raw, expected in (
            ('{"id":"one"}\n{"id":"two"}\n', [{"id": "one"}, {"id": "two"}]),
            ('{"id":"one"}\n', [{"id": "one"}]),
            ('', []),
        ):
            with self.subTest(raw=raw), \
                 patch.object(tools, "_runtime_context", return_value=(True, {"PATH": "/bin"})), \
                 patch("shutil.which", return_value="/bin/uv"), \
                 patch("subprocess.run", return_value=subprocess.CompletedProcess([], 0, raw, "")):
                self.assertEqual(tools.fulcra_get_data_catalog({}), json.dumps(expected, indent=2))


if __name__ == "__main__":
    unittest.main()
