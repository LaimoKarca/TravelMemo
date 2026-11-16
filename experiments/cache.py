"""Cache public benchmark passage encodings; queries are always freshly encoded."""

import hashlib
import os
from pathlib import Path

import numpy as np


class PassageCache:
    def __init__(self, model, path: Path):
        self.model = model
        self.path = path
        self.revision = model.revision
        self.dimension = model.dimension
        self._metadata_tokenizer = None
        self.values = {}
        if path.is_file():
            with np.load(path, allow_pickle=False) as stored:
                keys, vectors = stored["keys"], stored["vectors"]
                if vectors.shape != (len(keys), self.dimension) or not np.isfinite(vectors).all():
                    raise ValueError(
                        "Invalid benchmark embedding cache; remove the affected cache file"
                    )
                self.values = {str(key): vector.tolist() for key, vector in zip(keys, vectors)}

    def __getattr__(self, name):
        return getattr(self.model, name)

    def encode_query(self, text):
        return self.model.encode_query(text)

    def encode_passages(self, texts):
        keys = [hashlib.sha256(text.encode()).hexdigest() for text in texts]
        missing = {key: text for key, text in zip(keys, texts) if key not in self.values}
        if missing:
            vectors = self.model.encode_passages(list(missing.values()))
            self.values.update(zip(missing, vectors))
        return [self.values[key] for key in keys]

    def encode_passages_with_metadata(self, texts):
        vectors = self.encode_passages(texts)
        if self._metadata_tokenizer is None:
            from transformers import AutoTokenizer

            self._metadata_tokenizer = AutoTokenizer.from_pretrained(
                str(self.model.model_dir), local_files_only=True
            )
        counts = [
            len(self._metadata_tokenizer.encode("passage: " + t, truncation=False)) for t in texts
        ]
        return vectors, [{"token_count": n, "truncated": n > 512} for n in counts]

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp.npz")
        np.savez_compressed(
            temporary,
            keys=np.array(list(self.values)),
            vectors=np.array(list(self.values.values())),
        )
        os.replace(temporary, self.path)
