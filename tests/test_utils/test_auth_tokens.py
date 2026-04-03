from src.utils.auth_tokens import hash_api_key


def test_hash_api_key_stable():
    a = hash_api_key("mykey", "pepper")
    b = hash_api_key("mykey", "pepper")
    assert a == b
    assert len(a) == 64
