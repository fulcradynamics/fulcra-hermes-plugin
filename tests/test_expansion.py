"""Behavior tests at the CLI boundary; never contact a Fulcra account."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_tools import load_tools

ID = "01234567-89ab-cdef-0123-456789abcdef"
DT = "NumericAnnotation/" + ID


class ExpansionTests(unittest.TestCase):
    def setUp(self):
        self.tools = load_tools()

    def invoke(self, name, args, output="{}"):
        with patch.object(self.tools, "_run_cli", return_value=output) as run:
            result = getattr(self.tools, name)(args)
        self.assertFalse(result.startswith("Error"), result)
        return result, run.call_args.args[0]

    def reject(self, name, cases):
        for args in cases:
            with self.subTest(tool=name, args=args), patch.object(self.tools, "_run_cli") as run:
                result = getattr(self.tools, name)(args)
                self.assertTrue(result.startswith("Error"), result)
                run.assert_not_called()

    def test_large_reads_export_complete_json_without_overwriting(self):
        rows = [{"value": i, "note": "x" * 1000} for i in range(40)]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "records.json"
            result, argv = self.invoke("fulcra_get_records", {
                "data_type": DT, "time_range": ["1 day"], "limit": 1, "output_path": str(output)}, json.dumps(rows))
            self.assertEqual(json.loads(output.read_text()), rows)
            self.assertEqual(json.loads(result)["output_path"], str(output))
            self.assertNotIn(str(output), argv)
            self.reject("fulcra_get_records", [{"data_type": DT, "time_range": ["1 day"], "output_path": str(output)}])
        result, _ = self.invoke("fulcra_get_records", {"data_type": DT, "time_range": ["1 day"], "limit": 2}, json.dumps(rows))
        parsed = json.loads(result)
        self.assertEqual(parsed["returned"], len(parsed["items"]))
        self.assertEqual(parsed["available"], len(rows))
        self.assertTrue(parsed["truncated"])
        result, _ = self.invoke("fulcra_data_type_schema", {"data_type": DT}, json.dumps({"large": "x" * 30000}))
        self.assertTrue(json.loads(result)["data_omitted"])
        self.assertLess(len(result), 24000)

    def test_auth_rejects_unknown_arguments_before_cli(self):
        self.reject("fulcra_get_auth_url", [{"reset": True}, None])
        self.reject("fulcra_submit_device_code", [{"device_code": "fixture", "extra": "x"}])

    def test_negative_default_is_literal_and_remote_paths_are_not_repaired(self):
        _, argv = self.invoke("fulcra_create_data_type", {"base_type": "NumericAnnotation", "name": "Temperature", "default_value": "-2.5"})
        self.assertIn("--value=-2.5", argv)
        for name in ("fulcra_file_delete", "fulcra_file_stat", "fulcra_file_share"):
            base = {"user_ids": [ID]} if name == "fulcra_file_share" else {}
            self.reject(name, [{**base, "path": path} for path in ("/notes/../private", "//notes/test", "/notes/./test", "/notes\\test")])

    def test_file_upload_preserves_text_and_local_bytes_without_leaking_temp_files(self):
        seen = []
        def boundary(argv):
            self.assertEqual(argv[:2], ["file", "upload"])
            self.assertEqual(argv[3], "/notes/test.txt")
            path = Path(argv[2])
            seen.append(path)
            self.assertEqual(path.read_bytes(), b"--literal text\n")
            return "Uploaded"
        with patch.object(self.tools, "_run_cli", side_effect=boundary):
            result = self.tools.fulcra_file_upload({"path": "/notes/test.txt", "content": "--literal text\n"})
        self.assertFalse(result.startswith("Error"), result)
        self.assertFalse(seen[0].exists())
        with tempfile.TemporaryDirectory() as directory:
            local = Path(directory) / "input.bin"
            local.write_bytes(b"--literal text\n")
            with patch.object(self.tools, "_run_cli", side_effect=boundary):
                result = self.tools.fulcra_file_upload({"path": "/notes/test.txt", "local_path": str(local)})
            self.assertFalse(result.startswith("Error"), result)
            self.assertTrue(local.exists())
        self.reject("fulcra_file_upload", [
            {"path": "/notes/test.txt"}, {"path": "/notes/test.txt", "content": "x", "local_path": "/tmp/x"},
            {"path": "--help", "content": "x"}, {"path": "/notes/test.txt", "local_path": "-"},
        ])

    def test_file_download_returns_text_or_exclusive_local_file(self):
        seen = []
        def boundary(argv):
            self.assertEqual(argv[:3], ["file", "download", "/notes/test.txt"])
            seen.append(Path(argv[3]))
            seen[-1].write_bytes(b"hello\n")
            return "Downloaded"
        with patch.object(self.tools, "_run_cli", side_effect=boundary):
            result = json.loads(self.tools.fulcra_file_download({"path": "/notes/test.txt"}))
        self.assertEqual(result["content"], "hello\n")
        self.assertFalse(result["truncated"])
        self.assertFalse(seen[-1].exists())
        with tempfile.TemporaryDirectory() as directory:
            local = Path(directory) / "saved.txt"
            with patch.object(self.tools, "_run_cli", side_effect=boundary):
                result = json.loads(self.tools.fulcra_file_download({"path": "/notes/test.txt", "local_path": str(local)}))
            self.assertEqual(local.read_bytes(), b"hello\n")
            self.assertEqual(result["local_path"], str(local))
            self.reject("fulcra_file_download", [{"path": "/notes/test.txt", "local_path": str(local)}])
            self.assertEqual(local.read_bytes(), b"hello\n")
        def binary(argv):
            Path(argv[3]).write_bytes(b"\xff\x00")
            return "Downloaded"
        with patch.object(self.tools, "_run_cli", side_effect=binary):
            self.assertIn("local_path", self.tools.fulcra_file_download({"path": "/notes/test.txt"}))

    def test_file_metadata_delete_restore_and_share_keep_cli_capabilities(self):
        for name, args, expected, output in (
            ("fulcra_file_list", {"path": "/notes/", "user_id": ID, "limit": 1}, ["file", "list", "/notes/", "--user-id", ID], "folder/\n1B 2026-01-01 test.txt"),
            ("fulcra_file_stat", {"path": "/notes/test.txt"}, ["file", "stat", "/notes/test.txt"], "Version: " + ID),
            ("fulcra_file_delete", {"path": "/notes/test.txt"}, ["file", "delete", "/notes/test.txt"], "Deleted"),
            ("fulcra_file_restore", {"version_id": ID}, ["file", "restore", ID], "Restored"),
            ("fulcra_file_share", {"path": "/notes/", "user_ids": [ID], "name": "Notes"}, ["file", "share", "/notes/", "--to", ID, "--name", "Notes"], '{}'),
        ):
            result, argv = self.invoke(name, args, output)
            self.assertEqual(argv, expected)
            if name == "fulcra_file_list":
                self.assertTrue(json.loads(result)["truncated"])
        self.reject("fulcra_file_restore", [{"version_id": ID.replace("-", "")}])
        self.reject("fulcra_file_share", [{"path": "/notes/", "user_ids": []}])

    def test_share_creation_requires_explicit_recipients_and_scope(self):
        _, argv = self.invoke("fulcra_create_share", {"name": "Study", "user_ids": [ID], "group_ids": [ID], "data_types": ["HeartRate"], "files": ["/notes/"], "start_time": "2026-01-01T00:00:00Z"})
        self.assertEqual(argv, ["share", "create", "--name", "Study", "--data-type", "HeartRate", "--file", "/notes/", "--user-id", ID, "--group-id", ID, "--start-time", "2026-01-01T00:00:00Z"])
        self.reject("fulcra_create_share", [
            {"user_ids": [ID]}, {"data_types": ["HeartRate"]},
            {"user_ids": [ID], "share_all": True, "data_types": ["HeartRate"]},
            {"user_ids": [ID], "files": ["relative/path"]},
            {"user_ids": [ID], "share_all": True, "start_time": "2026-01-01"},
        ])

    def test_share_updates_preserve_false_and_reject_conflicts(self):
        _, argv = self.invoke("fulcra_update_share", {"share_id": ID, "share_all": False, "no_start_time": True, "add_user_ids": [ID], "remove_files": ["/notes/"]})
        self.assertEqual(argv, ["share", "update", ID, "--remove-file", "/notes/", "--add-user-id", ID, "--no-start-time", "--no-share-all-data"])
        self.reject("fulcra_update_share", [
            {"share_id": ID}, {"share_id": ID, "set_user_ids": []},
            {"share_id": ID, "set_data_types": ["HeartRate"], "add_data_types": ["StepCount"]},
            {"share_id": ID, "add_user_ids": [ID], "remove_user_ids": [ID]},
            {"share_id": ID, "no_group_ids": True, "set_group_ids": [ID]},
            {"share_id": ID, "start_time": "2026-01-01T00:00:00Z", "no_start_time": True},
            {"share_id": ID, "clear": True, "share_all": True},
        ])

    def test_share_reads_delete_and_leave_use_distinct_identifiers(self):
        with patch.object(self.tools, "_run_cli", side_effect=['{"grant_id":"fixture"}', '']) as run:
            result = json.loads(self.tools.fulcra_list_shares({"direction": "both"}))
        self.assertEqual([c.args[0] for c in run.call_args_list], [["share", "list-incoming"], ["share", "list-outgoing"]])
        self.assertEqual(result, {"incoming": [{"grant_id": "fixture"}], "outgoing": []})
        for name, field, command in (("fulcra_delete_share", "share_id", "delete"), ("fulcra_leave_share", "grant_id", "leave")):
            _, argv = self.invoke(name, {field: ID}, "Success")
            self.assertEqual(argv, ["share", command, ID])
            self.reject(name, [{field: "--help"}, {field: ID + "/suffix"}])
        result, argv = self.invoke("fulcra_shared_data_types", {"user_id": ID, "time_range": ["1 week"]}, '{"all_data_types":true,"fulcra_data_types":[]}')
        self.assertTrue(json.loads(result)["all_data_types"])
        self.assertEqual(argv, ["share", "shared-data-types", ID, "1 week"])

    def test_records_use_private_jsonl_and_cleanup_even_on_failure(self):
        for name, field, rows, command in (
            ("fulcra_record", "record", {"value": -2, "note": "--help; safe"}, "record"),
            ("fulcra_record", "records", [{"value": 1}, {"value": 2}], "record"),
            ("fulcra_delete_records", "record", {"record_id": ID}, "delete"),
            ("fulcra_delete_records", "records", [{"record_id": ID}, {"record_id": ID}], "delete"),
        ):
            paths = []
            def boundary(argv):
                self.assertEqual(argv[:2], [command, DT])
                path = Path(argv[argv.index("--file") + 1])
                paths.append(path)
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                self.assertEqual([json.loads(line) for line in path.read_text().splitlines()], rows if isinstance(rows, list) else [rows])
                return "Recorded 2 records\nUpload ID: fixture"
            with self.subTest(name=name, field=field), patch.object(self.tools, "_run_cli", side_effect=boundary):
                result = getattr(self.tools, name)({"data_type": DT, field: rows})
                self.assertFalse(result.startswith("Error"), result)
            self.assertFalse(paths[0].exists())
            def failing(argv):
                boundary(argv)
                raise RuntimeError("fixture failure")
            with patch.object(self.tools, "_run_cli", side_effect=failing):
                self.assertIn("Error", getattr(self.tools, name)({"data_type": DT, field: rows}))
            self.assertFalse(paths[-1].exists())
        _, argv = self.invoke("fulcra_delete_records", {"data_type": DT, "record_id": ID, "api_version": "v1alpha1"}, "Deleted 1 record")
        self.assertEqual(argv, ["delete", DT, ID, "--api-version", "v1alpha1"])
        self.reject("fulcra_record", [
            {"data_type": DT}, {"data_type": DT, "record": {}, "records": [{}]},
            {"data_type": DT, "records": []}, {"data_type": DT, "record": {"note": "bad\u0000"}},
            {"data_type": DT, "record": {"value": float("nan")}},
        ])
        self.reject("fulcra_delete_records", [
            {"data_type": DT, "record_id": "{" + ID + "}"},
            {"data_type": DT, "records": [{"record_id": ID, "unexpected": True}]},
            {"data_type": DT, "record_id": ID, "records": [{"record_id": ID}]},
        ])

    def test_record_queries_and_updates_validate_time_and_bound_output(self):
        for name, prefix in (("fulcra_get_records", ["get-records", DT]), ("fulcra_data_updates", ["data-updates"])):
            base = {"data_type": DT} if name == "fulcra_get_records" else {}
            _, argv = self.invoke(name, {**base, "time_range": ["2 days"], "user_id": ID}, '[]' if base else '{}')
            self.assertEqual(argv, prefix + ["2 days", "--user-id", ID])
            self.reject(name, [
                {**base, "time_range": ["2026-01-01T00:00:00", "2026-01-02T00:00:00Z"]},
                {**base, "time_range": ["2026-01-02T00:00:00Z", "2026-01-01T00:00:00Z"]},
                {**base, "time_range": ["2026-01-01"]}, {**base, "time_range": ["--help"]},
                {**base, "time_range": ["0 days"]},
            ])
        result, argv = self.invoke("fulcra_get_records", {"data_type": DT, "time_range": ["latest"]}, '{"value":2}')
        self.assertEqual(json.loads(result), [{"value": 2}])
        self.assertEqual(argv, ["get-records", DT, "latest"])
        self.reject("fulcra_data_updates", [{"time_range": ["latest"]}])
        self.reject("fulcra_get_records", [
            {"data_type": DT, "time_range": ["1 day"], "group_id": ID},
            {"data_type": DT, "time_range": ["1 day"], "group_id": ID, "participant_id": ID, "user_id": ID},
        ])

    def test_data_type_create_options_and_scope_validation(self):
        _, argv = self.invoke("fulcra_create_data_type", {
            "base_type": "NumericAnnotation", "name": "Energy", "description": "Daily energy",
            "tags": ["daily", "self"], "metric_kind": "discrete", "default_value": "2.5", "unit": "points"})
        self.assertEqual(argv, ["data-type", "create", "NumericAnnotation", "Energy", "--description", "Daily energy",
                                "--tag", "daily", "--tag", "self", "--kind", "discrete", "--value", "2.5", "--unit", "points"])
        self.reject("fulcra_create_data_type", [
            {"base_type": "ScaleAnnotation", "name": "Mood", "scale_labels": ["bad"]},
            {"base_type": "MomentAnnotation", "name": "Event", "unit": "points"},
            {"base_type": "NumericAnnotation", "name": "--help"},
            {"base_type": "BooleanAnnotation", "name": "Done", "default_value": "maybe"},
            {"base_type": "NumericAnnotation", "name": "N", "default_value": "nan"},
        ])

    def test_schema_and_lifecycle_preserve_exact_identifiers(self):
        result, argv = self.invoke("fulcra_data_type_schema", {"data_type": DT, "api_version": "v1alpha1", "user_id": ID}, '{"type":"object"}')
        self.assertEqual(json.loads(result), {"type": "object"})
        self.assertEqual(argv, ["data-type", "schema", DT, "--api-version", "v1alpha1", "--user-id", ID])
        for action in ("archive", "restore"):
            _, argv = self.invoke("fulcra_data_type_lifecycle", {"data_type": DT, "action": action}, "Archived" if action == "archive" else "{}")
            self.assertEqual(argv, ["data-type", action, DT])
        self.reject("fulcra_data_type_lifecycle", [
            {"data_type": DT + "/ignored", "action": "restore"},
            {"data_type": "NumericAnnotation/" + ID.replace("-", ""), "action": "archive"},
            {"data_type": "HeartRate", "action": "archive"},
            {"data_type": DT, "action": "delete"},
        ])
