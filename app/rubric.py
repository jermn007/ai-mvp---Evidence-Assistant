# app/rubric.py
from __future__ import annotations
import yaml
from dataclasses import dataclass
from typing import Dict, Tuple

@dataclass
class Rubric:
    thresholds: Dict[str, float]
    weights: Dict[str, float]
    recency: Dict[str, int]
    design_pos: list[str]
    design_neg: list[str]
    bias_pos: list[str]
    bias_neg: list[str]

    @classmethod
    def load(cls, path: str = "rubric.yaml") -> "Rubric":
        with open(path, "r", encoding="utf-8") as f:
            y = yaml.safe_load(f)
        return cls(
            thresholds=y["thresholds"],
            weights=y["weights"],
            recency=y["recency"],
            design_pos=[c.lower() for c in y["design_cues"]["positive"]],
            design_neg=[c.lower() for c in y["design_cues"]["negative"]],
            bias_pos=[c.lower() for c in y["bias_cues"]["positive"]],
            bias_neg=[c.lower() for c in y["bias_cues"]["negative"]],
        )

    def score_recency(self, year: int | None) -> float:
        if not year:
            return 0.5
        if year >= self.recency["recent_year"]:
            return 1.0
        if year >= self.recency["ok_year"]:
            return 0.7
        return 0.4

    def _count_cues(self, text: str, pos: list[str], neg: list[str]) -> Tuple[int,int]:
        t = (text or "").lower()
        return sum(p in t for p in pos), sum(n in t for n in neg)

    def score_design(self, text: str) -> float:
        p, n = self._count_cues(text, self.design_pos, self.design_neg)
        base = 0.5 + 0.1 * p - 0.1 * n
        return max(0.0, min(1.0, base))

    def score_bias(self, text: str) -> float:
        p, n = self._count_cues(text, self.bias_pos, self.bias_neg)
        base = 0.5 + 0.1 * p - 0.1 * n
        return max(0.0, min(1.0, base))

    def rate(self, year: int | None, title: str, abstract: str | None):
        text = f"{title}\n{abstract or ''}"
        rec = self.score_recency(year)
        des = self.score_design(text)
        bia = self.score_bias(text)
        w = self.weights
        final = rec*w["recency"] + des*w["design"] + bia*w["bias"]
        thr = self.thresholds
        rating = "Green" if final >= thr["green"] else ("Amber" if final >= thr["amber"] else "Red")
        return rating, {"recency": rec, "design": des, "bias": bia, "final": final}
