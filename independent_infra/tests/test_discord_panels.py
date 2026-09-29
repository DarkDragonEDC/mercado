from scripts.publish_discord_panels import PANELS, embed_payload


def test_panels_have_unique_versioned_markers_and_fit_discord_limits() -> None:
    markers = [panel["footer"].split(" | ", 1)[0] for panel in PANELS.values()]
    assert len(markers) == len(set(markers))
    assert all(marker.endswith(":v2") for marker in markers)
    assert all(len(panel["title"]) <= 256 for panel in PANELS.values())
    assert all(len(panel["description"]) <= 4096 for panel in PANELS.values())
    assert all(len(panel["footer"]) <= 2048 for panel in PANELS.values())


def test_commercial_copy_matches_current_business_model() -> None:
    plans = PANELS["💳・planos-e-acesso"]["description"]
    assert "R$ 39,90" in plans
    assert "R$ 49,90" in plans
    assert "R$ 99,90" in plans
    assert "30 dias" in plans
    assert "Não há renovação automática" in plans
    assert "pagamentos permanecem desativados" in plans


def test_embed_payload_disables_no_safety_copy() -> None:
    payload = embed_payload(PANELS["🚪・comece-aqui"])
    assert payload["footer"]["text"].startswith("albionmkt:comece-aqui:v2")
    assert payload["color"] > 0
