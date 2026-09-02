"""Tests for P0 auth hardening + parent-child chunk expansion."""
from __future__ import annotations

import os
import sys
import tempfile
import hashlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _isolated_engine():
    fd, path = tempfile.mkstemp(prefix="hd_test_", suffix=".sqlite")
    os.close(fd)
    from sqlmodel import SQLModel, create_engine, text as _text
    eng = create_engine(
        f"sqlite:///{path}",
        connect_args={"check_same_thread": False},
    )
    from app.storage.db import User
    from app.api.auth_security import RevokedToken
    SQLModel.metadata.create_all(eng)
    # chunk_fts is only needed by the parent-child tests; create lazily.
    return eng, path


def _ensure_fts(eng):
    """Create the chunk_fts table if it does not exist."""
    from sqlmodel import text
    with eng.begin() as conn:
        conn.execute(text(
            "CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5("
            "  note_id UNINDEXED,"
            "  chunk_index UNINDEXED,"
            "  content,"
            "  tokenize = 'unicode61 remove_diacritics 2'"
            ")"
        ))


def _install_engine(eng):
    import app.storage.db as db_mod
    import app.api.auth_security as sec_mod
    db_mod._engine = eng
    sec_mod.get_engine = lambda: eng


# ============ Auth: token blacklist ============
def test_revoke_then_block():
    from app.api.auth_security import revoke_token, is_revoked
    eng, path = _isolated_engine()
    _install_engine(eng)
    fake = "user.123.abcdef0123456789"
    assert not is_revoked(fake)
    assert revoke_token(fake, user_id=1, reason="logout")
    assert is_revoked(fake)
    assert not revoke_token(fake)
    eng.dispose()
    try: os.remove(path)
    except OSError: pass
    print("PASS test_revoke_then_block")


def test_revoke_rejects_short_token():
    from app.api.auth_security import revoke_token, is_revoked
    eng, path = _isolated_engine()
    _install_engine(eng)
    # Empty token or token without dots -> sig empty -> safe reject.
    assert not revoke_token(""), 'empty token must not be stored'
    assert not revoke_token("no_dots_at_all"), 'token with no dots must not be stored'
    assert not is_revoked("no_dots_at_all"), 'no-dots token must not appear as revoked'
    eng.dispose()
    try: os.remove(path)
    except OSError: pass
    print("PASS test_revoke_rejects_short_token")


# ============ Rate limiter ============
def test_rate_limiter_blocks_burst():
    from app.api.auth_security import RateLimiter
    rl = RateLimiter()
    rl._route_limits = {"test": (3, 0.01)}
    ok_count = 0
    blocked_count = 0
    for _ in range(10):
        ok, _ = rl.check("127.0.0.1", "test")
        if ok:
            ok_count += 1
        else:
            blocked_count += 1
    assert ok_count == 3, f"got {ok_count}"
    assert blocked_count == 7, f"got {blocked_count}"
    print("PASS test_rate_limiter_blocks_burst")


def test_rate_limiter_per_ip():
    from app.api.auth_security import RateLimiter
    rl = RateLimiter()
    rl._route_limits = {"test": (2, 0.01)}
    for _ in range(2):
        ok, _ = rl.check("1.2.3.4", "test")
        assert ok
    ok, _ = rl.check("1.2.3.4", "test")
    assert not ok
    ok, _ = rl.check("5.6.7.8", "test")
    assert ok
    print("PASS test_rate_limiter_per_ip")


# ============ Parent-child chunk expansion ============
def test_merge_neighboring_hits_groups_same_note():
    eng, path = _isolated_engine()
    from sqlmodel import text
    import app.storage.hybrid as hyb
    _install_engine(eng)
    _ensure_fts(eng)
    with eng.begin() as conn:
        for i, content in enumerate(["alpha chunk", "beta chunk", "gamma chunk"]):
            conn.execute(text(
                "INSERT INTO chunk_fts (note_id, chunk_index, content) VALUES (:n, :i, :c)"
            ), {"n": "note_a", "i": i, "c": content})

    hits = [
        {"note_id": "note_a", "chunk_index": 0, "text": "alpha chunk", "final_score": 0.8},
        {"note_id": "note_a", "chunk_index": 1, "text": "beta chunk", "final_score": 0.7},
        {"note_id": "note_b", "chunk_index": 0, "text": "other doc", "final_score": 0.5},
    ]
    merged = hyb.merge_neighboring_hits(hits, window=2)
    note_a_records = [h for h in merged if h.get("note_id") == "note_a"]
    assert len(note_a_records) == 1, f"got {len(note_a_records)}"
    assert set(note_a_records[0].get("sibling_chunk_indices") or []) == {1}
    assert note_a_records[0].get("merged_children") == 2
    note_b_records = [h for h in merged if h.get("note_id") == "note_b"]
    assert len(note_b_records) == 1
    eng.dispose()
    try: os.remove(path)
    except OSError: pass
    print("PASS test_merge_neighboring_hits_groups_same_note")


