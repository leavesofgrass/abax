"""Session-only credential store tests — :mod:`abax.core.livecreds`.

No network anywhere: the store is exercised in memory and the requests built
by ``build_request`` are inspected without ever being opened. Tests that
touch the process-wide ``CREDS`` singleton clear it in a ``finally`` so no
registration outlives its test.
"""

from __future__ import annotations

import pickle
import threading

import pytest

from abax.core.livecreds import CREDS, CredentialStore, build_request, redact

SECRET = "Bearer s3cr3t-t0ken-value"


# -- registration and lookup -------------------------------------------------

def test_lookup_matches_across_scheme_port_and_case():
    store = CredentialStore()
    store.set_headers("api.example.com", {"Authorization": SECRET})
    for url in (
        "http://api.example.com/v1",
        "https://api.example.com/v1?x=1",
        "https://api.example.com:8443/deep/path",
        "http://API.EXAMPLE.COM/casefold",
        "ws://api.example.com/feed",
    ):
        assert store.headers_for(url) == {"Authorization": SECRET}, url


def test_lookup_miss_returns_empty_dict():
    store = CredentialStore()
    store.set_headers("api.example.com", {"Authorization": SECRET})
    assert store.headers_for("https://other.example.com/") == {}
    assert store.headers_for("https://example.com/") == {}            # parent domain
    assert store.headers_for("https://sub.api.example.com/") == {}    # subdomain
    assert store.headers_for("https://api.example.com.evil.tld/") == {}  # suffix trick
    assert store.headers_for("") == {}                                # garbage in, {} out


def test_set_headers_accepts_url_and_host_port_forms():
    store = CredentialStore()
    store.set_headers("https://one.example:8443/some/path", {"X-A": "1"})
    store.set_headers("two.example:9000", {"X-B": "2"})
    store.set_headers("THREE.example", {"X-C": "3"})
    assert store.headers_for("http://one.example/") == {"X-A": "1"}
    assert store.headers_for("http://two.example/") == {"X-B": "2"}
    assert store.headers_for("http://three.example/") == {"X-C": "3"}
    assert len(store) == 3


def test_set_headers_replaces_previous_registration():
    store = CredentialStore()
    store.set_headers("h.example", {"Authorization": "Bearer old", "X-Extra": "1"})
    store.set_headers("h.example", {"Authorization": "Bearer new"})
    got = store.headers_for("https://h.example/")
    assert got == {"Authorization": "Bearer new"}   # rotated: old token + extras gone
    assert len(store) == 1


def test_set_headers_empty_mapping_removes_registration():
    store = CredentialStore()
    store.set_headers("h.example", {"Authorization": SECRET})
    store.set_headers("h.example", {})
    assert store.headers_for("https://h.example/") == {}
    assert len(store) == 0


def test_set_headers_rejects_bad_input():
    store = CredentialStore()
    with pytest.raises(ValueError):
        store.set_headers("", {"A": "1"})
    with pytest.raises(TypeError):
        store.set_headers("h.example", {"A": 1})        # non-str value
    with pytest.raises(TypeError):
        store.set_headers("h.example", {1: "x"})        # non-str name
    assert len(store) == 0


def test_headers_for_returns_a_copy():
    store = CredentialStore()
    store.set_headers("h.example", {"Authorization": SECRET})
    got = store.headers_for("https://h.example/")
    got["Authorization"] = "tampered"
    got["Injected"] = "nope"
    assert store.headers_for("https://h.example/") == {"Authorization": SECRET}


# -- clear / hosts / len -------------------------------------------------------

def test_clear_one_host_and_all():
    store = CredentialStore()
    store.set_headers("a.example", {"X": "1"})
    store.set_headers("b.example", {"Y": "2"})
    store.clear("A.EXAMPLE")                    # case-insensitive, host form
    assert store.hosts() == ["b.example"]
    store.clear("never-registered.example")     # unknown host: no-op, no raise
    assert len(store) == 1
    store.clear()                               # everything
    assert store.hosts() == [] and len(store) == 0


