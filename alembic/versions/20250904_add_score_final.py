"""add score_final to appraisals, backfill, add indexes"""

from __future__ import annotations
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
import json
import re

# !! set this to your real previous revision id
revision = "20250904_add_score_final"
down_revision = "5a2ea3e447f0"
branch_labels = None
depends_on = None

_FINAL_RX = re.compile(r"final\s*=\s*([0-9]*\.?[0-9]+)", re.IGNORECASE)

def _parse_score(rationale: str | None, scores_json: str | None, rating_label: str | None) -> float | None:
    # 1) Try to extract "... final=0.65 ..." from rationale
    if rationale:
        m = _FINAL_RX.search(rationale)
        if m:
            try:
                return float(m.group(1))
            except Exception:
                pass
    # 2) Try to average numeric values from scores_json
    if scores_json:
        try:
            obj = json.loads(scores_json)
            nums = []
            for v in obj.values():
                try:
                    nums.append(float(v))
                except Exception:
                    pass
            if nums:
                return float(sum(nums) / len(nums))
        except Exception:
            pass
    # 3) Optional: map labels to a rough numeric scale (tweak if you want)
    label_map = {"Red": 0.3, "Amber": 0.6, "Yellow": 0.6, "Green": 0.8}
    if rating_label and rating_label in label_map:
        return float(label_map[rating_label])
    return None

def upgrade():
    conn = op.get_bind()

    # 1) Add nullable numeric column
    op.add_column("appraisals", sa.Column("score_final", sa.Float(), nullable=True))

    # 2) Backfill in chunks (id, rationale, scores_json, rating)
    #    Keep it simple & safe; this runs fine for MVP-sized tables.
    sel = text("""
        SELECT id, rationale, scores_json, rating
        FROM appraisals
        WHERE score_final IS NULL
    """)
    upd = text("UPDATE appraisals SET score_final = :score WHERE id = :id")

    result = conn.execute(sel)
    rows = result.fetchall()
    for r in rows:
        score = _parse_score(r.rationale, r.scores_json, r.rating)
        if score is not None:
            conn.execute(upd, {"score": score, "id": r.id})

    # 3) Useful indexes for paging and filters
    #    (If they already exist, this will error; create once.)
    op.create_index("ix_appraisals_run_id_score_final", "appraisals", ["run_id", "score_final"])
    op.create_index("ix_appraisals_run_id_rating", "appraisals", ["run_id", "rating"])

def downgrade():
    op.drop_index("ix_appraisals_run_id_rating", table_name="appraisals")
    op.drop_index("ix_appraisals_run_id_score_final", table_name="appraisals")
    op.drop_column("appraisals", "score_final")
