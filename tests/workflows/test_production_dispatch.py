import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "dispatch_production.sh"
IMAGE = "ghcr.io/kamyar/emoji-maker@sha256:" + "a" * 64


class ProductionDispatchTests(unittest.TestCase):
    def setUp(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.directory = Path(temporary_directory.name)
        self.calls_file = self.directory / "calls.jsonl"
        stub = f"#!{sys.executable}\n" + """
import json
import os
from pathlib import Path
import sys

command = Path(sys.argv[0]).name
with open(os.environ["MOCK_CALLS"], "a") as calls:
    calls.write(json.dumps([command, *sys.argv[1:]]) + "\\n")
if command == "docker":
    print(os.environ["MOCK_IMAGE"])
    sys.exit(int(os.environ.get("MOCK_DOCKER_EXIT", "0")))
sys.exit(int(os.environ.get("MOCK_GH_EXIT", "0")))
"""
        for command in ("docker", "gh"):
            executable = self.directory / command
            executable.write_text(stub)
            executable.chmod(0o755)
        self.environment = {
            "PATH": f"{self.directory}{os.pathsep}{os.defpath}",
            "GITHUB_REPOSITORY": "kamyar/emoji-maker",
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_SHA": "b" * 40,
            "GH_TOKEN": "test-deployment-token",
            "MOCK_CALLS": str(self.calls_file),
            "MOCK_IMAGE": IMAGE,
        }

    def dispatch(self):
        return subprocess.run(
            ["bash", str(SCRIPT)],
            env=self.environment,
            capture_output=True,
            text=True,
            check=False,
        )

    def calls(self):
        if not self.calls_file.exists():
            return []
        return [json.loads(line) for line in self.calls_file.read_text().splitlines()]

    def test_dispatches_the_published_digest(self):
        result = self.dispatch()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.calls(),
            [
                [
                    "docker", "image", "inspect",
                    "ghcr.io/kamyar/emoji-maker:" + self.environment["GITHUB_SHA"],
                    "--format", "{{index .RepoDigests 0}}",
                ],
                [
                    "gh", "api", "--hostname", "github.com", "--method", "POST",
                    "repos/kamyar/kamyme/dispatches",
                    "--header", "Accept: application/vnd.github+json",
                    "--header", "X-GitHub-Api-Version: 2022-11-28",
                    "--raw-field", "event_type=emoji-maker-image",
                    "--raw-field", "client_payload[service]=emoji-maker",
                    "--raw-field", "client_payload[image]=" + IMAGE,
                ],
            ],
        )
        self.assertIn("Production deployment requested", result.stdout)
        self.assertNotIn(self.environment["GH_TOKEN"], result.stdout + result.stderr)

    def test_rejects_a_missing_token(self):
        del self.environment["GH_TOKEN"]
        result = self.dispatch()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("KAMYME_DEPLOY_TOKEN", result.stdout)
        self.assertEqual(self.calls(), [])

    def test_rejects_an_empty_token(self):
        self.environment["GH_TOKEN"] = ""
        self.assertNotEqual(self.dispatch().returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_rejects_a_missing_commit(self):
        del self.environment["GITHUB_SHA"]
        self.assertNotEqual(self.dispatch().returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_rejects_other_branches(self):
        self.environment["GITHUB_REF"] = "refs/heads/feature"
        self.assertNotEqual(self.dispatch().returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_rejects_other_repositories(self):
        self.environment["GITHUB_REPOSITORY"] = "other/emoji-maker"
        self.assertNotEqual(self.dispatch().returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_rejects_invalid_digests(self):
        for image in (
            "",
            "ghcr.io/kamyar/emoji-maker:main",
            "ghcr.io/kamyar/emoji-maker@sha256:" + "a" * 63,
            "ghcr.io/kamyar/emoji-maker@sha256:" + "g" * 64,
            "ghcr.io/kamyar/other@sha256:" + "a" * 64,
            IMAGE + "\nextra",
        ):
            with self.subTest(image=image):
                self.calls_file.unlink(missing_ok=True)
                self.environment["MOCK_IMAGE"] = image
                self.assertNotEqual(self.dispatch().returncode, 0)
                self.assertEqual([call[0] for call in self.calls()], ["docker"])

    def test_does_not_dispatch_after_an_inspection_failure(self):
        self.environment["MOCK_DOCKER_EXIT"] = "1"
        self.assertNotEqual(self.dispatch().returncode, 0)
        self.assertEqual([call[0] for call in self.calls()], ["docker"])

    def test_reports_a_failed_dispatch(self):
        self.environment["MOCK_GH_EXIT"] = "1"
        result = self.dispatch()
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Production deployment requested", result.stdout)


if __name__ == "__main__":
    unittest.main()
