from fc_manager.redact import MASK, Credentials, redact, register


def test_registered_secret_is_masked():
    register("s3cr3t-value")
    assert redact("error: s3cr3t-value leaked") == f"error: {MASK} leaked"


def test_short_values_are_not_registered():
    register("abc")
    assert redact("abc") == "abc"


def test_authorization_header_forms_are_masked():
    samples = [
        "Authorization: Token abc123:def456",
        "{'Authorization': 'Token abc123:def456'}",
        '"authorization": "token abc123:def456"',
        "authorization=Bearer xyz",
    ]
    for sample in samples:
        out = redact(sample)
        assert "abc123" not in out and "def456" not in out and "xyz" not in out, out
        assert MASK in out


def test_credentials_repr_and_str_hide_values():
    creds = Credentials("key-AAAA1111", "secret-BBBB2222")
    for text in (repr(creds), str(creds), f"{creds}", f"{creds!r}"):
        assert "AAAA1111" not in text and "BBBB2222" not in text
        assert MASK in text


def test_credentials_register_themselves():
    creds = Credentials("key-CCCC3333", "secret-DDDD4444")
    assert redact(creds.authorization()) == f"Token {MASK}:{MASK}"
