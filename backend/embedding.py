"""Multilingual E5 embedding model wrapper for TravelMemo."""

from __future__ import annotations

import logging
import math
import threading
from pathlib import Path
from typing import Any

from backend.locations import looks_like_url

logger = logging.getLogger(__name__)

E5_MODEL_NAME = "intfloat/multilingual-e5-small"
E5_REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
E5_DIMENSION = 384
MAX_TOKENS = 512
ENCODE_BATCH_SIZE = 8
QUERY_PREFIX = "query: "
PASSAGE_PREFIX = "passage: "


def l2_normalize(vector: list[float]) -> list[float]:
    """Applies L2 normalization to a vector."""
    norm = math.sqrt(sum(x * x for x in vector))
    if norm == 0:
        return vector
    return [x / norm for x in vector]


def event_to_passage_text(event: dict[str, Any]) -> str:
    """Formats event fields into passage text for embedding using only its own fields."""
    parts = []
    date = event.get("date") or event.get("timestamp")
    if date:
        parts.append(f"日期: {date}")
    time_val = event.get("time")
    if time_val:
        parts.append(f"時間: {time_val}")
    category = event.get("category") or event.get("venue_category")
    if category:
        parts.append(f"類別: {category}")
    place_name = event.get("place_name") or event.get("name")
    if place_name:
        parts.append(f"地點: {place_name}")
    city = event.get("city") or event.get("venue_city")
    if city:
        parts.append(f"城市: {city}")
    address = event.get("address")
    if address and not looks_like_url(address):
        parts.append(f"地址: {address}")
    notes = event.get("notes")
    if notes:
        parts.append(f"心得: {notes}")
    if event.get("event_text"):
        parts.append(str(event["event_text"]))
    return " ".join(parts).strip()


