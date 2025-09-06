from __future__ import annotations
from app.rubric import Rubric

def main():
    r = Rubric.load("rubric.yaml")
    print({
        "weights": r.weights,
        "amber_min": r.amber_min,
        "green_min": r.green_min,
        "recency": r.recency,
    })
    rating, scores = r.rate(
        2022,
        "Randomized controlled trial of team-based learning",
        "Blinded assessor; validated instrument; small sample",
    )
    print({"rating": rating, "scores": scores})

if __name__ == "__main__":
    main()

