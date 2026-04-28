from langchain_pinecone import PineconeVectorStore
from langchain_huggingface import HuggingFaceEmbeddings
from pinecone import Pinecone
from backend.config import PINECONE_API_KEY, PINECONE_INDEX
import os

_embeddings_cache = {}

class VectorStore:
    def __init__(self, model_name='BAAI/bge-m3'):
        # Use a singleton pattern for embeddings to avoid reloading the model
        if model_name not in _embeddings_cache:
            print(f"Loading embedding model: {model_name}...")
            _embeddings_cache[model_name] = HuggingFaceEmbeddings(model_name=model_name)
        
        self.embeddings = _embeddings_cache[model_name]
        self.index_name = PINECONE_INDEX
        
        # Ensure API key is set in environment for LangChain
        if PINECONE_API_KEY:
            os.environ["PINECONE_API_KEY"] = PINECONE_API_KEY

    def add_chunks(self, chunks, conversation_id: int):
        """Adds text chunks to Pinecone under a specific namespace (conversation_id)."""
        if not chunks:
            return
            
        PineconeVectorStore.from_texts(
            texts=chunks,
            embedding=self.embeddings,
            index_name=self.index_name,
            namespace=f"conv_{conversation_id}"
        )

    def search(self, query: str, conversation_id: int, top_k: int = 3):
        """Searches for relevant chunks in Pinecone within a specific namespace."""
        vector_store = PineconeVectorStore(
            index_name=self.index_name,
            embedding=self.embeddings,
            namespace=f"conv_{conversation_id}"
        )
        
        # similarity_search_with_score returns List[Tuple[Document, float]]
        results = vector_store.similarity_search_with_score(query, k=top_k)
        
        return [
            {"chunk": doc.page_content, "score": score}
            for doc, score in results
        ]

    def delete_namespace(self, conversation_id: int):
        """Deletes all vectors in the namespace associated with a conversation."""
        try:
            pc = Pinecone(api_key=PINECONE_API_KEY)
            index = pc.Index(self.index_name)
            index.delete(delete_all=True, namespace=f"conv_{conversation_id}")
            print(f"Deleted Pinecone namespace for conversation {conversation_id}")
        except Exception as e:
            print(f"Failed to delete Pinecone namespace: {e}")

    def load(self, file_path):
        """No-op for Pinecone as it's a cloud database."""
        pass

    def save(self, file_path):
        """No-op for Pinecone as it's a cloud database."""
        pass
