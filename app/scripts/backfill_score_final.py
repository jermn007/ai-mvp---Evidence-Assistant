from __future__ import annotations
import json, re, asyncio, importlib
from sqlalchemy import select, update, text
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

_FINAL_RX = re.compile(r"final\s*=\s*([0-9]*\.?[0-9]+)", re.IGNORECASE)
LABEL_MAP = {"Red": 0.3, "Amber": 0.6, "Yellow": 0.6, "Green": 0.8}

def _parse_score(rationale, scores_json, rating_label):
    # 1) Try "... final=0.65 ..." in rationale
    if rationale:
        m = _FINAL_RX.search(rationale)
        if m:
            try:
                return float(m.group(1))
            except Exception:
                pass
    # 2) Average numeric values in scores_json
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
    # 3) Label fallback
    if rating_label in LABEL_MAP:
        return float(LABEL_MAP[rating_label])
    return None

async def main():
    db = importlib.import_module("app.db")
    Appraisal = getattr(db, "Appraisal")
    engine = getattr(db, "engine")

    # Ensure score_final column exists (SQLite and Postgres)
    try:
        with engine.connect() as conn:
            dialect = str(engine.dialect.name)
            if dialect == "sqlite":
                cols = [row[1] for row in conn.execute(text("PRAGMA table_info('appraisals')"))]
                if "score_final" not in cols:
                    conn.execute(text("ALTER TABLE appraisals ADD COLUMN score_final FLOAT"))
                    conn.commit()
            else:
                conn.execute(text("ALTER TABLE appraisals ADD COLUMN IF NOT EXISTS score_final DOUBLE PRECISION"))
                conn.commit()
    except Exception as e:
        print(f"Warning: could not ensure score_final column exists: {e}")

    updated = 0

    if hasattr(db, "async_session"):
        async with db.async_session() as s:
            res = await s.execute(select(Appraisal).where(Appraisal.score_final.is_(None)))
            rows = res.scalars().all()
            for a in rows:
                score = _parse_score(getattr(a, "rationale", None),
                                     getattr(a, "scores_json", None),
                                     getattr(a, "rating", None))
                if score is not None:
                    await s.execute(update(Appraisal).where(Appraisal.id == a.id).values(score_final=score))
                    updated += 1
            await s.commit()
    else:
        with db.SessionLocal() as s:
            rows = s.execute(select(Appraisal).where(Appraisal.score_final.is_(None))).scalars().all()
            for a in rows:
                score = _parse_score(getattr(a, "rationale", None),
                                     getattr(a, "scores_json", None),
                                     getattr(a, "rating", None))
                if score is not None:
                    s.execute(update(Appraisal).where(Appraisal.id == a.id).values(score_final=score))
                    updated += 1
            s.commit()

    print(f"Backfill complete. Updated {updated} rows.")

if __name__ == "__main__":
    asyncio.run(main())
