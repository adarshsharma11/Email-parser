from pathlib import Path
from dotenv import load_dotenv
import sys, os

# load project .env
PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")
sys.path.append(str(PROJECT_ROOT))

# choose provider (optional override)
os.environ["LLM_PROVIDER"] = "openai"   # uncomment to force OpenAI
os.environ["LLM_MODEL"] = "gpt-3.5-turbo"  # Set proper model name
# os.environ["LLM_PROVIDER"] = "local"    # use mock

from src.llm.llm_skeleton import answer_question

from src.firebase_sync.firestore_client import FirestoreClient
from src.llm.llm_skeleton import get_llm_manager


def build_context_from_collection(collection_name: str, limit: int = None) -> str:
	"""Read documents from Firestore `collection_name` and format a context string."""
	client = FirestoreClient()
	if not client.initialize():
		print(f"[ask] Failed to initialize Firestore client")
		return ""

	# Get all documents if no limit specified, otherwise apply limit
	if limit:
		docs = list(client.db.collection(collection_name).limit(limit).stream())
		print(f"[ask] Reading {len(docs)} documents (limited to {limit}) from '{collection_name}'")
	else:
		docs = list(client.db.collection(collection_name).stream())
		print(f"[ask] Reading ALL {len(docs)} documents from '{collection_name}'")
	
	if not docs:
		print(f"[ask] No documents found in collection '{collection_name}'")
		return ""

	return docs  # Return the docs themselves, not formatted text


def smart_context_builder(docs, question: str, max_context_length: int = 8000) -> str:
	"""Build context intelligently based on question and token limits."""
	
	# Extract key info from each document for analysis
	doc_summaries = []
	for doc in docs:
		d = doc.to_dict()
		# Create a short summary of each document
		summary = f"ID:{doc.id}"
		for key in ['from', 'sender', 'subject', 'company', 'type', 'category']:
			if key in d:
				summary += f" {key}:{d[key]}"
		doc_summaries.append((doc.id, summary, d))
	
	# If asking about counts or totals, provide statistical summary
	question_lower = question.lower()
	if any(word in question_lower for word in ['how many', 'total', 'count', 'number of']):
		# Provide statistical overview
		total_count = len(docs)
		
		# Count by common fields
		companies = {}
		senders = {}
		subjects = {}
		
		for doc_id, summary, full_doc in doc_summaries:
			# Count companies/senders
			for field in ['from', 'sender', 'company']:
				if field in full_doc:
					sender = str(full_doc[field]).lower()
					companies[sender] = companies.get(sender, 0) + 1
			
			# Count subjects
			if 'subject' in full_doc:
				subject = str(full_doc['subject'])[:50]  # First 50 chars
				subjects[subject] = subjects.get(subject, 0) + 1
		
		# Build statistical context
		stats_context = f"Total emails: {total_count}\n\n"
		
		if companies:
			stats_context += "Top senders:\n"
			for sender, count in sorted(companies.items(), key=lambda x: x[1], reverse=True)[:10]:
				stats_context += f"  - {sender}: {count} emails\n"
		
		return stats_context
	
	# For other questions, use a sample of documents
	sample_size = min(20, len(docs))
	sampled_docs = docs[:sample_size]
	
	parts = []
	current_length = 0
	
	for doc in sampled_docs:
		d = doc.to_dict()
		doc_text = f"Document ID: {doc.id}\n" + "\n".join(f"{k}: {v}" for k, v in d.items())
		
		if current_length + len(doc_text) > max_context_length:
			break
			
		parts.append(doc_text)
		current_length += len(doc_text)
	
	if len(parts) < len(sampled_docs):
		parts.append(f"\n[NOTE: Showing {len(parts)} of {len(docs)} total documents due to size limits]")
	
	return "\n\n".join(parts)


def ask_about_alon_test(question: str, collection_name: str = "Alon-test"):
	# Get all documents from Firestore
	docs = build_context_from_collection(collection_name, limit=None)
	
	if not docs:
		print("❌ No documents found in the collection")
		return None
	
	# Build smart context based on the question
	context = smart_context_builder(docs, question)

	# Construct prompt using the smart context
	if context:
		full_prompt = f"Context Information:\n{context}\n\nQuestion: {question}\n\nPlease answer the question based on the context provided above."
	else:
		full_prompt = f"Question: {question}\n\nPlease answer this question based on your general knowledge."

	# Use the configured LLM provider directly
	manager = get_llm_manager()
	provider = manager.provider

	response = provider.generate_response(full_prompt)

	print(f"\n🤖 Provider: {response.get('provider')} ({response.get('model')})")
	print(f"📊 Has context: {bool(context)}")
	print(f"💬 Answer:\n{response.get('answer')}")
	return response


def interactive_loop():
	"""Interactive loop to ask multiple questions about the database."""
	collection_name = os.getenv("ALON_TEST_COLLECTION", "Alon-test")
	
	print("=" * 60)
	print("🔥 Interactive Database Query Assistant")
	print("=" * 60)
	print(f"📁 Connected to Firestore collection: '{collection_name}'")
	print("🤖 Using OpenAI GPT-3.5-turbo with your database context")
	print("\n💡 Tips:")
	print("  - Ask questions about the data in your collection")
	print("  - Type 'quit', 'exit', or 'q' to stop")
	print("  - Type 'help' for example questions")
	print("=" * 60)
	
	while True:
		try:
			question = input("\n❓ Your question: ").strip()
			
			if question.lower() in ['quit', 'exit', 'q', '']:
				print("\n👋 Goodbye!")
				break
			
			if question.lower() == 'help':
				print("\n📋 Example questions you can ask:")
				print("  • What types of emails are in the database?")
				print("  • Which companies send the most emails?")
				print("  • What patterns do you see in the data?")
				print("  • Summarize the main categories of emails")
				print("  • Are there any suspicious or unusual emails?")
				continue
			
			if len(question) < 3:
				print("⚠️  Please ask a more detailed question.")
				continue
			
			print(f"\n🔍 Searching database for: '{question}'")
			print("⏳ Processing...")
			
			ask_about_alon_test(question, collection_name)
			
		except KeyboardInterrupt:
			print("\n\n👋 Interrupted. Goodbye!")
			break
		except Exception as e:
			print(f"\n❌ Error: {str(e)}")
			print("Please try again with a different question.")


if __name__ == "__main__":
	# Check if a specific question was provided via environment variable
	specific_question = os.getenv("ALON_TEST_QUESTION")
	if specific_question:
		print(f"🎯 Running single question: {specific_question}")
		collection_name = os.getenv("ALON_TEST_COLLECTION", "Alon-test")
		ask_about_alon_test(specific_question, collection_name)
	else:
		# Start interactive mode
		interactive_loop()