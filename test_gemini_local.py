import asyncio
from backend.services.llm import gemini_text

messages = [
    {"role": "system", "content": "System test"},
    {"role": "user", "content": "Context test"},
    {"role": "user", "content": "Question test"}
]

try:
    gemini_text("fake-key", "gemini-1.5-flash", messages)
except Exception as e:
    print("EXCEPTION:", type(e))
    print(e)
