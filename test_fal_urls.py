import httpx
api_key = "123"
for url in [
    "https://rest.fal.run/storage/upload",
    "https://fal.media/upload",
    "https://queue.fal.run/storage/upload",
    "https://api.fal.ai/storage/upload",
    "https://fal.run/storage/upload",
]:
    try:
        r = httpx.post(url, headers={"Authorization": f"Key {api_key}"}, content=b"123")
        print(url, r.status_code)
    except Exception as e:
        print(url, type(e).__name__)
