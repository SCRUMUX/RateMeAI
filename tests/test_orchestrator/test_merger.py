from src.orchestrator.merger import ResultMerger


def test_merger_adds_share_with_score():
    m = ResultMerger()
    out = m.merge({"score": 7.5}, "https://cdn.example.com/card.jpg", "user-1")
    assert out["share"]["card_url"] == "https://cdn.example.com/card.jpg"
    assert "deep_link" in out["share"]
    assert "рейтинг" in out["share"]["caption"].lower()


def test_merger_dating_caption():
    m = ResultMerger()
    out = m.merge({"dating_score": 8}, None, "u2")
    assert out["share"]["card_url"] is None
    assert "знакомств" in out["share"]["caption"].lower()


def test_merger_cv_caption():
    m = ResultMerger()
    out = m.merge({"hireability": 9}, None, "u3")
    assert "карьерный" in out["share"]["caption"].lower()


def test_merger_social_caption():
    m = ResultMerger()
    out = m.merge({"social_score": 7.5}, None, "u4")
    assert "соцсет" in out["share"]["caption"].lower()


def test_merger_generic_caption():
    m = ResultMerger()
    out = m.merge({"stickers": []}, None, "u5")
    assert "результат" in out["share"]["caption"].lower()
