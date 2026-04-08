import os
import sys
try:
    import google.generativeai as genai
    from google.generativeai.types import GenerationConfig
    print("Google Generative AI imported. Version:", getattr(genai, "__version__", "unknown"))
except Exception as e:
    print("Error:", e)
