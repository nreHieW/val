from functools import lru_cache

import numpy as np
from sentence_transformers import SentenceTransformer


@lru_cache(maxsize=1)
def _get_model():
    return SentenceTransformer("Alibaba-NLP/gte-base-en-v1.5", trust_remote_code=True)


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
        if query in self.gts or query.lower() in self.gts:
            return query

        query_words = set(query.lower().split())
        candidates = [
            gt
            for gt in self.gts
            if any(len(word) >= 3 for word in query_words & set(gt.lower().split()))
        ]
        return min(candidates, key=lambda candidate: len(candidate.split())) if candidates else None

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
