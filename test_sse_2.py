import requests

r = requests.post(
    "http://127.0.0.1:8000/api/chat",
    headers={
        "X-Client-Session": "d7798363-1722-472b-95c9-278dc508d7f6",
        "X-Provider-Api-Key": "fake-key",
        "Content-Type": "application/json"
    },
    json={
        "provider": "gemini",
        "model": "gemini-1.5-flash",
        "document_id": "2764fda5-67e5-4c09-9a4a-9d35abb73547",
        "question": "test"
    },
    stream=True
)
print("Status:", r.status_code)
try:
    for chunk in r.iter_content(chunk_size=120):
        print("CHUNK:", repr(chunk))
        break
except Exception as e:
    print(e)
