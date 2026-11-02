from dataclasses import dataclass
from pathlib import Path
from threading import Lock

import numpy as np

from app.core.config import Settings


@dataclass(frozen=True)
class EmbeddingProfile:
    id: str
    label: str
    model_name: str
    local_path: Path
    dimensions: int
    query_prefix: str = ""
    query_prompt_name: str | None = None

    @property
    def collection_name(self) -> str:
        model = self.id.replace("-", "_").replace(".", "_")
        return f"campus_chunks_{model}_{self.dimensions}_v1"


class LocalEmbeddingModels:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.profiles = {
            "bge-small": EmbeddingProfile(
                id="bge-small",
                label="BGE-small-zh-v1.5",
                model_name=settings.embedding_bge_model,
                local_path=settings.embedding_bge_path,
                dimensions=settings.embedding_bge_dimensions,
                query_prefix=settings.embedding_bge_query_prefix,
            ),
            "qwen-0.6b": EmbeddingProfile(
                id="qwen-0.6b",
                label="Qwen3-Embedding-0.6B",
                model_name=settings.embedding_qwen_model,
                local_path=settings.embedding_qwen_path,
                dimensions=settings.embedding_qwen_dimensions,
                query_prompt_name="query",
            ),
        }
        self._models: dict[str, object] = {}
        self._locks = {profile_id: Lock() for profile_id in self.profiles}

    def profile(self, profile_id: str) -> EmbeddingProfile:
        try:
            return self.profiles[profile_id]
        except KeyError as exc:
            raise ValueError(f"Unknown local embedding profile: {profile_id}") from exc

    def encode_documents(self, profile_id: str, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._load(profile_id)
        with self._locks[profile_id]:
            vectors = model.encode(
                texts,
                batch_size=16,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        return np.asarray(vectors, dtype=np.float32).tolist()

    def encode_query(self, profile_id: str, question: str) -> list[float]:
        profile = self.profile(profile_id)
        model = self._load(profile_id)
        kwargs: dict[str, object] = {}
        text = question
        if profile.query_prompt_name:
            kwargs["prompt_name"] = profile.query_prompt_name
        elif profile.query_prefix:
            text = profile.query_prefix + question
        with self._locks[profile_id]:
            vector = model.encode(
                [text],
                batch_size=1,
                normalize_embeddings=True,
                show_progress_bar=False,
                **kwargs,
            )[0]
        return np.asarray(vector, dtype=np.float32).tolist()

    def _load(self, profile_id: str):
        profile = self.profile(profile_id)
        if profile_id in self._models:
            return self._models[profile_id]
        with self._locks[profile_id]:
            if profile_id in self._models:
                return self._models[profile_id]
            if not profile.local_path.is_dir():
                raise RuntimeError(f"Embedding model directory does not exist: {profile.local_path}")
            import torch
            from sentence_transformers import SentenceTransformer

            if self.settings.embedding_device == "cuda" and not torch.cuda.is_available():
                raise RuntimeError("CUDA was requested, but PyTorch cannot access a CUDA device")
            device = (
                "cuda"
                if self.settings.embedding_device in {"auto", "cuda"} and torch.cuda.is_available()
                else "cpu"
            )
            model = SentenceTransformer(
                str(profile.local_path),
                device=device,
                local_files_only=True,
            )
            model.max_seq_length = min(512, model.max_seq_length or 512)
            dimensions = model.get_sentence_embedding_dimension()
            if dimensions != profile.dimensions:
                raise RuntimeError(
                    f"Embedding dimension mismatch for {profile_id}: "
                    f"expected {profile.dimensions}, got {dimensions}"
                )
            self._models[profile_id] = model
            return model
