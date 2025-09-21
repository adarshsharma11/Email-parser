#!/usr/bin/env python3
"""
Example usage of RAG and LLM functionality for vacation rental automation.
"""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def example_rag_usage():
    """Example of using RAG functionality."""
    print("=== RAG Usage Examples ===")
    
    from src.rag.rag_data import load_constants, get_context_sections, build_prompt_context
    
    # Load all constants (vendors, recs, rules)
    print("1. Loading constants from Firestore...")
    constants = load_constants()
    print(f"   - Vendors: {len(constants['vendors'])} records")
    print(f"   - Recommendations: {len(constants['recs'])} records") 
    print(f"   - Rules: {len(constants['rules'])} records")
    
    # Get relevant context for a question
    print("\n2. Finding relevant context...")
    question = "What cleaning services are available?"
    sections = get_context_sections(question, k=3)
    print(f"   Question: {question}")
    print(f"   Found {len(sections)} relevant sections")
    
    for i, (source_tag, record) in enumerate(sections, 1):
        print(f"   {i}. {source_tag}: {record.get('name', record.get('title', 'Unknown'))}")
    
    # Build prompt-ready context
    print("\n3. Building prompt context...")
    context = build_prompt_context(question, k=2)
    print(f"   Context length: {len(context)} characters")
    print(f"   Preview: {context[:150]}...")
    
    return True


def example_llm_usage():
    """Example of using LLM functionality."""
    print("\n=== LLM Usage Examples ===")
    
    from src.llm.llm_skeleton import answer_question
    
    # Example questions
    questions = [
        "What vendors do you recommend for cleaning?",
        "What are the house rules for guests?",
        "How should I handle maintenance requests?",
        "What's the check-in process?"
    ]
    
    print("Answering questions with RAG context...")
    
    for i, question in enumerate(questions, 1):
        print(f"\n{i}. Question: {question}")
        
        # Get answer with context
        result = answer_question(question, k=3)
        
        print(f"   Answer: {result['answer']}")
        print(f"   Provider: {result['provider']}")
        print(f"   Model: {result['model']}")
        print(f"   Context used: {result.get('has_context', False)}")
        print(f"   Sections used: {result.get('context_sections_used', 0)}")
    
    return True


def example_with_system_hint():
    """Example using system hints to guide the LLM."""
    print("\n=== LLM with System Hints ===")
    
    from src.llm.llm_skeleton import answer_question
    
    question = "What should I do if a guest complains about cleanliness?"
    
    system_hint = """You are a helpful vacation rental property manager assistant. 
    Always provide practical, actionable advice. Be professional but friendly. 
    Focus on solutions that maintain guest satisfaction while being cost-effective."""
    
    print(f"Question: {question}")
    print(f"System hint: {system_hint[:100]}...")
    
    result = answer_question(question, k=3, system_hint=system_hint)
    
    print(f"Answer: {result['answer']}")
    print(f"Provider: {result['provider']}")


def example_force_refresh():
    """Example of forcing cache refresh."""
    print("\n=== Force Refresh Example ===")
    
    from src.rag.rag_data import load_constants
    
    print("Loading constants with force refresh...")
    constants = load_constants(force_refresh=True)
    
    print(f"Refreshed data - Vendors: {len(constants['vendors'])} records")


def main():
    """Run all examples."""
    print("RAG and LLM Integration Examples")
    print("=" * 50)
    
    try:
        # Run examples
        example_rag_usage()
        example_llm_usage()
        example_with_system_hint()
        example_force_refresh()
        
        print("\n" + "=" * 50)
        print("✅ All examples completed successfully!")
        print("\nKey Features Demonstrated:")
        print("- Loading and caching data from Firestore")
        print("- Context retrieval based on questions")
        print("- Prompt building with relevant context")
        print("- LLM integration with multiple providers")
        print("- System hints for guided responses")
        print("- Cache management with force refresh")
        
    except Exception as e:
        print(f"\n❌ Example failed: {e}")
        print("Make sure your .env file is configured and Firestore is accessible.")


if __name__ == "__main__":
    main()
