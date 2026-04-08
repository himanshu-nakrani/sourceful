import unittest
from unittest.mock import MagicMock
import sys

# Mock dependencies before importing the code under test
sys.modules['openai'] = MagicMock()
sys.modules['google'] = MagicMock()
sys.modules['google.generativeai'] = MagicMock()

from backend.services.llm import build_rag_prompt, SYSTEM_PROMPT

class TestLLM(unittest.TestCase):
    def test_build_rag_prompt_basic(self):
        class MockChunk:
            def __init__(self, c):
                self.excerpt = c
                self.page_number = None
        context_chunks = [MockChunk("Chunk 1 content"), MockChunk("Chunk 2 content")]
        question = "What is the content?"

        messages = build_rag_prompt(context_chunks, question)

        self.assertEqual(len(messages), 3)
        self.assertEqual(messages[0], {"role": "system", "content": SYSTEM_PROMPT})
        self.assertEqual(messages[1]["role"], "user")
        self.assertIn("[1]\nChunk 1 content", messages[1]["content"])
        self.assertIn("[2]\nChunk 2 content", messages[1]["content"])
        self.assertEqual(messages[2], {"role": "user", "content": question})

    def test_build_rag_prompt_with_history(self):
        class MockChunk:
            def __init__(self, c):
                self.excerpt = c
                self.page_number = None
        context_chunks = [MockChunk("Context")]
        question = "Current question"
        history = [
            {"role": "user", "content": "Prev question"},
            {"role": "assistant", "content": "Prev answer"},
            {"role": "system", "content": "Should be filtered"},
            {"role": "other", "content": "Should be filtered"}
        ]

        messages = build_rag_prompt(context_chunks, question, history=history)

        # system (fixed) + user (context) + user (history) + assistant (history) + user (current question) = 5
        self.assertEqual(len(messages), 5)
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[1]["role"], "user")
        self.assertEqual(messages[2], {"role": "user", "content": "Prev question"})
        self.assertEqual(messages[3], {"role": "assistant", "content": "Prev answer"})
        self.assertEqual(messages[4], {"role": "user", "content": question})

    def test_build_rag_prompt_empty_context(self):
        context_chunks = []
        question = "Question"

        messages = build_rag_prompt(context_chunks, question)

        self.assertEqual(len(messages), 3)
        self.assertEqual(messages[1]["role"], "user")
        self.assertIn("Document excerpts:", messages[1]["content"])
        # If context_chunks is empty, it should probably just have the header or be empty.
        # Current implementation: "\n\n---\n\n".join(...) will be ""
        self.assertIn("Document excerpts:\n\n", messages[1]["content"])

if __name__ == "__main__":
    unittest.main()
