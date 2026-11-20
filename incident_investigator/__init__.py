"""Evidence-first incident investigation, with offline and optional LLM modes.

The supported public API is :func:`investigate` and :func:`render_markdown`.
All findings are observations of supplied records, not verified real-world events.
"""
from .investigation import investigate
from .llm import LLMConfig, LLMError, LLMValidationError
from .report import render_markdown

__all__ = ["investigate", "render_markdown", "LLMConfig", "LLMError", "LLMValidationError"]
__version__ = "0.1.0"
