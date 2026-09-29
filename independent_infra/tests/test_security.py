from app.security import generate_license_key, license_digest, masked_key


def test_keys_are_random_and_not_exposed_by_preview() -> None:
    keys = {generate_license_key() for _ in range(100)}
    assert len(keys) == 100
    for key in keys:
        assert key.startswith("ALBIONMKT-")
        assert len(key.split("-")) == 5
        assert key not in masked_key(key)


def test_digest_is_stable_and_case_insensitive() -> None:
    pepper = "p" * 32
    assert license_digest("  AlbionMKT-ABCDE  ", pepper) == license_digest(
        "ALBIONMKT-ABCDE", pepper
    )

