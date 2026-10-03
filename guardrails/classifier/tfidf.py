from __future__ import annotations

import pickle
from pathlib import Path

from ..normalize import normalize
from ..types import INTENTS, Classification
from .data import Example

# Baseline for the paper's comparison table: TF-IDF (word 1-2 grams + char 3-5 grams)
# with logistic regression heads. Same three outputs as the transformer.


class TfidfClassifier:
    name = "tfidf-logreg"

    def __init__(self, vectorizer, intent_clf, personal_clf, injection_clf):
        self.vectorizer = vectorizer
        self.intent_clf = intent_clf
        self.personal_clf = personal_clf
        self.injection_clf = injection_clf

    @classmethod
    def train(cls, rows: list[Example]) -> "TfidfClassifier":
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import FeatureUnion

        vectorizer = FeatureUnion([
            ("word", TfidfVectorizer(ngram_range=(1, 2), min_df=1, sublinear_tf=True)),
            ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=2, sublinear_tf=True)),
        ])
        X = vectorizer.fit_transform([normalize(e.text) for e in rows])

        def fit(y):
            return LogisticRegression(max_iter=2000, C=4.0, class_weight="balanced").fit(X, y)

        return cls(
            vectorizer,
            fit([e.intent.value for e in rows]),
            fit([e.personal for e in rows]),
            fit([e.injection for e in rows]),
        )

    def classify(self, text: str) -> Classification:
        x = self.vectorizer.transform([normalize(text)])
        probs = dict(zip(self.intent_clf.classes_, self.intent_clf.predict_proba(x)[0]))
        return Classification(
            intent_probs={i: float(probs.get(i.value, 0.0)) for i in INTENTS},
            personal=float(self.personal_clf.predict_proba(x)[0][1]),
            injection=float(self.injection_clf.predict_proba(x)[0][1]),
            model=self.name,
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as fh:
            pickle.dump(self, fh)

    @classmethod
    def load(cls, path: Path) -> "TfidfClassifier":
        with open(path, "rb") as fh:
            clf = pickle.load(fh)
        clf.name = f"tfidf:{path.stem}"
        return clf


