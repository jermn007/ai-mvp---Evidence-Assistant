# app/rubric.py
from __future__ import annotations
import re
import yaml
from dataclasses import dataclass
from typing import Dict, Tuple


def _parse_thresholds(thr: dict) -> tuple[float, float]:
    """
    Support two schemas:
    - v1: { green: 0.75, amber: 0.55 }
    - v2: { green: "score_final >= 0.75", amber: "0.55 <= score_final < 0.75", red: ... }
    Returns (amber_min, green_min) as floats.
    """
    # v1 numeric
    if isinstance(thr.get("green"), (int, float)) and isinstance(thr.get("amber"), (int, float)):
        return float(thr["amber"]), float(thr["green"])

    # v2 string expressions
    amber_min = 0.55
    green_min = 0.75
    g = thr.get("green")
    a = thr.get("amber")
    if isinstance(g, str):
        m = re.search(r"([0-9]+(?:\.[0-9]+)?)", g)
        if m:
            green_min = float(m.group(1))
    if isinstance(a, str):
        m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*<=\s*score_final", a)
        if m:
            amber_min = float(m.group(1))
        else:
            m2 = re.search(r"([0-9]+(?:\.[0-9]+)?)", a)
            if m2:
                amber_min = float(m2.group(1))
    return amber_min, green_min


@dataclass
class Rubric:
    # Internals normalized to recency/design/bias weights
    weights: Dict[str, float]
    # Recency year bands
    recency: Dict[str, int]
    # Cue lists (fallback if not provided by YAML)
    design_pos: list[str]
    design_neg: list[str]
    bias_pos: list[str]
    bias_neg: list[str]
    # Threshold cutoffs
    amber_min: float
    green_min: float

    @classmethod
    def load(cls, path: str = "rubric.yaml") -> "Rubric":
        with open(path, "r", encoding="utf-8") as f:
            y = yaml.safe_load(f) or {}

        weights_y = y.get("weights", {}) or {}
        thresholds_y = y.get("thresholds", {}) or {}

        # Recency years: fallback defaults if missing (v2 doesn't define these)
        recency = y.get("recency") or {"recent_year": 2021, "ok_year": 2018}

        # Determine thresholds
        amber_min, green_min = _parse_thresholds(thresholds_y)

        # Detect schema: v1 expects keys recency/design/bias
        if all(k in weights_y for k in ("recency", "design", "bias")):
            w_rec = float(weights_y.get("recency", 0.1))
            w_des = float(weights_y.get("design", 0.45))
            w_bia = float(weights_y.get("bias", 0.45))
        else:
            # v2 fine-grained weights; map to our 3 buckets
            w_rec = float(weights_y.get("recency", 0.1))
            w_bia = float(weights_y.get("risk_of_bias_avg", 0.2))
            designish_keys = [
                "design_strength",
                "validated_measure_used",
                "kirkpatrick_level",
                "intervention_replicability",
                "learner_match",
                "context_match",
            ]
            w_des = sum(float(weights_y.get(k, 0.0)) for k in designish_keys)
            # If everything is zero, fallback sane defaults
            total = w_rec + w_des + w_bia
            if total <= 0:
                w_rec, w_des, w_bia = 0.3, 0.4, 0.3
        # Normalize to 1
        total = w_rec + w_des + w_bia
        if total > 0:
            w_rec, w_des, w_bia = w_rec/total, w_des/total, w_bia/total

        # Cue lists: v1 provides them; v2 does not — use defaults
        def _lower_list(xs):
            return [str(x).lower() for x in (xs or [])]

        design_pos = _lower_list(((y.get("design_cues") or {}).get("positive"))) or [
            "randomized", "controlled", "rct", "quasi-experimental", "cluster",
            "control group", "pretest", "posttest", "systematic review", "meta-analysis",
        ]
        design_neg = _lower_list(((y.get("design_cues") or {}).get("negative"))) or [
            "case report", "opinion", "editorial", "letter", "single-group", "pilot only",
        ]
        bias_pos = _lower_list(((y.get("bias_cues") or {}).get("positive"))) or [
            "blinded", "registered", "validated", "consort", "prisma", "low risk of bias",
        ]
        bias_neg = _lower_list(((y.get("bias_cues") or {}).get("negative"))) or [
            "self-report", "small sample", "selection bias", "confounding", "attrition",
        ]

        return cls(
            weights={"recency": w_rec, "design": w_des, "bias": w_bia},
            recency=recency,
            design_pos=design_pos,
            design_neg=design_neg,
            bias_pos=bias_pos,
            bias_neg=bias_neg,
            amber_min=amber_min,
            green_min=green_min,
        )

    def score_recency(self, year: int | None) -> float:
        if not year:
            return 0.5
        try:
            recent = int(self.recency["recent_year"])  # type: ignore[index]
            ok = int(self.recency["ok_year"])          # type: ignore[index]
        except Exception:
            recent, ok = 2021, 2018
        if year >= recent:
            return 1.0
        if year >= ok:
            return 0.7
        return 0.4

    def _count_cues(self, text: str, pos: list[str], neg: list[str]) -> Tuple[int, int]:
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
        final = rec * w["recency"] + des * w["design"] + bia * w["bias"]
        if final >= self.green_min:
            rating = "Green"
        elif final >= self.amber_min:
            rating = "Amber"
        else:
            rating = "Red"
        return rating, {"recency": rec, "design": des, "bias": bia, "final": final}
