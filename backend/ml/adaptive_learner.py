import logging
import numpy as np
import pickle
import os
from typing import List, Optional

logger = logging.getLogger("sentinelpay.ml")

class AdaptiveAnomalyDetector:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.model = None
        self.baseline_samples: List[List[float]] = []
        self.is_trained = False
        self.MIN_SAMPLES = 10
        self._init_model()

    def _init_model(self):
        try:
            from sklearn.ensemble import IsolationForest
            self.model = IsolationForest(
                contamination=0.05,
                n_estimators=100,
                random_state=42
            )
        except ImportError:
            logger.warning("scikit-learn not installed, using rule-based only")
            self.model = None

    def extract_features(self, tx: dict) -> List[float]:
        return [
            float(tx.get("amount", 0)),
            float(tx.get("hour_of_day", 12)),
            float(tx.get("day_of_week", 1)),
            float(tx.get("transactions_last_hour", 0)),
            float(tx.get("transactions_last_24h", 0)),
            float(tx.get("amount_vs_weekly_avg", 1.0)),
            float(tx.get("merchant_seen_before", 0)),
            float(tx.get("seconds_since_last_tx", 3600)),
        ]

    def score(self, tx: dict) -> float:
        features = self.extract_features(tx)

        if not self.is_trained or not self.model or len(self.baseline_samples) < self.MIN_SAMPLES:
            return self._rule_based_score(tx)

        try:
            raw_score = self.model.decision_function([features])[0]
            # More negative = more anomalous. Normalize to 0-1.
            normalized = max(0.0, min(1.0, (-raw_score + 0.5) * 2))
            return round(normalized, 3)
        except Exception as e:
            logger.error(f"Model scoring failed: {e}")
            return self._rule_based_score(tx)

    def learn(self, tx: dict, was_safe: bool):
        if was_safe:
            features = self.extract_features(tx)
            self.baseline_samples.append(features)

            # Rolling window of 500
            if len(self.baseline_samples) > 500:
                self.baseline_samples = self.baseline_samples[-500:]

            # Retrain when enough samples
            if len(self.baseline_samples) >= self.MIN_SAMPLES and self.model:
                try:
                    X = np.array(self.baseline_samples)
                    self.model.fit(X)
                    self.is_trained = True
                    logger.info(f"Model retrained for user {self.user_id} with {len(self.baseline_samples)} samples")
                except Exception as e:
                    logger.error(f"Model training failed: {e}")

    def _rule_based_score(self, tx: dict) -> float:
        score = 0.0

        amount = tx.get("amount", 0)
        weekly_avg = tx.get("weekly_avg", 500)
        if weekly_avg > 0 and amount > weekly_avg * 3:
            score += 0.4

        if tx.get("transactions_last_hour", 0) > 5:
            score += 0.3

        hour = tx.get("hour_of_day", 12)
        if hour < 5 or hour > 23:
            score += 0.2

        if not tx.get("merchant_seen_before", True):
            score += 0.1

        return min(round(score, 3), 1.0)

    def save(self, path: str = None):
        path = path or f"ml_model_{self.user_id}.pkl"
        try:
            with open(path, "wb") as f:
                pickle.dump({
                    "user_id": self.user_id,
                    "baseline_samples": self.baseline_samples,
                    "is_trained": self.is_trained,
                    "model": self.model
                }, f)
            logger.info(f"Model saved to {path}")
        except Exception as e:
            logger.error(f"Model save failed: {e}")

    @staticmethod
    def load(path: str) -> Optional["AdaptiveAnomalyDetector"]:
        try:
            with open(path, "rb") as f:
                data = pickle.load(f)
            detector = AdaptiveAnomalyDetector(data["user_id"])
            detector.baseline_samples = data["baseline_samples"]
            detector.is_trained = data["is_trained"]
            detector.model = data["model"]
            return detector
        except Exception as e:
            logger.error(f"Model load failed: {e}")
            return None

    def get_stats(self) -> dict:
        return {
            "user_id": self.user_id,
            "is_trained": self.is_trained,
            "sample_count": len(self.baseline_samples),
            "min_samples_needed": self.MIN_SAMPLES
        }