def test_hosts_lists_names_never_values():
    store = CredentialStore()
    store.set_headers("b.example", {"Authorization": SECRET})
    store.set_headers("a.example", {"X-Api-Key": "k-12345"})
    assert store.hosts() == ["a.example", "b.example"]  # sorted, names only
    listing = str(store.hosts()) + repr(store)
    assert SECRET not in listing
    assert "s3cr3t" not in listing
    assert "k-12345" not in listing
    assert "Authorization" not in listing  # header *names* stay private too


# -- no serialization surface ----------------------------------------------------

def test_no_serialization_surface_exists():
    store = CredentialStore()
    store.set_headers("h.example", {"Authorization": SECRET})
    for name in ("to_dict", "as_dict", "from_dict", "to_json", "from_json",
                 "save", "load", "dump", "dumps", "serialize", "deserialize",
                 "export"):
        assert not hasattr(store, name), name
        assert not hasattr(CredentialStore, name), name


def test_pickle_is_refused():
    store = CredentialStore()
    store.set_headers("h.example", {"Authorization": SECRET})
    with pytest.raises(TypeError):
        pickle.dumps(store)


# -- thread-safety smoke ----------------------------------------------------------

def test_concurrent_set_and_lookup_smoke():
    store = CredentialStore()
    errors: list[Exception] = []

    def worker(n: int) -> None:
        try:
            for i in range(200):
                host = f"h{(n + i) % 4}.example"
                store.set_headers(host, {"X-Token": f"tok-{n}-{i}"})
                got = store.headers_for(f"https://{host}:8443/path")
                assert "X-Token" in got     # some thread's token, never absent
                store.hosts()
                len(store)
        except Exception as exc:  # noqa: BLE001 — surfaced via the errors list
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert store.hosts() == [f"h{i}.example" for i in range(4)]


# -- build_request -------------------------------------------------------------------

def test_build_request_defaults_plus_overlay():
    # NB: urllib's Request stores header names str.capitalize()d, hence the
    # "User-agent" / "X-api-key" spellings in the get_header calls below.
    CREDS.set_headers("api.example.com", {"Authorization": SECRET, "X-API-Key": "k-9"})
    try:
        req = build_request("https://api.example.com/v1", accept="application/json")
        assert req.full_url == "https://api.example.com/v1"
        assert req.get_header("User-agent") == "abax-livedata/1"
        assert req.get_header("Accept") == "application/json"
        assert req.get_header("Authorization") == SECRET
        assert req.get_header("X-api-key") == "k-9"
    finally:
        CREDS.clear()


def test_build_request_without_creds_or_accept():
    req = build_request("https://plain.example/x", user_agent="abax-webservice/1")
    assert req.get_header("User-agent") == "abax-webservice/1"
    assert req.get_header("Accept") is None
    assert req.get_header("Authorization") is None


def test_build_request_overlay_wins_over_defaults():
    CREDS.set_headers("api.example.com", {"User-Agent": "custom-agent/2"})
    try:
        req = build_request("https://api.example.com/v1")
        assert req.get_header("User-agent") == "custom-agent/2"
    finally:
        CREDS.clear()


def test_creds_is_a_module_level_store():
    assert isinstance(CREDS, CredentialStore)
    CREDS.set_headers("tmp.example", {"X": "1"})
    try:
        assert "tmp.example" in CREDS.hosts()
    finally:
        CREDS.clear("tmp.example")
    assert "tmp.example" not in CREDS.hosts()


# -- redact ------------------------------------------------------------------------------

def test_redact_masks_all_but_head():
    assert redact("Bearer eyJhbGciOi...") == "Bear****"
    assert redact("abcde") == "abcd****"
    long = redact("Bearer " + "x" * 64)
    assert "x" not in long                # tail fully gone, length hidden
    assert long == "Bear****"


def test_redact_short_values_fully_masked():
    for short in ("", "a", "tok", "abcd", None):
        assert redact(short) == "****", short
