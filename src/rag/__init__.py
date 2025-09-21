"""
RAG (Retrieval-Augmented Generation) module for vacation rental automation.
"""

from .rag_data import (
    RAGDataManager,
    load_constants,
    get_context_sections,
    build_prompt_context,
    get_rag_manager
)

__all__ = [
    'RAGDataManager',
    'load_constants', 
    'get_context_sections',
    'build_prompt_context',
    'get_rag_manager'
]

