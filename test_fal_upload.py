import httpx

api_key = "123"
resp = httpx.post(
    "https://fal.media/upload",
    headers={"Authorization": f"Key {api_key}"},
    content=b"dummy",
)
print(resp.status_code, resp.text)
