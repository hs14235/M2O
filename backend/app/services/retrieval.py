import numpy as np
from sqlalchemy import select

from ..embeddings import get_embedding_function
from ..models import TranscriptChunk
from .common import current_revision, meeting_access
from .errors import ServiceError


class RetrievalService:
    def __init__(self, session, principal):
        self.session, self.principal = session, principal

    def search(self, meeting_id, query, k=5):
        meeting = meeting_access(self.session, self.principal, meeting_id)
        revision = current_revision(self.session, meeting)
        if revision.index_status != "ready":
            raise ServiceError(status_code=409, error="Transcript indexing is not ready", where="client")
        provider, model = revision.embed_provider, revision.embed_model
        if not provider or not model:
            raise ServiceError(status_code=409, error="Transcript embedding configuration is missing")
        chunks = self.session.scalars(
            select(TranscriptChunk)
            .where(TranscriptChunk.revision_id == revision.id)
            .order_by(TranscriptChunk.chunk_index)
        ).all()
        if not chunks or any(chunk.embedding is None for chunk in chunks):
            raise ServiceError(status_code=409, error="Transcript vectors are incomplete")
        query_vector = np.asarray(
            get_embedding_function(provider)([query], model)[0],
            dtype=np.float32,
        )
        vectors = np.asarray([chunk.embedding for chunk in chunks], dtype=np.float32)
        if vectors.ndim != 2 or vectors.shape[-1] != query_vector.size or not np.isfinite(vectors).all():
            raise ServiceError(status_code=409, error="Transcript vectors require reindexing")
        scores = vectors @ query_vector
        order = np.argsort(-scores, kind="stable")[:k]
        return {
            "results": [
                {
                    "id": chunks[i].id,
                    "score": float(scores[i]),
                    "text": chunks[i].text,
                    "metadata": {
                        "i": chunks[i].chunk_index,
                        "speaker": chunks[i].speaker,
                        "meeting_id": meeting.slug,
                        "title": meeting.title,
                        "start_line": chunks[i].start_line,
                    },
                }
                for i in order
            ],
            "provider": revision.embed_provider,
            "revision_id": revision.id,
        }
