from types import SimpleNamespace

from src.api import deps


def test_exempt_username_match(monkeypatch):
    monkeypatch.setattr(
        deps.settings,
        "rate_limit_exempt_usernames",
        "Foo,scrumux,@Other",
    )
    u = SimpleNamespace(username="ScrumUx")
    assert deps._user_exempt_from_rate_limit(u) is True


def test_not_exempt(monkeypatch):
    monkeypatch.setattr(deps.settings, "rate_limit_exempt_usernames", "scrumux")
    u = SimpleNamespace(username="someone_else")
    assert deps._user_exempt_from_rate_limit(u) is False


def test_no_username_not_exempt(monkeypatch):
    monkeypatch.setattr(deps.settings, "rate_limit_exempt_usernames", "scrumux")
    u = SimpleNamespace(username=None)
    assert deps._user_exempt_from_rate_limit(u) is False
