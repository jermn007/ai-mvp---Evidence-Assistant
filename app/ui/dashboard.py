from __future__ import annotations
import os
import json
import math
from datetime import datetime
import httpx
import pandas as pd
import streamlit as st

DEFAULT_BASE = os.getenv("EA_API_BASE", "http://127.0.0.1:8000")

@st.cache_data(ttl=15)
def fetch_json(url: str):
    with httpx.Client(timeout=30) as client:
        r = client.get(url)
        r.raise_for_status()
        return r.json()

def main():
    st.set_page_config(page_title="Evidence Assistant Dashboard", layout="wide")
    st.title("Evidence Assistant Dashboard")

    base = st.sidebar.text_input("API base", value=DEFAULT_BASE)
    limit = st.sidebar.number_input("Runs per page", min_value=5, max_value=100, value=20, step=5)

    # --- Plan and Run (PRESS) ---
    st.markdown("## Plan and Run")
    with st.expander("Build PRESS plan from LICO and run", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            learner = st.text_input("Learner", value="prelicensure nursing students")
            context = st.text_input("Context", value="university and clinical")
            years_str = st.text_input("Years (e.g., 2018-)", value=os.getenv("PRESS_YEAR_MIN", "2019-"))
        with c2:
            intervention = st.text_input("Intervention", value="simulation-based learning")
            outcome = st.text_input("Outcome", value="skills and attitudes")
            src_default = ["PubMed", "ERIC", "Crossref", "SemanticScholar", "GoogleScholar", "arXiv"]
            sources_sel = st.multiselect("Sources", options=src_default, default=src_default)
        c3, c4 = st.columns(2)
        with c3:
            template = st.selectbox("Template", options=["education","clinical","general"], index=0)
        with c4:
            use_stock = st.checkbox("Use stock scaffolds (template)", value=True)

        plan_state = st.session_state.setdefault("press_plan", None)

        colp1, colp2, colp3 = st.columns(3)
        if colp1.button("Build Plan"):
            body = {
                "lico": {
                    "learner": learner,
                    "intervention": intervention,
                    "context": context,
                    "outcome": outcome,
                },
                "template": template,
                "use_stock": use_stock,
            }
            try:
                with httpx.Client(timeout=60) as client:
                    r = client.post(f"{base}/press/plan", json=body)
                    r.raise_for_status()
                    plan_built = r.json()
                    st.session_state["press_plan"] = plan_built
                    st.session_state["press_plan_original"] = plan_built
            except Exception as e:
                st.error(f"Plan build failed: {e}")
        if colp2.button("Add PubMed Hits"):
            body = {
                "lico": {
                    "learner": learner,
                    "intervention": intervention,
                    "context": context,
                    "outcome": outcome,
                },
                "template": template,
                "use_stock": use_stock,
            }
            try:
                with httpx.Client(timeout=120) as client:
                    r = client.post(f"{base}/press/plan/hits", json=body)
                    r.raise_for_status()
                    st.session_state["press_plan"] = r.json()
            except Exception as e:
                st.error(f"Hits lookup failed: {e}")
        if colp3.button("Run with Plan"):
            plan = st.session_state.get("press_plan")
            if not plan:
                st.warning("Build a plan first.")
            else:
                try:
                    payload = {"plan": plan, "sources": sources_sel}
                    with httpx.Client(timeout=300) as client:
                        r = client.post(f"{base}/run/press", json=payload)
                        r.raise_for_status()
                        resp = r.json()
                        st.session_state["last_run_with_plan_resp"] = resp
                        st.success(f"Run created: {resp.get('run_id')}")
                        st.write({k: resp.get(k) for k in ["run_id","n_appraised","years"]})
                except Exception as e:
                    st.error(f"Run with plan failed: {e}")

        plan_view = st.session_state.get("press_plan")
        if plan_view:
            st.caption("Current PRESS plan (MEDLINE excerpt)")
            med = (plan_view.get("strategies") or {}).get("MEDLINE") or {}
            lines = med.get("lines") or []
            dfp = pd.DataFrame(lines)
            if not dfp.empty:
                # Editable line table
                allowed_types = ["Learner","Intervention","Context","Outcome","Combine","Limits","MeSH","Text"]
                colcfg = {}
                if "type" in dfp.columns:
                    try:
                        from streamlit import column_config as cc  # type: ignore
                        colcfg["type"] = cc.SelectboxColumn(options=allowed_types)
                    except Exception:
                        pass
                edited = st.data_editor(
                    dfp[[c for c in ["n","type","text","hits"] if c in dfp.columns]],
                    num_rows="dynamic",
                    use_container_width=True,
                    column_config=colcfg,
                    key="press_plan_line_editor",
                )

                col_e1, col_e2 = st.columns(2)
                if col_e1.button("Apply line edits"):
                    try:
                        # Normalize and validate
                        rows = edited.to_dict(orient="records") if isinstance(edited, pd.DataFrame) else list(edited)
                        new_lines = []
                        for row in rows:
                            t = str(row.get("type", "Text"))
                            if t not in allowed_types:
                                t = "Text"
                            txt = str(row.get("text") or "").strip()
                            if not txt:
                                continue
                            new_lines.append({"type": t, "text": txt, "hits": row.get("hits")})
                        # Renumber sequentially
                        out_lines = []
                        for i, ln in enumerate(new_lines, start=1):
                            out_lines.append({"n": i, **{k: v for k, v in ln.items() if k != "n"}})
                        st.session_state["press_plan"]["strategies"]["MEDLINE"]["lines"] = out_lines
                        st.success("Applied edits to plan lines.")
                    except Exception as e:
                        st.error(f"Failed to apply edits: {e}")
                if col_e2.button("Reset lines"):
                    if st.session_state.get("press_plan_original"):
                        st.session_state["press_plan"] = st.session_state["press_plan_original"]
                        st.success("Reset plan lines to original.")
                    else:
                        st.info("No original plan stored yet. Build a plan first.")
            else:
                st.write("No lines to display.")

            # Derive queries (PubMed and generic) from the plan, without running
            try:
                with httpx.Client(timeout=60) as client:
                    r = client.post(f"{base}/press/plan/queries", json={"plan": plan_view})
                    r.raise_for_status()
                    qinfo = r.json()
                st.markdown("#### Derived queries")
                st.code(qinfo.get("query_pubmed", ""), language="text")
                st.caption(f"Generic query for other sources (years={qinfo.get('years') or 'n/a'})")
                st.code(qinfo.get("query_generic", ""), language="text")
            except Exception as e:
                st.warning(f"Could not derive queries: {e}")

    # Runs list
    runs_data = fetch_json(f"{base}/runs.page.json?limit={limit}&offset=0")
    items = runs_data.get("items", [])
    if not items:
        st.info("No runs found. Trigger a run via the API.")
        return

    run_options = { f"{it['id']} — {it.get('query','')[:60]}": it['id'] for it in items }
    sel_label = st.sidebar.selectbox("Select a run", list(run_options.keys()))
    run_id = run_options[sel_label]

    # Summary
    summary = fetch_json(f"{base}/runs/{run_id}/summary.json")
    counts = summary.get("counts", {})
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    col1.metric("Identified", counts.get("identified", 0))
    col2.metric("Deduped", counts.get("deduped", 0))
    col3.metric("Screened", counts.get("screened", 0))
    col4.metric("Excluded", counts.get("excluded", 0))
    col5.metric("Eligible", counts.get("eligible", 0))
    col6.metric("Included", counts.get("included", 0))

    # Ratings and sources
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Ratings")
        labs = summary.get("label_counts", {})
        df_labs = pd.DataFrame({"label": list(labs.keys()), "count": list(labs.values())})
        if not df_labs.empty:
            st.bar_chart(df_labs.set_index("label"))
        else:
            st.write("No appraisals")
    with c2:
        st.subheader("Per-source (kept records)")
        srcs = summary.get("source_counts_kept", {})
        df_src = pd.DataFrame({"source": list(srcs.keys()), "count": list(srcs.values())})
        if not df_src.empty:
            st.bar_chart(df_src.set_index("source"))
        else:
            st.write("No records")

    # Exclusion reasons chart
    st.subheader("Exclusion reasons (PRISMA)")
    reasons = summary.get("exclude_reasons", {}) or {}
    if reasons:
        df_re = pd.DataFrame({"reason": list(reasons.keys()), "count": list(reasons.values())})
        st.bar_chart(df_re.set_index("reason"))
    else:
        st.write("No exclusion reasons recorded.")

    # Table with filters
    st.subheader("Records")
    view_choice = st.radio("View", options=["Included (appraised)", "Excluded (screened)"])
    # Controls (client -> server params)
    selected_labels = st.multiselect("Labels", options=["Red","Amber","Green"], default=["Red","Amber","Green"])
    score_min = st.slider("Min score_final", 0.0, 1.0, 0.0, 0.05)
    default_sources = ["PubMed", "Crossref", "ERIC", "SemanticScholar", "GoogleScholar", "arXiv"]
    sources_all = sorted(list(set(default_sources) | set((summary.get("source_counts_kept") or {}).keys())))
    selected_sources = st.multiselect("Sources", options=sources_all, default=sources_all)
    # Use sensible defaults within widget bounds to avoid Streamlit errors
    current_year = datetime.utcnow().year
    year_min = st.number_input("Year min", min_value=1900, max_value=2100, value=1900)
    year_max = st.number_input("Year max", min_value=1900, max_value=2100, value=min(2100, max(current_year, 1900)))
    q = st.text_input("Search title/abstract", "")
    page_size = st.number_input("Page size", min_value=10, max_value=200, value=20, step=10)
    page = st.number_input("Page", min_value=1, value=1)

    if view_choice.startswith("Included"):
        # Build query params
        params = {
            "limit": int(page_size),
            "offset": int((page-1) * page_size),
            "order_by": "score_final",
            "order_dir": "desc",
        }
        if selected_labels and len(selected_labels) < 3:
            params["label_in"] = ",".join(selected_labels)
        if score_min > 0:
            params["score_min"] = score_min
        if selected_sources and len(selected_sources) < len(sources_all):
            params["source_in"] = ",".join(selected_sources)
        if year_min > 0:
            params["year_min"] = int(year_min)
        if year_max < 2100:
            params["year_max"] = int(year_max)
        if q:
            params["q"] = q

        # Fetch paged results
        try:
            with httpx.Client(timeout=30) as client:
                r = client.get(f"{base}/runs/{run_id}/records_with_appraisals.page.json", params=params)
                r.raise_for_status()
                page_data = r.json()
        except Exception as e:
            st.error(f"Failed to load records: {e}")
            page_data = {"items": [], "total": 0, "limit": params.get("limit", 20), "offset": params.get("offset", 0)}

        items = page_data.get("items", [])
        if isinstance(items, dict):
            items = list(items.values()) if items else []
        df = pd.DataFrame(items)
        if not df.empty:
            st.caption(f"Total: {page_data.get('total', 0)} | Showing {len(df)} items (page {page})")
            st.dataframe(df[[c for c in ["rating","score_final","year","title","source","url"] if c in df.columns]], use_container_width=True)
        else:
            st.write("No items match the filters.")
    else:
        # Excluded (screened) with paging and filters via API
        reasons_opts = list((summary.get("exclude_reasons") or {}).keys())
        reasons_sel = st.multiselect("Reasons", options=reasons_opts, default=reasons_opts)
        page_size_ex = st.number_input("Page size (excluded)", min_value=10, max_value=500, value=20, step=10)
        page_ex = st.number_input("Page (excluded)", min_value=1, value=1)

        params = {
            "limit": int(page_size_ex),
            "offset": int((page_ex-1) * page_size_ex),
            "decision": "exclude",
            "order_by": "year",
            "order_dir": "desc",
        }
        if reasons_sel and len(reasons_sel) < len(reasons_opts):
            params["reason_in"] = ",".join(reasons_sel)
        if selected_sources and len(selected_sources) < len(sources_all):
            params["source_in"] = ",".join(selected_sources)
        if year_min > 0:
            params["year_min"] = int(year_min)
        if year_max < 2100:
            params["year_max"] = int(year_max)
        if q:
            params["q"] = q

        try:
            with httpx.Client(timeout=60) as client:
                r = client.get(f"{base}/runs/{run_id}/screenings_with_records.page.json", params=params)
                r.raise_for_status()
                data_ex = r.json()
        except Exception as e:
            st.error(f"Failed to load screenings: {e}")
            data_ex = {"items": [], "total": 0}

        items_ex = data_ex.get("items", [])
        dfe = pd.DataFrame(items_ex)
        if not dfe.empty:
            st.caption(f"Total: {data_ex.get('total', 0)} | Showing {len(dfe)} items (page {page_ex})")
            st.dataframe(dfe[[c for c in ["decision","reason","year","title","source","url"] if c in dfe.columns]], use_container_width=True)
        else:
            st.write("No excluded items.")

    # Show queries after run-with-plan, if present
    last_run = st.session_state.get("last_run_with_plan_resp")
    if last_run:
        with st.expander("Last run queries", expanded=False):
            st.write({k: last_run.get(k) for k in ["query_pubmed","query_generic","years"]})

    # Downloads
    st.markdown("### Downloads")
    st.write("PRISMA/Screenings and joined appraisals CSVs exposed by the API:")
    st.code(f"curl -o prisma_{run_id}.csv {base}/runs/{run_id}/prisma.summary.csv")
    st.code(f"curl -o screenings_{run_id}.csv {base}/runs/{run_id}/screenings_with_records.csv")
    st.code(f"curl -o records_{run_id}.csv {base}/runs/{run_id}/records_with_appraisals.csv")

if __name__ == "__main__":
    main()
