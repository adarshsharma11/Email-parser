#!/usr/bin/env python3
"""
Simple test script to demonstrate RAG and LLM functionality.
"""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_rag_functionality():
    """Test RAG data loading and context building."""
    print("=== Testing RAG Functionality ===")
    
    try:
        from src.rag.rag_data import load_constants, get_context_sections, build_prompt_context
        
        # Test loading constants
        print("Loading constants...")
        constants = load_constants()
        print(f"Loaded {len(constants['vendors'])} vendors, {len(constants['recs'])} recs, {len(constants['rules'])} rules")
        
        # Test context sections
        print("\nTesting context retrieval...")
        sections = get_context_sections("cleaning services", k=3)
        print(f"Found {len(sections)} relevant sections")
        
        # Test prompt context building
        print("\nTesting prompt context building...")
        context = build_prompt_context("What are the cleaning rules?", k=2)
        print(f"Context length: {len(context)} characters")
        print(f"Context preview: {context[:200]}...")
        
        return True
        
    except Exception as e:
        print(f"RAG test failed: {e}")
        return False


def test_llm_functionality():
    """Test LLM question answering."""
    print("\n=== Testing LLM Functionality ===")
    
    try:
        from src.llm.llm_skeleton import answer_question
        
        # Test question answering
        questions = [
            "What vendors do you have?",
            "What are the cleaning rules?",
            "How do I handle guest complaints?"
        ]
        
        for question in questions:
            print(f"\nQuestion: {question}")
            result = answer_question(question, k=3)
            
            print(f"Answer: {result['answer']}")
            print(f"Provider: {result['provider']}")
            print(f"Model: {result['model']}")
            print(f"Has context: {result.get('has_context', False)}")
            
        return True
        
    except Exception as e:
        print(f"LLM test failed: {e}")
        return False


def main():
    """Run all tests."""
    print("Testing RAG and LLM Integration")
    print("=" * 40)
    
    # Test RAG
    rag_success = test_rag_functionality()
    
    # Test LLM
    llm_success = test_llm_functionality()
    
    # Summary
    print("\n" + "=" * 40)
    print("Test Summary:")
    print(f"RAG: {'✅ PASS' if rag_success else '❌ FAIL'}")
    print(f"LLM: {'✅ PASS' if llm_success else '❌ FAIL'}")
    
    if rag_success and llm_success:
        print("\n🎉 All tests passed! RAG and LLM integration is working.")
    else:
        print("\n⚠️  Some tests failed. Check the error messages above.")


if __name__ == "__main__":
    main()

