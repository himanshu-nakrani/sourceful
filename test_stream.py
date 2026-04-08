import asyncio
from backend.services.llm import build_rag_prompt, create_openai_text_stream, gemini_text_stream
from backend.services.vectorstore import RetrievedChunk

async def test_openai():
    # Attempting to see if OpenAI returns empty response
    messages = build_rag_prompt(
        [RetrievedChunk(document_id="doc1", chunk_id="chunk1", excerpt="Some evidence.", score=0.9, page_number=1)],
        "What evidence supports the core conclusion?"
    )
    print("Messages payload:", messages)
    # We cannot test live if no api key... but we can check if there are obvious errors.

if __name__ == "__main__":
    asyncio.run(test_openai())
