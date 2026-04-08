import requests

r = requests.post(
    "http://127.0.0.1:8000/api/chat",
    headers={
        "X-Client-Session": "c7c6fd36-0fb2-4531-8e4d-4d321e80d531",
        "X-Provider-Api-Key": "fake-key",
        "Content-Type": "application/json"
    },
    json={
        "provider": "gemini",
        "model": "gemini-1.5-flash",
        "document_id": "2764fda5-67e5-4c09-9a4a-9d35abb73547",
        "question": "TEST"
    },
    stream=True
)
print("Status:", r.status_code)
for chunk in r.iter_content(chunk_size=100):
    print(repr(chunk))
    break
