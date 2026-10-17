"""The passphrase factor (ADR D-49): scrypt with a per-user salt, compared in constant time."""

import pytest

from app.core import passphrase as pp


def test_a_hash_records_its_parameters_and_a_salt():
    stored = pp.hash_passphrase("correct horse battery staple")
    scheme, n, r, p, salt, digest = stored.split("$")
    assert (scheme, n, r, p) == ("scrypt", "16384", "8", "1")
    assert salt and digest
    assert "correct" not in stored


def test_the_same_passphrase_gets_a_different_salt_each_time():
    assert pp.hash_passphrase("same words here") != pp.hash_passphrase("same words here")


def test_verify_accepts_the_right_passphrase_and_refuses_others():
    stored = pp.hash_passphrase("correct horse battery staple")
    assert pp.verify_passphrase(stored, "correct horse battery staple")
    assert not pp.verify_passphrase(stored, "correct horse battery stapl")
    assert not pp.verify_passphrase(stored, "")


def test_no_stored_hash_never_verifies_but_still_does_the_work(monkeypatch):
    calls = []
    real = pp._derive
    monkeypatch.setattr(pp, "_derive", lambda *a: calls.append(1) or real(*a))
    assert not pp.verify_passphrase(None, "anything at all")
    assert calls == [1]  # an unknown user costs as much as a known one


@pytest.mark.parametrize("broken", ["", "scrypt$1$2", "md5$x$y$z$a$b", "scrypt$a$b$c$d$e"])
def test_a_malformed_stored_hash_is_refused_not_an_error(broken):
    assert not pp.verify_passphrase(broken, "anything at all")


@pytest.mark.parametrize("weak", ["short", " " * 20, "x" * 129])
def test_weak_or_absurd_passphrases_cannot_be_set(weak):
    with pytest.raises(ValueError):
        pp.hash_passphrase(weak)


def test_generated_passphrases_are_long_and_differ():
    first, second = pp.generate_passphrase(), pp.generate_passphrase()
    assert first != second
    assert len(first) >= pp.MIN_LENGTH
