"""Knowledge inference layer (Phase A): conversation -> structured knowledge."""

from app.application.services.inference.knowledge_inference import (
    InferredKnowledge,
    KnowledgeInferenceLayer,
    infer,
)

__all__ = ["InferredKnowledge", "KnowledgeInferenceLayer", "infer"]
