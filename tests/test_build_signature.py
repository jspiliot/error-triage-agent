import re

from scripts.build_signature import build_signature


def test_same_input_produces_same_signature():
    sig1 = build_signature("NullPointerException", ["UserService.java:42"])
    sig2 = build_signature("NullPointerException", ["UserService.java:42"])
    assert sig1 == sig2


def test_different_frames_produce_different_signatures():
    sig1 = build_signature("NullPointerException", ["UserService.java:42"])
    sig2 = build_signature("NullPointerException", ["UserService.java:99"])
    assert sig1 != sig2


def test_signature_is_branch_name_safe():
    sig = build_signature("Null Pointer: Exception!!", ["Some Weird File.java:1"])
    assert re.fullmatch(r"[a-z0-9-]+", sig)


def test_signature_is_length_bounded():
    sig = build_signature("A" * 200, ["B" * 200 + ".java:1"])
    assert len(sig) <= 50


def test_signature_includes_hash_suffix():
    sig = build_signature("TimeoutError", ["worker.py:10"])
    _, _, suffix = sig.rpartition("-")
    assert len(suffix) == 12
