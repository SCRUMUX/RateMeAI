"""Unit tests for webhook IP validation."""
from src.api.v1.payments import _is_trusted_ip


def test_yookassa_ip_trusted():
    assert _is_trusted_ip("185.71.76.1") is True
    assert _is_trusted_ip("185.71.77.255") is True
    assert _is_trusted_ip("77.75.153.10") is True


def test_random_ip_untrusted():
    assert _is_trusted_ip("1.2.3.4") is False
    assert _is_trusted_ip("192.168.1.1") is False


def test_none_ip_untrusted():
    assert _is_trusted_ip(None) is False
    assert _is_trusted_ip("") is False
