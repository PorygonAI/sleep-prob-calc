"""Exercise the data publisher against temporary local Git repositories."""
import contextlib
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import publish_ralts_probability as publisher
import run_pipeline


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True, stderr=subprocess.STDOUT).strip()


class PublisherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.repo = self.base / "repo"
        self.remote = self.base / "remote.git"
        self.repo.mkdir()
        self.remote.mkdir()
        git(self.remote, "init", "--bare", "--initial-branch=main")
        git(self.repo, "init", "--initial-branch=main")
        git(self.repo, "config", "user.email", "test@example.invalid")
        git(self.repo, "config", "user.name", "Test")
        git(self.repo, "remote", "add", "origin", str(self.remote))
        (self.repo / "note.txt").write_text("initial", encoding="utf-8")
        git(self.repo, "add", "note.txt")
        git(self.repo, "commit", "-m", "initial")
        self.source = ROOT / publisher.CSV_NAME

    def publish(self, *extra):
        args = ["publish", "--source-csv", str(self.source), "--repo-dir", str(self.repo), *extra]
        with patch.object(sys, "argv", args), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return publisher.main()

    def test_only_csv_is_committed_and_unchanged_data_has_no_extra_commit(self):
        (self.repo / "note.txt").write_text("unrelated edit", encoding="utf-8")
        self.assertEqual(self.publish(), 0)
        self.assertEqual(git(self.repo, "show", "--pretty=format:", "--name-only", "HEAD"), publisher.CSV_NAME)
        head = git(self.repo, "rev-parse", "HEAD")
        self.assertEqual(self.publish(), 0)
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), head)
        self.assertEqual(git(self.remote, "rev-parse", "main"), head)
        self.assertIn("note.txt", git(self.repo, "status", "--short"))

    def test_push_failure_can_be_retried_without_new_data(self):
        git(self.repo, "remote", "set-url", "origin", str(self.base / "missing.git"))
        self.assertEqual(self.publish(), 1)
        head = git(self.repo, "rev-parse", "HEAD")
        git(self.repo, "remote", "set-url", "origin", str(self.remote))
        self.assertEqual(self.publish(), 0)
        self.assertEqual(git(self.remote, "rev-parse", "main"), head)
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), head)

    def test_staged_changes_stop_publish_before_copying(self):
        (self.repo / "note.txt").write_text("staged edit", encoding="utf-8")
        git(self.repo, "add", "note.txt")
        self.assertEqual(self.publish(), 1)
        self.assertFalse((self.repo / publisher.CSV_NAME).exists())

    def test_invalid_csv_is_not_copied(self):
        self.source = self.base / "invalid.csv"
        self.source.write_text("<html>error</html>", encoding="utf-8")
        self.assertEqual(self.publish(), 1)
        self.assertFalse((self.repo / publisher.CSV_NAME).exists())

    def test_copy_only_does_not_commit(self):
        head = git(self.repo, "rev-parse", "HEAD")
        self.assertEqual(self.publish("--copy-only"), 0)
        self.assertTrue((self.repo / publisher.CSV_NAME).exists())
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), head)


class PipelineTests(unittest.TestCase):
    def test_stages_scrape_then_publish_without_probability_calculation(self):
        with patch.object(sys, "argv", ["run_pipeline", "--copy-only"]), patch.object(run_pipeline, "run_stage") as stage:
            self.assertEqual(run_pipeline.main(), 0)
        commands = [call.args[1] for call in stage.call_args_list]
        self.assertEqual(len(commands), 2)
        self.assertTrue(commands[0][1].endswith("scrape_lapis_lakeside_spo.py"))
        self.assertTrue(commands[1][1].endswith("publish_ralts_probability.py"))
        self.assertIn("--copy-only", commands[1])

    def test_scrape_failure_prevents_publish(self):
        with patch.object(sys, "argv", ["run_pipeline"]), patch.object(run_pipeline, "run_stage", side_effect=subprocess.CalledProcessError(1, ["scrape"])) as stage:
            self.assertEqual(run_pipeline.main(), 1)
        self.assertEqual(stage.call_count, 1)


if __name__ == "__main__":
    unittest.main()
