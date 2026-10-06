from abc import ABC, abstractmethod
from typing import Any


class VectorStore(ABC):
    @abstractmethod
    def upsert(self, ids: list[str], embeddings: list[list[float]], metas: list[dict[str, Any]]): ...
    @abstractmethod
    def query(
        self, embedding: list[float], k: int = 5, filters: dict[str, Any] | None = None
    ) -> list[tuple[str, float, dict[str, Any]]]: ...
    @abstractmethod
    def delete(self, filters: dict[str, Any]) -> int: ...
    @abstractmethod
    def persist(self): ...
