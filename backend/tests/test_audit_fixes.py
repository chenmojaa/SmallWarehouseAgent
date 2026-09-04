"""Regression tests for the high-priority security/correctness fixes."""
from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


class TestFtsSanitization(unittest.TestCase):
    def test_phrase_quote_and_strip(self):
        from app.storage.db import _fts_sanitize_phrase, _fts_quote
        self.assertEqual(_fts_sanitize_phrase('foo"bar OR baz'), "foo bar OR baz")
        self.assertEqual(_fts_sanitize_phrase("foo(bar):*"), "foo bar")
        self.assertEqual(_fts_sanitize_phrase('"""'), "")
        self.assertEqual(_fts_sanitize_phrase("个人知识"), "个人知识")
        self.assertEqual(_fts_quote('a"b'), '"a""b"')


class TestBucketAtomicity(unittest.TestCase):
    def test_under_concurrent_load(self):
        import threading
        from app.api.auth_security import _Bucket
        b = _Bucket(capacity=10, refill_per_sec=0.001)
        ok = 0
        lock = threading.Lock()

        def hammer():
            nonlocal ok
            allowed, _ = b.hit()
            if allowed:
                with lock:
                    ok += 1

        threads = [threading.Thread(target=hammer) for _ in range(50)]
        for t in threads: t.start()
        for t in threads: t.join()
        self.assertLessEqual(ok, 11)
        self.assertGreaterEqual(ok, 10)


class TestSkillIdSlug(unittest.TestCase):
    def test_load_skill_rejects_traversal(self):
        from app.agent.tools import skill_tools
        self.assertIsNone(skill_tools._read_skill("../etc/passwd"))
        self.assertIsNone(skill_tools._read_skill("/etc/passwd"))
        self.assertIsNone(skill_tools._read_skill("foo/bar"))
        self.assertIsNone(skill_tools._read_skill("a" * 200))


class TestSsrfGuard(unittest.TestCase):
    def test_blocks_localhost_and_metadata(self):
        from app.tools.fetch_url import _is_blocked_host
        self.assertTrue(_is_blocked_host("localhost"))
        self.assertTrue(_is_blocked_host("127.0.0.1"))
        self.assertTrue(_is_blocked_host("0.0.0.0"))
        self.assertTrue(_is_blocked_host("metadata.google.internal"))


if __name__ == "__main__":
    unittest.main()
