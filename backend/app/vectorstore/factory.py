from .base import VectorStore
from .faiss_store import FaissStore
from .memory_store import MemoryStore


def get_store(dim: int, backend: str, index_path: str, meta_path: str) -> VectorStore:
    if backend.lower() == "faiss":
        try:
            return FaissStore(dim, index_path, meta_path)
        except ImportError:
            # fall back gracefully
            return MemoryStore()
    return MemoryStore()