def test_expand_search_results_adds_context():
    eng, path = _isolated_engine()
    from sqlmodel import text
    import app.storage.hybrid as hyb
    _install_engine(eng)
    _ensure_fts(eng)
    with eng.begin() as conn:
        for i, content in enumerate([
            "alpha alpha alpha",
            "beta beta beta",
            "gamma gamma gamma",
            "delta delta delta",
        ]):
            conn.execute(text(
                "INSERT INTO chunk_fts (note_id, chunk_index, content) VALUES (:n, :i, :c)"
            ), {"n": "note_x", "i": i, "c": content})

    hits = [{"note_id": "note_x", "chunk_index": 2, "text": "gamma gamma gamma", "final_score": 0.9}]
    expanded = hyb.expand_search_results(hits, window=2)
    assert len(expanded) == 1
    assert "alpha" in expanded[0]["text"]
    assert "beta" in expanded[0]["text"]
    assert "gamma" in expanded[0]["text"]
    assert "delta" in expanded[0]["text"]
    assert expanded[0]["context_window"] == 2
    eng.dispose()
    try: os.remove(path)
    except OSError: pass
    print("PASS test_expand_search_results_adds_context")


def test_expand_window_zero_disables():
    eng, path = _isolated_engine()
    from sqlmodel import text
    import app.storage.hybrid as hyb
    _install_engine(eng)
    _ensure_fts(eng)
    with eng.begin() as conn:
        for i, content in enumerate(["a", "b", "c"]):
            conn.execute(text(
                "INSERT INTO chunk_fts (note_id, chunk_index, content) VALUES (:n, :i, :c)"
            ), {"n": "n1", "i": i, "c": content})

    hits = [{"note_id": "n1", "chunk_index": 1, "text": "b", "final_score": 0.5}]
    expanded = hyb.expand_search_results(hits, window=0)
    assert expanded[0]["text"] == "b"
    eng.dispose()
    try: os.remove(path)
    except OSError: pass
    print("PASS test_expand_window_zero_disables")


# ============ Auth helpers ============
def test_password_hash_unique_per_salt():
    salt1 = "salt1" * 16
    salt2 = "salt2" * 16
    pw = "password123"
    h1 = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt1.encode(), 100_000).hex()
    h2 = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt2.encode(), 100_000).hex()
    assert h1 != h2
    assert len(h1) == 64
    print("PASS test_password_hash_unique_per_salt")


def test_sig_suffix_extraction():
    from app.api.auth_security import _sig_suffix
    assert _sig_suffix("") == ""
    assert _sig_suffix("nope") == ""
    long_sig = "a" * 4 + "b" * 4 + "0123456789abcdef"
    assert _sig_suffix("1.2." + long_sig) == "0123456789abcdef"
    print("PASS test_sig_suffix_extraction")


def test_change_password_token_roundtrip():
    eng, path = _isolated_engine()
    _install_engine(eng)
    from app.api.auth import _hash_password, make_token, verify_token
    from app.storage.db import User
    from sqlmodel import Session
    salt = "x" * 32
    user = User(phone="13800138000", password_salt=salt,
                password_hash=_hash_password("correct-old", salt))
    with Session(eng) as s:
        s.add(user); s.commit(); s.refresh(user)
    tok = make_token(user.id)
    assert verify_token(tok) == user.id
    bad = tok[:-4] + "ZZZZ"
    assert verify_token(bad) is None
    eng.dispose()
    try: os.remove(path)
    except OSError: pass
    print("PASS test_change_password_token_roundtrip")


def main() -> int:
    test_names = sorted([k for k in globals().keys() if k.startswith("test_")])
    passed = 0
    failed = 0
    for name in test_names:
        try:
            globals()[name]()
            passed += 1
        except AssertionError as e:
            print(f"FAIL {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR {name}: {type(e).__name__}: {e}")
            failed += 1
    print("=" * 40)
    print(f"Passed: {passed}/{len(test_names)}  Failed: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())