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
        context_chunks = ["Chunk 1 content", "Chunk 2 content"]
        question = "What is the content?"

        messages = build_rag_prompt(context_chunks, question)

        self.assertEqual(len(messages), 3)
        self.assertEqual(messages[0], {"role": "system", "content": SYSTEM_PROMPT})
        self.assertEqual(messages[1]["role"], "user")
        self.assertIn("[1] Chunk 1 content", messages[1]["content"])
        self.assertIn("[2] Chunk 2 content", messages[1]["content"])
        self.assertEqual(messages[2], {"role": "user", "content": question})

    def test_build_rag_prompt_with_history(self):
        context_chunks = ["Context"]
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
        self.assertIn("Context excerpts from the document:", messages[1]["content"])
        # If context_chunks is empty, it should probably just have the header or be empty.
        # Current implementation: "\n\n---\n\n".join(...) will be ""
        self.assertIn("Context excerpts from the document:\n\n", messages[1]["content"])

if __name__ == "__main__":
    unittest.main()
