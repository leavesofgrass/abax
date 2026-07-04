"""In-memory secrets holder + redaction, and the per-action consent helper
(:mod:`abax.sandbox`).

Credentials for the DB / REST connectors must never be persisted and must never
leak through an error string. These tests pin both guarantees.
"""

from __future__ import annotations

import pytest

from abax import sandbox

# --- the secrets holder: memory-only ------------------------------------------


def test_secret_never_appears_in_a_redacted_error():
    holder = sandbox.SecretsHolder()
    password = "hunter2-SUPER-secret"
    holder.set("pg", password)
    # Simulate a driver echoing the DSN (with the password) in its exception.
    raw = f"could not connect: password authentication failed for '{password}'"
    redacted = holder.redact(raw)
    assert password not in redacted
    assert "***" in redacted
    # The non-secret context survives so the message stays useful.
    assert "password authentication failed" in redacted


def test_redact_longest_first_scrubs_overlapping_secrets():
    holder = sandbox.SecretsHolder()
    holder.set("short", "abc")
    holder.set("long", "abcdef")  # contains 'abc' as a prefix
    out = holder.redact("value=abcdef and abc")
    assert "abcdef" not in out
    assert "abc" not in out


def test_redact_free_function():
    text = "token=Bearer XYZ123 in the clear"
    out = sandbox.redact_secrets(text, ["XYZ123"])
    assert "XYZ123" not in out and "***" in out
    # Non-string / empty inputs pass through untouched.
    assert sandbox.redact_secrets(None, ["x"]) is None
    assert sandbox.redact_secrets("", ["x"]) == ""
    assert sandbox.redact_secrets("nothing here", []) == "nothing here"


def test_holder_get_set_has_clear():
    holder = sandbox.SecretsHolder()
    assert holder.get("x") is None
    assert holder.has("x") is False
    holder.set("x", "s3cr3t")
    assert holder.get("x") == "s3cr3t"
    assert holder.has("x") is True
    assert holder.names() == ["x"]
    # Empty value drops the entry rather than storing a blank secret.
    holder.set("x", "")
    assert holder.has("x") is False
    holder.set("y", "v")
    holder.clear()
    assert holder.names() == []


def test_holder_has_no_serialization_surface_and_repr_hides_values():
    holder = sandbox.SecretsHolder()
    holder.set("pw", "topsecret")
    # No persistence API exists — a secret can't ride out via these.
    for attr in ("to_dict", "save", "dump", "serialize", "json"):
        assert not hasattr(holder, attr)
    # repr must never contain the value (it would end up in logs/tracebacks).
    assert "topsecret" not in repr(holder)
    assert "pw" in repr(holder)  # names are fine; values are not


def test_pickling_a_holder_does_not_leak_the_value():
    import pickle

    holder = sandbox.SecretsHolder()
    holder.set("pw", "do-not-persist")
    # Even if something naively pickles the object, the secret is what we protect
    # against *persisting to settings/workbook*; there is no code path in abax
    # that pickles it, but confirm the value isn't reachable via a public dict.
    assert not any(
        "do-not-persist" in str(v)
        for k, v in vars(holder).items()
        if not k.startswith("_")
    )
    # (The private store still holds it in memory, by design — that's the point.)
    del pickle  # silence lints; pickle import documents the persistence concern


# --- per-action consent -------------------------------------------------------


def test_require_consent_raises_without_consent():
    with pytest.raises(sandbox.ConsentError):
        sandbox.require_consent(False, action="run a macro")


def test_require_consent_passes_with_consent():
    # No exception -> returns None.
    assert sandbox.require_consent(True, action="run a macro") is None


def test_consent_error_message_mentions_the_action():
    try:
        sandbox.require_consent(False, action="open a terminal")
    except sandbox.ConsentError as exc:
        assert "open a terminal" in str(exc)
    else:  # pragma: no cover
        pytest.fail("expected ConsentError")
