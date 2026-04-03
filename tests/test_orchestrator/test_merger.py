from src.orchestrator.merger import ResultMerger


def test_merger_adds_share_with_score():
    m = ResultMerger()
    out = m.merge({"score": 7.5}, "https://cdn.example.com/card.jpg", "user-1")
    assert out["share"]["card_url"] == "https://cdn.example.com/card.jpg"
    assert "deep_link" in out["share"]
    assert out["share"]["caption"]


def test_merger_without_score_caption():
    m = ResultMerger()
    out = m.merge({"dating_score": 8}, None, "u2")
    assert out["share"]["card_url"] is None
    assert "результат" in out["share"]["caption"].lower() or "@" in out["share"]["caption"]
