import numpy as np
from sentence_transformers import SentenceTransformer


class StringMapper:
    def __init__(self, gts: list, threshold=0):
        self.model = SentenceTransformer("Alibaba-NLP/gte-base-en-v1.5", trust_remote_code=True)
        self.gts = gts
        self.embeddings = self.model.encode(gts)
        self.embeddings = self.embeddings / np.linalg.norm(self.embeddings, axis=1)[:, None]
        self.threshold = threshold

    def get_closest(self, query: str, num_results=1):
        if query in self.gts or query.lower() in self.gts:
            return [query]

        query_words = set(query.lower().split())
        candidates = []
        for gt in self.gts:
            gt_words = set(gt.lower().split())
            if any(len(word) >= 3 for word in query_words & gt_words):
                candidates.append(gt)
        if candidates:
            candidates = sorted(candidates, key=lambda x: len(x.split()))
            return [candidates[0]]

        query_embedding = self.model.encode(query)
        query_embedding = query_embedding / np.linalg.norm(query_embedding)
        similarities = np.dot(self.embeddings, query_embedding)
        indices = np.argsort(-similarities)
        indices = [i for i in indices if similarities[i] > self.threshold][:num_results]
        return [self.gts[i] for i in indices]

    def get_closest_with_scores(self, query: str, num_results=1, indices_to_adjust=None):
        if query in self.gts or query.lower() in self.gts:
            return [(query, 1.0)]

        query_words = set(query.lower().split())
        candidates = []
        for gt in self.gts:
            gt_words = set(gt.lower().split())
            if any(len(word) >= 3 for word in query_words & gt_words):
                candidates.append(gt)
        if candidates:
            candidates = sorted(candidates, key=lambda x: len(x.split()))
            return [(candidates[0], 1.0)]

        query_embedding = self.model.encode(query)
        query_embedding = query_embedding / np.linalg.norm(query_embedding)
        scores = np.dot(self.embeddings, query_embedding)
        if indices_to_adjust:
            scores[indices_to_adjust] += np.max(scores) * 0.1

        indices = np.argsort(-scores)
        indices = [i for i in indices if scores[i] > self.threshold][:num_results]
        return [(self.gts[i], scores[i]) for i in indices]