class EmbeddingModel:
    """Wraps multilingual-e5-small with lazy loading and version verification.

    Model loading and downloading are strictly deferred until explicit download()
    or first encode_* invocation. If the model or runtime is unavailable,
    it gracefully indicates unavailability so BM25 can continue serving queries.
    Thread-safe lazy loading and inference protected by a shared RLock.
    """

    def __init__(self, settings: Any = None):
        self.settings = settings
        self.model_name = getattr(settings, "embedding_model", E5_MODEL_NAME)
        self.revision = getattr(settings, "embedding_revision", E5_REVISION)
        self.model_dir = Path(getattr(settings, "embedding_model_dir", "data/models/multilingual-e5-small"))
        self.dimension = E5_DIMENSION
        self.batch_size = ENCODE_BATCH_SIZE
        self._model = None
        self._tokenizer = None
        self._load_failed = False
        self._load_error: str | None = None
        self._lock = threading.RLock()

    @property
    def is_loaded(self) -> bool:
        with self._lock:
            return self._model is not None

    def download(self) -> bool:
        """Explicitly downloads and caches the model with the pinned revision."""
        with self._lock:
            try:
                rev_file = self.model_dir / "revision.txt"
                has_weights = (self.model_dir / "model.safetensors").is_file() or (
                    self.model_dir / "pytorch_model.bin"
                ).is_file()
                has_config = (self.model_dir / "config.json").is_file()

                if (
                    self.model_dir.is_dir()
                    and rev_file.is_file()
                    and has_weights
                    and has_config
                    and rev_file.read_text(encoding="utf-8").strip() == self.revision
                ):
                    logger.info("Local model already present at %s with revision %s", self.model_dir, self.revision)
                    return True

                logger.info("Downloading model %s (rev: %s) into %s", self.model_name, self.revision, self.model_dir)
                self.model_dir.mkdir(parents=True, exist_ok=True)
                from huggingface_hub import snapshot_download

                snapshot_download(
                    repo_id=self.model_name,
                    revision=self.revision,
                    local_dir=str(self.model_dir),
                    allow_patterns=["*.json", "*.txt", "*.model", "*.safetensors"],
                )
                rev_file.write_text(self.revision, encoding="utf-8")
                return True
            except Exception as exc:  # noqa: BLE001
                self._load_failed = True
                self._load_error = str(exc)
                logger.warning("Embedding model download failed: %s", exc)
                return False

    def _ensure_loaded(self):
        with self._lock:
            if self._model is not None:
                return

            # If previously marked failed, check if local files have appeared before giving up
            if self._load_failed:
                rev_file = self.model_dir / "revision.txt"
                has_weights = (self.model_dir / "model.safetensors").is_file() or (
                    self.model_dir / "pytorch_model.bin"
                ).is_file()
                has_config = (self.model_dir / "config.json").is_file()
                if not (self.model_dir.is_dir() and rev_file.is_file() and has_weights and has_config):
                    raise RuntimeError(f"Embedding model unavailable: {self._load_error}")
                self._load_failed = False
                self._load_error = None

            try:
                import torch

                torch.set_num_threads(2)

                # Local-only model directory check
                if not self.model_dir.is_dir() or not (self.model_dir / "config.json").is_file():
                    raise RuntimeError(
                        f"Local embedding model directory '{self.model_dir}' not found or incomplete. Run download CLI."
                    )

                rev_file = self.model_dir / "revision.txt"
                if not rev_file.is_file():
                    raise RuntimeError(
                        f"Model revision marker missing: '{rev_file}' does not exist. Run download CLI."
                    )

                loaded_rev = rev_file.read_text(encoding="utf-8").strip()
                if loaded_rev != self.revision:
                    raise RuntimeError(
                        f"Model revision mismatch: expected '{self.revision}', found '{loaded_rev}'."
                    )

                from transformers import AutoModel, AutoTokenizer

                self._tokenizer = AutoTokenizer.from_pretrained(
                    str(self.model_dir),
                    local_files_only=True,
                )
                self._model = AutoModel.from_pretrained(
                    str(self.model_dir),
                    local_files_only=True,
                )
                self._model.eval()
                logger.info("Loaded local embedding model from %s (threads=2)", self.model_dir)
            except Exception as exc:
                self._load_failed = True
                self._load_error = str(exc)
                logger.warning("Failed to load embedding model: %s", exc)
                raise

    def encode_query(self, text: str) -> list[float]:
        """Encodes a single search query with 'query: ' prefix and L2 normalization."""
        with self._lock:
            self._ensure_loaded()
            prefixed = QUERY_PREFIX + text
            vectors, _ = self._encode_texts_with_metadata([prefixed], is_query=True)
            return vectors[0]

    def encode_passages(self, texts: list[str]) -> list[list[float]]:
        """Encodes passage texts with 'passage: ' prefix and L2 normalization."""
        vectors, _ = self.encode_passages_with_metadata(texts)
        return vectors

    def encode_passages_with_metadata(
        self, texts: list[str]
    ) -> tuple[list[list[float]], list[dict[str, Any]]]:
        """Encodes passage texts with 'passage: ' prefix, returning vectors and truncation metadata."""
        if not texts:
            return [], []
        with self._lock:
            self._ensure_loaded()
            prefixed = [PASSAGE_PREFIX + t for t in texts]
            return self._encode_texts_with_metadata(prefixed, is_query=False)

    def _encode_texts_with_metadata(
        self, texts: list[str], is_query: bool = False
    ) -> tuple[list[list[float]], list[dict[str, Any]]]:
        import torch

        torch.set_num_threads(2)

        metadata: list[dict[str, Any]] = []

        # Check truncation for each text; NEVER log raw text or snippets
        for t in texts:
            token_count = 0
            truncated = False
            if self._tokenizer is not None:
                token_count = len(self._tokenizer.encode(t, truncation=False))
                if token_count > MAX_TOKENS:
                    truncated = True
                    logger.warning(
                        "Input text exceeds %d tokens (token_count=%d); truncated.",
                        MAX_TOKENS,
                        token_count,
                    )
            elif len(t) > MAX_TOKENS * 3:
                truncated = True
                token_count = len(t) // 3
                logger.warning(
                    "Input text length %d exceeds threshold; potential truncation.",
                    len(t),
                )
            else:
                token_count = len(t)
            metadata.append({"token_count": token_count, "truncated": truncated})

        results: list[list[float]] = []

        # Batch execution (batch size <= 8 to preserve 2GiB memory budget)
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            inputs = self._tokenizer(
                batch,
                padding=True,
                truncation=True,
                max_length=MAX_TOKENS,
                return_tensors="pt",
            )
            with torch.no_grad():
                outputs = self._model(**inputs)
                # Average pooling
                mask = inputs["attention_mask"].unsqueeze(-1).expand(outputs.last_hidden_state.size()).float()
                sum_embeddings = torch.sum(outputs.last_hidden_state * mask, 1)
                sum_mask = torch.clamp(mask.sum(1), min=1e-9)
                mean_pooled = sum_embeddings / sum_mask
                normalized = torch.nn.functional.normalize(mean_pooled, p=2, dim=1)
                results.extend(normalized.cpu().tolist())

        return results, metadata
