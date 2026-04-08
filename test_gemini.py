import os
import google.generativeai as genai

genai.configure(api_key=os.environ.get("GEMINI_API_KEY", ""))

model = genai.GenerativeModel(model_name="gemini-1.5-flash")
history = [{"role": "user", "parts": ["Document excerpts..."]}]
try:
    chat = model.start_chat(history=history)
    response = chat.send_message("What evidence supports the core conclusion?", stream=True)
    for chunk in response:
        try:
            print("CHUNK:", chunk.text)
        except Exception as e:
            print("ERROR IN CHUNK:", type(e))
except Exception as e:
    print("ERROR:", type(e), e)
