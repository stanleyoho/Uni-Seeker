from app.auth import create_access_token, decode_token, hash_password, verify_password


def test_hash_and_verify() -> None:
    hashed = hash_password("test123")
    assert verify_password("test123", hashed)
    assert not verify_password("wrong", hashed)


def test_create_and_decode_token() -> None:
    token = create_access_token(user_id=1, email="test@example.com")
    payload = decode_token(token)
    assert payload["sub"] == "1"
    assert payload["email"] == "test@example.com"


def test_hash_different_each_time() -> None:
    h1 = hash_password("same")
    h2 = hash_password("same")
    assert h1 != h2  # bcrypt uses random salt
