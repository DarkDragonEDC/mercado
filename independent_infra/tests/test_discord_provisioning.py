from scripts.provision_discord_server import (
    CATEGORY_SPECS,
    ROLE_SPECS,
    TEXT_CHANNELS,
    VIEW_CHANNEL,
    VOICE_CHANNELS,
    category_overwrites,
)


def role_ids() -> dict[str, str]:
    return {spec["name"]: str(index + 100) for index, spec in enumerate(ROLE_SPECS)}


def test_server_spec_has_unique_names_and_expected_totals() -> None:
    category_names = [spec["name"] for spec in CATEGORY_SPECS]
    text_names = [name for _category, name, _topic in TEXT_CHANNELS]
    voice_names = [name for _category, name in VOICE_CHANNELS]

    assert len(category_names) == len(set(category_names)) == 5
    assert len(text_names) == len(set(text_names)) == 20
    assert len(voice_names) == len(set(voice_names)) == 3
    assert {spec["name"] for spec in ROLE_SPECS} == {
        "🎓・Fundador",
        "🎓・Admin",
        "🧪・Beta",
        "💎・Cliente",
        "👤・Visitante",
    }


def test_public_category_has_no_restrictive_overwrites() -> None:
    assert category_overwrites("public", "1", role_ids(), "999") == []


def test_private_categories_deny_everyone_and_allow_expected_roles() -> None:
    admin = category_overwrites("admin", "1", role_ids(), "999")
    client = category_overwrites("client", "1", role_ids(), "999")
    visitor = category_overwrites("visitor", "1", role_ids(), "999")

    assert admin[0] == {"id": "1", "type": 0, "allow": "0", "deny": str(VIEW_CHANNEL)}
    assert client[0] == admin[0]
    assert len(admin) == 4
    assert len(client) == 6
    assert len(visitor) == 7
    assert admin[-1]["id"] == client[-1]["id"] == visitor[-1]["id"] == "999"
