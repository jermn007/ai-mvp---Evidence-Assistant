# app/export.py
import csv, sys
from app.db import get_session, Record, Appraisal, PrismaCounts

def export(run_id: str):
    with get_session() as s:
        recs = s.query(Record).filter_by(run_id=run_id).all()
        apps = {a.record_id: a for a in s.query(Appraisal).filter_by(run_id=run_id).all()}
        pc = s.query(PrismaCounts).filter_by(run_id=run_id).one_or_none()

        with open(f"records_{run_id}.csv","w",newline="",encoding="utf-8") as f:
            w = csv.writer(f); w.writerow(["record_id","title","year","doi","url","source","rating"])
            for r in recs:
                rating = apps.get(r.id).rating if r.id in apps else ""
                w.writerow([r.id, r.title, r.year, r.doi, r.url, r.source, rating])

        with open(f"prisma_{run_id}.csv","w",newline="",encoding="utf-8") as f:
            w = csv.writer(f); w.writerow(["identified","deduped","screened","excluded","eligible","included"])
            if pc: w.writerow([pc.identified, pc.deduped, pc.screened, pc.excluded, pc.eligible, pc.included])

        print(f"Wrote records_{run_id}.csv and prisma_{run_id}.csv")

if __name__ == "__main__":
    export(sys.argv[1])
