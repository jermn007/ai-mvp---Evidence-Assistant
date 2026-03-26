from __future__ import annotations
import json
from tabulate import tabulate

from app.db import (
    init_db,
    get_session,
    SearchRun,
    Record,
    Appraisal,
    PrismaCounts,
    Screening,
)

def main():
    init_db()
    with get_session() as s:
        runs = (
            s.query(SearchRun)
            .order_by(SearchRun.created_at.desc())
            .limit(5)
            .all()
        )
        print("\nLast runs:")
        if runs:
            print(
                tabulate(
                    [[r.id, r.query, r.created_at] for r in runs],
                    headers=["run_id", "query", "created_at"],
                )
            )
        else:
            print("(none)")
            return

        # Inspect the most recent run
        run = runs[0]
        print(f"\nRecords for run {run.id}: ", end="")

        recs = s.query(Record).filter_by(run_id=run.id).all()
        print(len(recs))
        if recs:
            print(
                tabulate(
                    [[r.id, (r.title or "")[:60], r.source, r.year] for r in recs],
                    headers=["record_id", "title", "source", "year"],
                )
            )

        apps = s.query(Appraisal).filter_by(run_id=run.id).all()
        print(f"\nAppraisals: {len(apps)}")
        if apps:
            rows = []
            for a in apps:
                try:
                    scores = json.loads(a.scores_json or "{}")
                except Exception:
                    scores = {}
                rows.append([a.record_id, a.rating, scores])
            print(tabulate(rows, headers=["record_id", "rating", "scores"]))

        pc = s.query(PrismaCounts).filter_by(run_id=run.id).one_or_none()
        if pc:
            print(
                "\nPRISMA:",
                pc.identified,
                pc.deduped,
                pc.screened,
                pc.excluded,
                pc.eligible,
                pc.included,
            )
        else:
            print("\nPRISMA: (none)")

        # Exclusion reasons breakdown
        reasons = {}
        for sc in s.query(Screening).filter_by(run_id=run.id).all():
            if sc.decision.lower() == "exclude":
                key = sc.reason or "unspecified"
                reasons[key] = reasons.get(key, 0) + 1
        print("\nExclude reasons:", reasons or "(none)")

if __name__ == "__main__":
    main()
