from app.security.passwords import hash_password, needs_rehash, verify_password


def test_hash_and_verify_round_trip() -> None:
    password_hash = hash_password("correct-horse-battery-staple")
    assert verify_password("correct-horse-battery-staple", password_hash)
    assert not needs_rehash(password_hash)


def test_verify_rejects_wrong_password() -> None:
    password_hash = hash_password("secret-one")
    assert not verify_password("secret-two", password_hash)
