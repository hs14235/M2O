"""Adapters open a request-scoped session; no mutable global tenant state."""

from .services.extraction import ExtractionService
from .services.issues import IssueService
from .services.meetings import MeetingService
from .services.retrieval import RetrievalService
from .services.review import ReviewService


def services(session, principal):
    return {
        "meetings": MeetingService(session, principal),
        "review": ReviewService(session, principal),
        "issues": IssueService(session, principal),
        "retrieval": RetrievalService(session, principal),
        "extraction": ExtractionService(session),
    }
