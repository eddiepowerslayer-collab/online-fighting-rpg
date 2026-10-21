import pytest

from shared.protocol import ProtocolError, decode, encode, field


def test_encode_decode_roundtrip_is_newline_framed():
    raw = encode({"t": "ping", "id": 3})
    assert raw.endswith(b"\n") and raw.count(b"\n") == 1
    assert decode(raw) == {"t": "ping", "id": 3}


@pytest.mark.parametrize("bad", [b"not json", b"[1,2]", b'"str"', b'{"id": 1}', b'{"t": 5}', b'{"t": "' + b"x" * 40 + b'"}', b"\xff\xfe"])
def test_decode_rejects_malformed(bad):
    with pytest.raises(ProtocolError):
        decode(bad)


def test_field_validation():
    msg = {"a": 5, "b": "hello", "c": True, "d": 99}
    assert field(msg, "a", int, lo=1, hi=10) == 5
    assert field(msg, "missing", int, default=7) == 7
    for args in [("a", int, {"lo": 6}), ("b", int, {}), ("b", str, {"maxlen": 3}), ("c", int, {}), ("d", int, {"hi": 50}),
                 ("nope", int, {})]:
        with pytest.raises(ProtocolError):
            field(msg, args[0], args[1], **args[2])
