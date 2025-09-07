from __future__ import annotations
import os
import json
import math
from datetime import datetime, timezone
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
        c3, c4, c5 = st.columns(3)
        with c3:
            template = st.selectbox("Template", options=["education","clinical","general"], index=0)
        with c4:
            use_stock = st.checkbox("Use stock scaffolds (template)", value=True)
        with c5:
            enable_ai = st.checkbox("🤖 Enable AI assistance", value=False, help="Get AI-powered suggestions for LICO terms and strategy analysis")

        plan_state = st.session_state.setdefault("press_plan", None)

        # AI assistance section
        if enable_ai:
            with st.expander("🤖 AI Assistant", expanded=True):
                col_ai1, col_ai2, col_ai3 = st.columns(3)
                
                with col_ai1:
                    if st.button("🎯 Smart Template", help="Get AI recommendation for best template"):
                        lico_data = {
                            "learner": learner,
                            "intervention": intervention,
                            "context": context,
                            "outcome": outcome,
                        }
                        try:
                            with httpx.Client(timeout=30) as client:
                                r = client.post(f"{base}/ai/suggest-template", json=lico_data)
                                if r.status_code == 200:
                                    result = r.json()
                                    st.session_state["suggested_template"] = result.get("suggested_template")
                                    st.success(f"🎯 Suggested template: **{result.get('suggested_template')}**")
                                    st.info(result.get("reasoning", ""))
                                else:
                                    st.error("Template suggestion unavailable")
                        except Exception as e:
                            st.error(f"Template suggestion failed: {e}")
                
                with col_ai2:
                    if st.button("💡 Enhance LICO", help="Get AI suggestions for improving LICO terms"):
                        lico_data = {
                            "learner": learner,
                            "intervention": intervention,
                            "context": context,
                            "outcome": outcome,
                        }
                        request_data = {
                            "lico": lico_data,
                            "research_domain": f"{intervention} in {context}" if intervention and context else None
                        }
                        try:
                            with httpx.Client(timeout=60) as client:
                                r = client.post(f"{base}/ai/enhance-lico", json=request_data)
                                if r.status_code == 200:
                                    result = r.json()
                                    st.session_state["ai_enhancement"] = result
                                    st.success("💡 AI suggestions generated! Check below for recommendations.")
                                else:
                                    st.error("AI enhancement unavailable")
                        except Exception as e:
                            st.error(f"AI enhancement failed: {e}")
                
                with col_ai3:
                    if st.button("🔍 AI Status", help="Check AI service status"):
                        try:
                            with httpx.Client(timeout=10) as client:
                                r = client.get(f"{base}/ai/status")
                                if r.status_code == 200:
                                    status = r.json()
                                    if status.get("available"):
                                        st.success(f"✅ AI Available (Model: {status.get('model', 'Unknown')})")
                                        st.write("Features:", ", ".join(status.get("features", [])))
                                    else:
                                        st.warning("⚠️ AI Unavailable - Check OPENAI_API_KEY")
                                else:
                                    st.error("Cannot check AI status")
                        except Exception as e:
                            st.error(f"Status check failed: {e}")
                
        # Display AI enhancement results if available (moved outside AI section for better visibility)
        if "ai_enhancement" in st.session_state and st.session_state["ai_enhancement"]:
            with st.container():
                st.markdown("---")
                st.markdown("#### 🧠 AI Enhancement Results")
                st.success("💡 AI has analyzed your LICO terms and provided suggestions below!")
                
                enhancement = st.session_state["ai_enhancement"]
                
                tab1, tab2, tab3 = st.tabs(["📝 Term Suggestions", "🏷️ MeSH Terms", "💭 AI Analysis"])
                
                with tab1:
                    st.markdown("**💡 Suggested additional search terms:**")
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        if enhancement.get("learner_suggestions"):
                            st.markdown("**🎓 Learner terms:**")
                            for term in enhancement["learner_suggestions"][:5]:  # Show first 5
                                st.write(f"• {term}")
                                
                        if enhancement.get("intervention_suggestions"):
                            st.markdown("**⚡ Intervention terms:**")
                            for term in enhancement["intervention_suggestions"][:5]:
                                st.write(f"• {term}")
                    
                    with col2:
                        if enhancement.get("context_suggestions"):
                            st.markdown("**🏢 Context terms:**")
                            for term in enhancement["context_suggestions"][:5]:
                                st.write(f"• {term}")
                                
                        if enhancement.get("outcome_suggestions"):
                            st.markdown("**📊 Outcome terms:**")
                            for term in enhancement["outcome_suggestions"][:5]:
                                st.write(f"• {term}")
                
                with tab2:
                    st.markdown("**🏷️ Recommended MeSH headings:**")
                    mesh_suggestions = enhancement.get("mesh_suggestions", {})
                    if mesh_suggestions:
                        for category, terms in mesh_suggestions.items():
                            if terms:
                                st.markdown(f"**{category.title()}:**")
                                for term in terms[:3]:  # Show first 3 per category
                                    st.write(f"• {term}")
                                st.write("")
                    else:
                        st.info("No specific MeSH suggestions available for this query.")
                
                with tab3:
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("🎯 Recommended Template", 
                                enhancement.get("template_recommendation", "Not specified"))
                    with col2:
                        if enhancement.get("template_recommendation") != template:
                            st.warning(f"💡 Consider switching to '{enhancement.get('template_recommendation')}' template")
                        else:
                            st.success("✅ You're using the recommended template!")
                    
                    st.markdown("**🤖 AI Explanation:**")
                    st.info(enhancement.get("explanation", "No explanation provided"))
                
                # Clear button
                if st.button("🗑️ Clear AI Suggestions"):
                    del st.session_state["ai_enhancement"]
                    st.rerun()

        colp1, colp2, colp3 = st.columns(3)
        if colp1.button("Build Plan"):
            # Use suggested template if available
            selected_template = st.session_state.get("suggested_template", template)
            
            body = {
                "lico": {
                    "learner": learner,
                    "intervention": intervention,
                    "context": context,
                    "outcome": outcome,
                },
                "template": selected_template,
                "use_stock": use_stock,
                "enable_ai": enable_ai,
                "research_domain": f"{intervention} in {context}" if intervention and context else None
            }
            
            endpoint = "/press/plan/ai-enhanced" if enable_ai else "/press/plan"
            
            try:
                with httpx.Client(timeout=120) as client:
                    r = client.post(f"{base}{endpoint}", json=body)
                    r.raise_for_status()
                    result = r.json()
                    
                    if enable_ai and "base_plan" in result:
                        # AI-enhanced response
                        st.session_state["press_plan"] = result["base_plan"]
                        st.session_state["press_plan_original"] = result["base_plan"]
                        st.session_state["ai_strategy_analysis"] = result.get("strategy_analysis")
                        if result.get("ai_available"):
                            st.success("🤖 AI-enhanced plan generated successfully!")
                        else:
                            st.warning("⚠️ AI unavailable - generated standard plan")
                    else:
                        # Standard response
                        st.session_state["press_plan"] = result
                        st.session_state["press_plan_original"] = result
                        
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
                # Enhanced editable line table with better UX
                allowed_types = ["Learner","Intervention","Context","Outcome","Combine","Limits","MeSH","Text"]
                
                # Type color mapping for visual clarity
                type_colors = {
                    "Learner": "#E3F2FD", "Intervention": "#E8F5E8", "Context": "#FFF3E0", 
                    "Outcome": "#F3E5F5", "Combine": "#E0F2F1", "Limits": "#FFF8E1", 
                    "MeSH": "#E1F5FE", "Text": "#F5F5F5"
                }
                
                # Column configuration with enhanced features
                colcfg = {}
                if "type" in dfp.columns:
                    try:
                        from streamlit import column_config as cc  # type: ignore
                        colcfg["type"] = cc.SelectboxColumn(
                            options=allowed_types,
                            help="Select the type of search component"
                        )
                        colcfg["text"] = cc.TextColumn(
                            help="Enter search terms, MeSH headings, or query components",
                            validate=r"^.{1,500}$",  # Basic length validation
                            max_chars=500
                        )
                        colcfg["hits"] = cc.NumberColumn(
                            help="Estimated number of results for this component",
                            min_value=0,
                            format="%d"
                        )
                    except Exception:
                        pass
                
                # Show line count and validation status
                st.caption(f"📝 {len(dfp)} search strategy lines configured")
                
                # Add help text
                with st.expander("💡 PRESS Line Types Guide", expanded=False):
                    st.markdown("""
                    - **Learner**: Target population (e.g., "nursing students", "residents")
                    - **Intervention**: What is being studied (e.g., "simulation", "VR training")
                    - **Context**: Setting or environment (e.g., "hospital", "classroom")
                    - **Outcome**: Measured results (e.g., "knowledge", "skills", "satisfaction")
                    - **Combine**: Boolean operators and grouping (e.g., "AND", "OR")
                    - **Limits**: Filters and constraints (e.g., "2019-2024", "English")
                    - **MeSH**: Medical Subject Headings (e.g., "Education, Nursing[MeSH]")
                    - **Text**: Free text terms and phrases
                    """)
                
                edited = st.data_editor(
                    dfp[[c for c in ["n","type","text","hits"] if c in dfp.columns]],
                    num_rows="dynamic",
                    width='stretch',
                    column_config=colcfg,
                    key="press_plan_line_editor",
                    height=400,  # Fixed height for better scrolling
                )

                # Enhanced action buttons with better UX
                col_e1, col_e2, col_e3 = st.columns(3)
                
                # Validation before applying edits
                validation_issues = []
                if isinstance(edited, pd.DataFrame) and not edited.empty:
                    for idx, row in edited.iterrows():
                        if not str(row.get("text", "")).strip():
                            validation_issues.append(f"Row {idx + 1}: Text cannot be empty")
                        if len(str(row.get("text", ""))) > 500:
                            validation_issues.append(f"Row {idx + 1}: Text too long (max 500 chars)")
                
                if validation_issues:
                    st.warning("⚠️ Validation Issues:")
                    for issue in validation_issues[:5]:  # Show max 5 issues
                        st.write(f"• {issue}")
                    if len(validation_issues) > 5:
                        st.write(f"• ... and {len(validation_issues) - 5} more issues")
                
                # Apply edits button with enhanced validation
                apply_disabled = len(validation_issues) > 0
                if col_e1.button("✅ Apply Changes", disabled=apply_disabled, help="Apply your edits to the search strategy"):
                    try:
                        # Enhanced validation and normalization
                        rows = edited.to_dict(orient="records") if isinstance(edited, pd.DataFrame) else list(edited)
                        new_lines = []
                        skipped_count = 0
                        
                        for row in rows:
                            t = str(row.get("type", "Text"))
                            if t not in allowed_types:
                                t = "Text"
                            txt = str(row.get("text") or "").strip()
                            if not txt:
                                skipped_count += 1
                                continue
                            # Validate hits as non-negative integer
                            hits = row.get("hits")
                            if hits is not None:
                                try:
                                    hits = max(0, int(hits))
                                except (ValueError, TypeError):
                                    hits = None
                            new_lines.append({"type": t, "text": txt, "hits": hits})
                        
                        # Renumber sequentially
                        out_lines = []
                        for i, ln in enumerate(new_lines, start=1):
                            out_lines.append({"n": i, **{k: v for k, v in ln.items() if k != "n"}})
                        
                        st.session_state["press_plan"]["strategies"]["MEDLINE"]["lines"] = out_lines
                        success_msg = f"✅ Applied {len(out_lines)} search lines successfully"
                        if skipped_count > 0:
                            success_msg += f" (skipped {skipped_count} empty lines)"
                        st.success(success_msg)
                        st.rerun()  # Refresh to show updated query preview
                    except Exception as e:
                        st.error(f"❌ Failed to apply edits: {e}")
                        
                if col_e2.button("🔄 Reset Lines", help="Restore original plan from template"):
                    if st.session_state.get("press_plan_original"):
                        st.session_state["press_plan"] = st.session_state["press_plan_original"].copy()
                        st.success("🔄 Reset plan lines to original template")
                        st.rerun()
                    else:
                        st.info("💡 No original plan stored yet. Build a plan first.")
                        
                # Add smart suggestions button        
                if col_e3.button("💡 Smart Suggestions", help="Get AI-powered suggestions to improve your search strategy"):
                    if len(dfp) > 0:
                        # Show suggestions based on current plan structure
                        suggestions = []
                        has_learner = any(row.get("type") == "Learner" for _, row in dfp.iterrows())
                        has_intervention = any(row.get("type") == "Intervention" for _, row in dfp.iterrows())
                        has_outcome = any(row.get("type") == "Outcome" for _, row in dfp.iterrows())
                        has_limits = any(row.get("type") == "Limits" for _, row in dfp.iterrows())
                        
                        if not has_learner:
                            suggestions.append("• Consider adding **Learner** terms to specify your target population")
                        if not has_intervention:
                            suggestions.append("• Add **Intervention** terms to define what is being studied")
                        if not has_outcome:
                            suggestions.append("• Include **Outcome** terms to specify measured results")
                        if not has_limits:
                            suggestions.append("• Add **Limits** for publication years, language, or study types")
                            
                        # Check for very short or very long text entries
                        for _, row in dfp.iterrows():
                            text = str(row.get("text", ""))
                            if len(text) < 3:
                                suggestions.append(f"• Row {row.get('n', '')}: Consider expanding the search term '{text}'")
                            elif len(text) > 100:
                                suggestions.append(f"• Row {row.get('n', '')}: Consider breaking down the long term into multiple lines")
                        
                        if suggestions:
                            st.info("💡 **Suggestions to improve your search strategy:**\n\n" + "\n".join(suggestions))
                        else:
                            st.success("✨ Your search strategy looks well-structured!")
                    else:
                        st.info("💡 Add some search lines first to get personalized suggestions")
            else:
                st.write("No lines to display.")

            # Enhanced query preview with real-time updates
            st.markdown("#### 🔍 Live Query Preview")
            st.caption("These queries are automatically generated from your PRESS plan lines above")
            
            try:
                with httpx.Client(timeout=60) as client:
                    r = client.post(f"{base}/press/plan/queries", json={"plan": plan_view})
                    r.raise_for_status()
                    qinfo = r.json()
                
                # Show query statistics
                query_stats = {
                    "PubMed Query Length": len(qinfo.get("query_pubmed", "")),
                    "Generic Query Length": len(qinfo.get("query_generic", "")),
                    "Year Range": qinfo.get("years", "Not specified")
                }
                
                col_q1, col_q2, col_q3 = st.columns(3)
                col_q1.metric("PubMed Length", query_stats["PubMed Query Length"], help="Character count of PubMed query")
                col_q2.metric("Generic Length", query_stats["Generic Query Length"], help="Character count of generic query")
                col_q3.metric("Years", query_stats["Year Range"], help="Publication year filters")
                
                # Tabbed view for different queries
                tab1, tab2 = st.tabs(["📚 PubMed/MEDLINE Query", "🌐 Generic Query (Other Sources)"])
                
                with tab1:
                    pubmed_query = qinfo.get("query_pubmed", "")
                    st.code(pubmed_query, language="sql", wrap_lines=True)
                    if pubmed_query:
                        st.caption(f"💡 This query will search PubMed/MEDLINE ({len(pubmed_query)} characters)")
                        # Add copy button simulation
                        st.info("💡 **Tip**: You can copy this query and test it directly in PubMed to preview results")
                
                with tab2:
                    generic_query = qinfo.get("query_generic", "")
                    st.code(generic_query, language="text", wrap_lines=True)
                    if generic_query:
                        st.caption(f"💡 This query will search Crossref, ERIC, ArXiv, Semantic Scholar, and Google Scholar")
                        
            except Exception as e:
                st.error(f"❌ Could not generate query preview: {e}")
                st.info("💡 Make sure your PRESS plan has at least one valid search line")
        
        # Display AI strategy analysis if available
        if "ai_strategy_analysis" in st.session_state and st.session_state["ai_strategy_analysis"]:
            analysis = st.session_state["ai_strategy_analysis"]
            st.markdown("#### 🤖 AI Strategy Analysis")
            
            col_analysis1, col_analysis2 = st.columns(2)
            
            with col_analysis1:
                st.metric("Completeness Score", f"{analysis.get('completeness_score', 0):.1%}", help="Overall strategy completeness")
                
                precision = analysis.get('estimated_precision', 'unknown')
                recall = analysis.get('estimated_recall', 'unknown')
                
                precision_color = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(precision.lower(), "⚪")
                recall_color = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(recall.lower(), "⚪")
                
                st.write(f"**Estimated Precision:** {precision_color} {precision.title()}")
                st.write(f"**Estimated Recall:** {recall_color} {recall.title()}")
            
            with col_analysis2:
                st.write("**Balance Assessment:**", analysis.get('balance_assessment', 'No assessment'))
                
                if analysis.get('missing_components'):
                    st.warning("**Missing Components:**")
                    for component in analysis.get('missing_components', []):
                        st.write(f"• {component}")
            
            if analysis.get('suggestions'):
                with st.expander("💡 AI Suggestions for Improvement", expanded=False):
                    for i, suggestion in enumerate(analysis.get('suggestions', []), 1):
                        st.write(f"{i}. {suggestion}")

    # Runs list
    runs_data = fetch_json(f"{base}/runs.page.json?limit={limit}&offset=0")
    items = runs_data.get("items", [])
    if not items:
        st.info("No runs found. Trigger a run via the API.")
        return

    run_options = { f"{it['id']} — {it.get('query','')[:60]}": it['id'] for it in items }
    sel_label = st.sidebar.selectbox("Select a run", list(run_options.keys()))
    run_id = run_options[sel_label]

    # Progressive Workflow Indicators
    st.markdown("### 🔄 Systematic Review Workflow Progress")
    
    # Fetch detailed summary for workflow tracking
    summary = fetch_json(f"{base}/runs/{run_id}/summary.json")
    counts = summary.get("counts", {})
    
    # Define the 5-step workflow with progress logic
    workflow_steps = [
        {
            "name": "1️⃣ PRESS Planning",
            "description": "Search strategy development",
            "status": "completed",  # Always completed if we have a run
            "icon": "📋"
        },
        {
            "name": "2️⃣ Harvesting", 
            "description": "Multi-database search execution",
            "status": "completed" if counts.get("identified", 0) > 0 else "pending",
            "icon": "🔍",
            "metric": counts.get("identified", 0),
            "metric_label": "records found"
        },
        {
            "name": "3️⃣ Deduplication & Screening",
            "description": "Remove duplicates and apply inclusion criteria",
            "status": "completed" if counts.get("screened", 0) > 0 else ("in_progress" if counts.get("identified", 0) > 0 else "pending"),
            "icon": "🔄",
            "metric": counts.get("deduped", 0),
            "metric_label": "unique records"
        },
        {
            "name": "4️⃣ Quality Appraisal",
            "description": "Systematic quality assessment",
            "status": "completed" if counts.get("included", 0) > 0 else ("in_progress" if counts.get("screened", 0) > 0 else "pending"),
            "icon": "⭐",
            "metric": len(summary.get("label_counts", {})),
            "metric_label": "quality ratings"
        },
        {
            "name": "5️⃣ PRISMA Reporting",
            "description": "Generate systematic review report",
            "status": "completed" if all(counts.get(k, 0) >= 0 for k in ["identified", "deduped", "included"]) and counts.get("identified", 0) > 0 else "pending",
            "icon": "📊",
            "metric": counts.get("included", 0),
            "metric_label": "final studies"
        }
    ]
    
    # Create visual progress indicator
    progress_cols = st.columns(5)
    
    for i, step in enumerate(workflow_steps):
        with progress_cols[i]:
            # Status-based styling
            if step["status"] == "completed":
                status_color = "🟢"
                status_text = "Complete"
            elif step["status"] == "in_progress":
                status_color = "🟡"
                status_text = "In Progress"
            else:
                status_color = "⚪"
                status_text = "Pending"
            
            # Display step
            st.markdown(f"""
            <div style="text-align: center; padding: 10px; border-radius: 10px; border: 2px solid {'#4CAF50' if step['status'] == 'completed' else '#FFC107' if step['status'] == 'in_progress' else '#E0E0E0'}; background-color: {'#E8F5E9' if step['status'] == 'completed' else '#FFF8E1' if step['status'] == 'in_progress' else '#F5F5F5'};">
                <div style="font-size: 24px;">{step['icon']}</div>
                <div style="font-weight: bold; font-size: 12px; color: {'#2E7D32' if step['status'] == 'completed' else '#F57C00' if step['status'] == 'in_progress' else '#424242'};">{step['name']}</div>
                <div style="font-size: 10px; color: {'#4A4A4A' if step['status'] == 'completed' else '#5D4037' if step['status'] == 'in_progress' else '#666'};">{step['description']}</div>
                <div style="margin-top: 5px; font-weight: 500; color: {'#2E7D32' if step['status'] == 'completed' else '#F57C00' if step['status'] == 'in_progress' else '#757575'};">{status_color} {status_text}</div>
            </div>
            """, unsafe_allow_html=True)
            
            # Show metrics if available
            if "metric" in step and step["status"] != "pending":
                st.metric(step["metric_label"], step["metric"], label_visibility="collapsed")
    
    # Overall progress calculation
    completed_steps = sum(1 for step in workflow_steps if step["status"] == "completed")
    progress_percentage = (completed_steps / len(workflow_steps)) * 100
    
    st.progress(progress_percentage / 100, text=f"Overall Progress: {completed_steps}/{len(workflow_steps)} steps completed ({progress_percentage:.0f}%)")
    
    # Status-specific guidance
    if progress_percentage == 100:
        st.success("🎉 **Systematic review workflow completed!** Your review is ready for analysis and reporting.")
    elif progress_percentage >= 60:
        st.info("📝 **Almost there!** Complete the remaining steps to finish your systematic review.")
    elif progress_percentage >= 20:
        st.warning("⚠️ **In progress...** Your search has been executed. Continue with screening and appraisal.")
    else:
        st.error("🚀 **Getting started...** Execute your search strategy to begin the systematic review process.")
    
    st.divider()
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

    # Enhanced Results Dashboard with Advanced Filtering
    st.markdown("### 📊 Results Explorer")
    st.caption("Explore and filter your systematic review results with advanced search and sorting options")
    
    # Main view selection with enhanced options
    col_view1, col_view2 = st.columns([2, 1])
    with col_view1:
        view_choice = st.radio("📋 **View Mode**", 
                              options=["Included (appraised)", "Excluded (screened)"],
                              help="Choose between final included studies or excluded records")
    with col_view2:
        if view_choice.startswith("Included"):
            sort_options = ["Quality Score (High→Low)", "Quality Score (Low→High)", "Year (Recent→Old)", "Year (Old→Recent)", "Title (A→Z)"]
            default_sort = "Quality Score (High→Low)"
        else:
            sort_options = ["Year (Recent→Old)", "Year (Old→Recent)", "Title (A→Z)", "Exclusion Reason"]
            default_sort = "Year (Recent→Old)"
        sort_choice = st.selectbox("🔄 **Sort By**", options=sort_options, index=0, help="Choose how to sort the results")
    
    # Advanced filtering in expandable sections
    with st.expander("🔍 **Advanced Filters**", expanded=True):
        filter_col1, filter_col2, filter_col3 = st.columns(3)
        
        with filter_col1:
            st.markdown("**📊 Quality & Ratings**")
            if view_choice.startswith("Included"):
                # Use session state values if available for presets
                default_labels = ["🔴 Red", "🟡 Amber", "🟢 Green"]
                if 'selected_labels' in st.session_state:
                    default_labels = [f"🔴 {label}" if label == "Red" else f"🟡 {label}" if label == "Amber" else f"🟢 {label}" for label in st.session_state['selected_labels']]
                
                selected_labels = st.multiselect("Quality Labels", 
                                               options=["🔴 Red", "🟡 Amber", "🟢 Green"], 
                                               default=default_labels,
                                               help="Filter by quality assessment ratings")
                # Convert display labels back to API format
                selected_labels = [label.split(" ")[1] for label in selected_labels]
                
                score_min = st.slider("Minimum Quality Score", 0.0, 1.0, 
                                    st.session_state.get('score_min', 0.0), 0.05, 
                                    help="Filter studies by minimum quality score")
                score_max = st.slider("Maximum Quality Score", 0.0, 1.0, 
                                    st.session_state.get('score_max', 1.0), 0.05, 
                                    help="Filter studies by maximum quality score")
            else:
                selected_labels = ["Red", "Amber", "Green"]  # Default for excluded view
                score_min = 0.0
                score_max = 1.0
        
        with filter_col2:
            st.markdown("**📚 Sources & Timeline**")
            default_sources = ["PubMed", "Crossref", "ERIC", "SemanticScholar", "GoogleScholar", "arXiv"]
            sources_all = sorted(list(set(default_sources) | set((summary.get("source_counts_kept") or {}).keys())))
            selected_sources = st.multiselect("Database Sources", 
                                            options=sources_all, 
                                            default=st.session_state.get('selected_sources', sources_all),
                                            help="Filter by academic database source")
            
            # Smart year range defaults
            current_year = datetime.now(timezone.utc).year
            col_year1, col_year2 = st.columns(2)
            with col_year1:
                year_min = st.number_input("From Year", min_value=1900, max_value=2100, 
                                         value=st.session_state.get('year_min', 2000), 
                                         help="Earliest publication year")
            with col_year2:
                year_max = st.number_input("To Year", min_value=1900, max_value=2100, 
                                         value=st.session_state.get('year_max', min(2100, max(current_year, 1900))),
                                         help="Latest publication year")
        
        with filter_col3:
            st.markdown("**🔍 Text Search & Display**")
            q = st.text_input("Search Title/Abstract", st.session_state.get('q', ''), 
                            help="Search within title and abstract text",
                            placeholder="Enter keywords...")
            
            col_page1, col_page2 = st.columns(2)
            with col_page1:
                page_size = st.selectbox("Results per page", options=[10, 20, 50, 100], index=1,
                                       help="Number of results to show per page")
            with col_page2:
                page = st.number_input("Page", min_value=1, value=1, help="Navigate through result pages")
    
    # Quick filter presets
    with st.expander("⚡ **Quick Filter Presets**", expanded=False):
        preset_col1, preset_col2, preset_col3, preset_col4 = st.columns(4)
        
        with preset_col1:
            if st.button("🏆 **High Quality Only**", help="Show only high-quality studies (Green + score ≥ 0.7)"):
                if view_choice.startswith("Included"):
                    st.session_state.update({
                        'selected_labels': ['Green'],
                        'score_min': 0.7,
                        'score_max': 1.0
                    })
                    st.rerun()
        
        with preset_col2:
            if st.button("📅 **Recent Studies**", help="Show studies from last 5 years"):
                st.session_state.update({
                    'year_min': current_year - 5,
                    'year_max': current_year
                })
                st.rerun()
        
        with preset_col3:
            if st.button("🔬 **PubMed Only**", help="Show only PubMed/MEDLINE studies"):
                st.session_state.update({
                    'selected_sources': ['PubMed']
                })
                st.rerun()
        
        with preset_col4:
            if st.button("🔄 **Reset All Filters**", help="Clear all filters and show all results"):
                st.session_state.update({
                    'selected_labels': ['Red', 'Amber', 'Green'],
                    'score_min': 0.0,
                    'score_max': 1.0,
                    'selected_sources': sources_all,
                    'year_min': 1900,
                    'year_max': current_year,
                    'q': ''
                })
                st.rerun()

    if view_choice.startswith("Included"):
        # Build query params
        params = {
            "limit": int(page_size),
            "offset": int((page-1) * page_size),
            "order_by": "score_final" if "Quality Score" in sort_choice else "year" if "Year" in sort_choice else "title",
            "order_dir": "desc" if "High→Low" in sort_choice or "Recent→Old" in sort_choice else "asc",
        }
        if selected_labels and len(selected_labels) < 3:
            params["label_in"] = ",".join(selected_labels)
        if score_min > 0:
            params["score_min"] = score_min
        if score_max < 1.0:
            params["score_max"] = score_max
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
            # Enhanced results display with metrics and styling
            total_results = page_data.get('total', 0)
            current_start = (page - 1) * page_size + 1
            current_end = min(page * page_size, total_results)
            
            # Results summary with metrics
            res_col1, res_col2, res_col3, res_col4 = st.columns(4)
            res_col1.metric("📊 Total Results", total_results)
            res_col2.metric("📄 Current Page", f"{current_start}-{current_end}")
            
            if "rating" in df.columns:
                rating_counts = df['rating'].value_counts()
                res_col3.metric("🟢 High Quality", rating_counts.get('Green', 0))
                res_col4.metric("🔴 Low Quality", rating_counts.get('Red', 0))
            
            # Enhanced dataframe with better column configuration
            display_columns = []
            column_config = {}
            
            if "rating" in df.columns:
                # Add color coding for ratings (don't include raw rating column)
                df['rating_display'] = df['rating'].map({
                    'Green': '🟢 Green', 'Amber': '🟡 Amber', 'Red': '🔴 Red'
                }).fillna(df['rating'])
                display_columns.append("rating_display")
                column_config["rating_display"] = st.column_config.TextColumn("Quality Rating", width="small")
            
            if "score_final" in df.columns:
                display_columns.append("score_final")
                column_config["score_final"] = st.column_config.ProgressColumn(
                    "Quality Score", 
                    help="Normalized quality assessment score",
                    min_value=0.0,
                    max_value=1.0,
                    format="%.2f",
                    width="small"
                )
            
            if "year" in df.columns:
                display_columns.append("year")
                column_config["year"] = st.column_config.NumberColumn("Year", width="small")
            
            if "title" in df.columns:
                display_columns.append("title")
                column_config["title"] = st.column_config.TextColumn("Title", width="large")
            
            if "source" in df.columns:
                display_columns.append("source")
                column_config["source"] = st.column_config.TextColumn("Database", width="small")
            
            if "url" in df.columns:
                display_columns.append("url")
                column_config["url"] = st.column_config.LinkColumn("Link", width="small")
            
            # Filter display columns to only those that exist
            display_columns = [c for c in display_columns if c in df.columns]
            
            # Display enhanced dataframe
            st.dataframe(
                df[display_columns],
                width='stretch',
                column_config=column_config,
                height=400,
                hide_index=True
            )
            
            # Pagination controls
            if total_results > page_size:
                total_pages = math.ceil(total_results / page_size)
                st.caption(f"📄 Page {page} of {total_pages} ({total_results} total results)")
                
                # Quick page navigation
                nav_col1, nav_col2, nav_col3, nav_col4, nav_col5 = st.columns(5)
                with nav_col1:
                    if st.button("⏮️ First", disabled=page <= 1):
                        st.session_state['page'] = 1
                        st.rerun()
                with nav_col2:
                    if st.button("◀️ Previous", disabled=page <= 1):
                        st.session_state['page'] = page - 1
                        st.rerun()
                with nav_col4:
                    if st.button("▶️ Next", disabled=page >= total_pages):
                        st.session_state['page'] = page + 1
                        st.rerun()
                with nav_col5:
                    if st.button("⏭️ Last", disabled=page >= total_pages):
                        st.session_state['page'] = total_pages
                        st.rerun()
        else:
            st.warning("🔍 No results found matching your filters. Try adjusting your search criteria.")
            st.info("💡 **Suggestions:**\n- Expand your quality score range\n- Include more database sources\n- Broaden your year range\n- Check your text search terms")
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
            st.dataframe(dfe[[c for c in ["decision","reason","year","title","source","url"] if c in dfe.columns]], width='stretch')
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
