"""Tests for musubu_tar_preflight."""
import gzip
import json
import tarfile
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest import mock

from scripts import musubu_tar_preflight as preflight


class TarPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def _write_tar(self, resource: str, pages: list[int]) -> Path:
        path = self.root / f"{resource}_pages_{pages[0]:05d}-{pages[-1]:05d}.tar.gz"
        buf = BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            for page in pages:
                name = f"{resource}_page_{page:05d}.json"
                raw = gzip.compress(json.dumps({"page": page}).encode())
                ti = tarfile.TarInfo(name=name)
                ti.size = len(raw)
                tar.addfile(ti, BytesIO(raw))
        path.write_bytes(buf.getvalue())
        return path

    def test_expected_pages_companies_gap_70(self):
        exp = preflight.expected_pages("companies", 69, 71)
        self.assertEqual(exp, [69, 71])

    def test_protected_companies_tar(self):
        self.assertTrue(
            preflight.is_protected_drive_name("companies_pages_00001-00200.tar.gz")
        )
        self.assertFalse(
            preflight.is_protected_drive_name("companies_pages_01834-02033.tar.gz")
        )

    @mock.patch.object(preflight, "tar_is_stable", return_value=True)
    def test_preflight_pass(self, _s):
        pages = list(range(4, 204))
        tar = self._write_tar("key_people", pages)
        argv = ["prog", str(tar), "--skip-drive", "--skip-queue", "--stable-sec", "0"]
        with mock.patch.object(preflight.sys, "argv", argv):
            preflight.main()
