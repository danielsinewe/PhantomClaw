from __future__ import annotations

import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import railway_openclaw_deploy


class RailwayOpenClawDeployTests(unittest.TestCase):
    def test_loads_repo_root_target_from_local_config(self) -> None:
        with TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "Automations"
            repo_root.mkdir()
            config_path = Path(tmpdir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "projects": {
                            str(repo_root): {
                                "project": "project-id",
                                "environment": "environment-id",
                                "service": "service-id",
                            }
                        }
                    }
                )
            )

            target = railway_openclaw_deploy.load_local_railway_target(config_path, repo_root)

        self.assertEqual(target.project, "project-id")
        self.assertEqual(target.environment, "environment-id")
        self.assertEqual(target.service, "service-id")
        self.assertEqual(target.source, str(config_path))

    def test_loads_deploy_path_target_from_local_config(self) -> None:
        with TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "Automations"
            deploy_path = repo_root / "deployments" / "openclaw-railway"
            deploy_path.mkdir(parents=True)
            config_path = Path(tmpdir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "projects": {
                            str(deploy_path): {
                                "project": "project-id",
                                "environmentName": "production",
                                "service": "OpenClaw",
                            }
                        }
                    }
                )
            )

            target = railway_openclaw_deploy.load_local_railway_target(config_path, repo_root)

        self.assertEqual(target.project, "project-id")
        self.assertEqual(target.environment, "production")
        self.assertEqual(target.service, "OpenClaw")

    def test_command_env_reads_token_file_without_printing_token(self) -> None:
        with TemporaryDirectory() as tmpdir:
            token_file = Path(tmpdir) / "railway.token"
            token_file.write_text("secret-project-token\n")
            args = railway_openclaw_deploy.build_parser().parse_args(["--token-file", str(token_file)])

            with patch.dict("os.environ", {}, clear=True):
                env = railway_openclaw_deploy.command_env(args)

        self.assertEqual(env["RAILWAY_TOKEN"], "secret-project-token")
        self.assertEqual(railway_openclaw_deploy.auth_mode(env), "project_token")

    def test_command_env_detects_account_token_without_rewriting_it(self) -> None:
        args = railway_openclaw_deploy.build_parser().parse_args([])

        with patch.dict("os.environ", {"RAILWAY_API_TOKEN": "account-token"}, clear=True):
            env = railway_openclaw_deploy.command_env(args)

        self.assertNotIn("RAILWAY_TOKEN", env)
        self.assertEqual(env["RAILWAY_API_TOKEN"], "account-token")
        self.assertEqual(railway_openclaw_deploy.auth_mode(env), "account_token")

    def test_build_deploy_command_targets_openclaw_deploy_path(self) -> None:
        args = railway_openclaw_deploy.build_parser().parse_args(
            [
                "--deploy-path",
                "/tmp/openclaw",
                "--message",
                "Deploy analytics fix",
            ]
        )
        target = railway_openclaw_deploy.RailwayTarget(
            project="project-id",
            environment="environment-id",
            service="service-id",
            source="test",
        )

        command = railway_openclaw_deploy.build_deploy_command(args, target)

        self.assertEqual(
            command,
            [
                "railway",
                "up",
                "--detach",
                "--message",
                "Deploy analytics fix",
                "--service",
                "service-id",
                "--environment",
                "environment-id",
                "--project",
                "project-id",
            ],
        )

    def test_main_reports_status_check_failure_without_deploying(self) -> None:
        target = railway_openclaw_deploy.RailwayTarget(
            project="project-id",
            environment="environment-id",
            service="service-id",
            source="test",
        )

        stdout = StringIO()
        with patch("scripts.railway_openclaw_deploy.resolve_target", return_value=target):
            with patch(
                "scripts.railway_openclaw_deploy.run_command",
                return_value={"ok": False, "exit_code": 1, "stdout": "", "stderr": "invalid_grant"},
            ) as run:
                with redirect_stdout(stdout):
                    exit_code = railway_openclaw_deploy.main([])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 3)
        self.assertEqual(payload["reason"], "railway_auth_or_link_check_failed")
        self.assertFalse(payload["deploy_requested"])
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0], ["railway", "status", "--json"])

    def test_main_deploy_runs_from_deploy_path_so_railway_toml_is_used(self) -> None:
        with TemporaryDirectory() as tmpdir:
            deploy_path = Path(tmpdir) / "openclaw"
            deploy_path.mkdir()
            target = railway_openclaw_deploy.RailwayTarget(
                project="project-id",
                environment="environment-id",
                service="service-id",
                source="test",
            )

            def fake_run(command, *, cwd, env, timeout_seconds):
                if command == ["railway", "status", "--json"]:
                    return {"ok": True, "exit_code": 0, "stdout": "{}", "stderr": ""}
                if command[0] == "bash":
                    return {"ok": True, "exit_code": 0, "stdout": "prepared", "stderr": ""}
                return {"ok": True, "exit_code": 0, "stdout": '{"deploymentId":"dep"}', "stderr": ""}

            stdout = StringIO()
            with patch("scripts.railway_openclaw_deploy.resolve_target", return_value=target):
                with patch("scripts.railway_openclaw_deploy.run_command", side_effect=fake_run) as run:
                    with redirect_stdout(stdout):
                        exit_code = railway_openclaw_deploy.main(
                            ["--deploy", "--deploy-path", str(deploy_path)]
                        )

            self.assertEqual(exit_code, 0)
            deploy_call = run.call_args_list[-1]
            self.assertEqual(deploy_call.kwargs["cwd"], deploy_path)
            self.assertEqual(deploy_call.args[0][0:2], ["railway", "up"])
            self.assertNotIn("--path-as-root", deploy_call.args[0])


if __name__ == "__main__":
    unittest.main()
