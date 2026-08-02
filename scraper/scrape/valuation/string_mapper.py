import re
from functools import lru_cache

import numpy as np
from sentence_transformers import SentenceTransformer


@lru_cache(maxsize=1)
def _get_model():
    return SentenceTransformer(
        "Alibaba-NLP/gte-base-en-v1.5",
        revision="a829fd0e060bb84554da0dfd354d0de0f7712b7f",
        trust_remote_code=True,
        model_kwargs={"code_revision": "40ced75c3017eb27626c9d4ea981bde21a2662f4"},
    )


class StringMapper:
    def __init__(self, gts: list, threshold=0):
        self.model = _get_model()
        self.gts = gts
        self.embeddings = self.model.encode(gts, show_progress_bar=False)
        self.embeddings = self.embeddings / np.linalg.norm(self.embeddings, axis=1)[:, None]
        self.threshold = threshold

    def get_closest(self, query: str, num_results=1):
        return [gt for gt, _ in self.get_closest_with_scores(query, num_results)]

    def _word_match(self, query: str):
        def words(value):
            normalized = []
            for word in re.findall(r"[a-z0-9]+", value.lower()):
                if len(word) > 3 and word.endswith("ies"):
                    word = word[:-3] + "y"
                elif len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
                    word = word[:-1]
                normalized.append(word)
            return set(normalized)

        query_words = words(query)
        return next((gt for gt in self.gts if words(gt) == query_words), None)

    def get_closest_with_scores(self, query: str, num_results=1, indices_to_adjust=None):
        return list(self._get_closest_with_scores(query, num_results, tuple(indices_to_adjust or ())))

    @lru_cache(maxsize=10000)
    def _get_closest_with_scores(self, query: str, num_results: int, indices_to_adjust: tuple):
        match = self._word_match(query)
        if match is not None:
            return ((match, 1.0),)

        query_embedding = self.model.encode(query, show_progress_bar=False)
        query_embedding = query_embedding / np.linalg.norm(query_embedding)
        scores = np.dot(self.embeddings, query_embedding)
        if indices_to_adjust:
            scores[list(indices_to_adjust)] += np.max(scores) * 0.1

        indices = np.argsort(-scores)
        indices = [i for i in indices if scores[i] > self.threshold][:num_results]
        return tuple((self.gts[i], scores[i]) for i in indices)
