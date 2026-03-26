from __future__ import annotations
import os
from uuid import uuid4
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from app.graph.build import get_graph
from app.persist import persist_run

def main():
    graph = get_graph()
    inputs = {"query": "active learning in higher education"}
    config = {"configurable": {"thread_id": str(uuid4())}}  # <- important
    final = graph.invoke(inputs, config=config)
    run_id = persist_run(final)
    print(f"\nRun saved with run_id={run_id}")
    print("PRISMA:", final["prisma"].model_dump())
    print("Appraisals:", [a.model_dump() for a in final["appraisals"]])

if __name__ == "__main__":
    main()
