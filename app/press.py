# app/press.py
from __future__ import annotations
from typing import Dict, List, Tuple
from pydantic import BaseModel
import re, yaml, os

from app.press_contract import LICO, DatabaseSpec, StrategyLine, PressStrategy, PressChecklist, PressPlanResponse

DEFAULT_DBs = [DatabaseSpec(name="MEDLINE", interface="PubMed")]

def _load_terms(path: str = "config/press_terms.yaml") -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def _dedupe(seq: List[str]) -> List[str]:
    seen, out = set(), []
    for s in seq:
        k = (s or "").strip()
        if k and k not in seen:
            seen.add(k); out.append(k)
    return out

def _extract_user_terms(text: str) -> List[str]:
    """Extract search terms from user input text."""
    if not text or not text.strip():
        return []

    # Clean up and split the text into potential search terms
    # Handle common separators and clean up terms
    terms = []

    # Split by common separators: comma, semicolon, and, or, etc.
    import re
    raw_terms = re.split(r'[,;]\s*|\s+and\s+|\s+or\s+|\s*&\s*|\s*\|\s*', text.lower())

    for term in raw_terms:
        # Clean up each term
        cleaned = re.sub(r'[^\w\s-]', '', term.strip())
        if cleaned and len(cleaned) > 2:  # Skip very short terms
            terms.append(cleaned)

    # Also add the full phrase if it's meaningful
    full_text = re.sub(r'[^\w\s-]', '', text.strip().lower())
    if full_text and len(full_text) > 3 and full_text not in terms:
        terms.append(full_text)

    return _dedupe(terms)

def _merge_terms_with_yaml(user_terms: List[str], yaml_component_terms: Dict) -> Dict:
    """Merge user extracted terms with existing YAML terms."""
    if not yaml_component_terms:
        yaml_component_terms = {}

    # Get existing terms from YAML
    existing_mesh = yaml_component_terms.get("mesh", [])
    existing_text = yaml_component_terms.get("text", [])

    # Combine user terms with existing text terms (user terms go to text, not mesh)
    combined_text = existing_text + user_terms

    return {
        "mesh": _dedupe(existing_mesh),
        "text": _dedupe(combined_text)
    }

def _pubmed_clause(mesh: List[str], text: List[str]) -> Tuple[str, List[str], List[str]]:
    mesh_parts = [f"\"{m}\"[Mesh]" for m in mesh]
    text_parts = []
    for t in text:
        if " " in t or t.endswith("*"):
            text_parts.append(f"{t}[tiab]" if not t.endswith("*") else f"{t}[tiab]")
        else:
            text_parts.append(f"{t}*[tiab]")
    return " OR ".join(mesh_parts + text_parts), mesh_parts, text_parts

def _limits_to_pubmed(limits: Dict) -> str:
    parts = []
    if limits.get("year_min"):
        parts.append(f"{int(limits['year_min'])}:3000[dp]")
    if limits.get("language"):
        parts.append(f"{limits['language']}[la]")
    if limits.get("humans"):
        parts.append("Humans[Mesh]")
    return " AND ".join(parts) if parts else ""

def _facet_block_pubmed(terms: Dict, facet: str) -> Tuple[str, List[str], List[str]]:
    mesh = _dedupe(terms.get(facet, {}).get("mesh", []))
    text = _dedupe(terms.get(facet, {}).get("text", []))
    clause, mesh_parts, text_parts = _pubmed_clause(mesh, text)
    return clause, mesh_parts, text_parts

def _press_self_check_pubmed(lines: List[StrategyLine], mesh_present: bool, text_present: bool, limits_present: bool) -> PressChecklist:
    def grade(ok: bool) -> str: return "pass" if ok else "suggest"
    has_lines = bool(lines and all(isinstance(l.n, int) for l in lines))
    has_bool = any(re.search(r"\b(AND|OR|NOT|NEAR|adj\d+)\b", l.text, re.I) for l in lines if l.type in {"Combine","Learner","Intervention","Context","Outcome","MeSH","Text"})
    return PressChecklist(
        translation=grade(True),  # we always map LICO → facets here
        subject_headings=grade(mesh_present),
        text_words=grade(text_present),
        spelling_syntax_lines=grade(has_lines and has_bool),
        limits_filters=grade(limits_present),
        notes="Auto-checks are heuristic; librarian review recommended."
    )

def plan_press_from_lico(lico: LICO, databases: List[DatabaseSpec] | None = None, terms_path: str = "config/press_terms.yaml") -> PressPlanResponse:
    terms = _load_terms(terms_path)
    dbs = databases or DEFAULT_DBs

    strategies: Dict[str, PressStrategy] = {}
    checklist: Dict[str, PressChecklist] = {}

    # Build once for PubMed-like syntax
    l_clause, l_mesh, l_text = _facet_block_pubmed(terms, "learner")
    i_clause, i_mesh, i_text = _facet_block_pubmed(terms, "intervention")
    c_clause, c_mesh, c_text = _facet_block_pubmed(terms, "context")
    o_clause, o_mesh, o_text = _facet_block_pubmed(terms, "outcome")
    limits_clause = _limits_to_pubmed(terms.get("limits", {}))

    mesh_present = any([l_mesh, i_mesh, c_mesh, o_mesh])
    text_present = any([l_text, i_text, c_text, o_text])
    limits_present = bool(limits_clause)

    # Numbered lines
    lines: List[StrategyLine] = []
    n = 1
    if l_mesh or l_text:
        lines.append(StrategyLine(n=n, type="Learner", text=f"({l_clause})")); n += 1
    if i_mesh or i_text:
        lines.append(StrategyLine(n=n, type="Intervention", text=f"({i_clause})")); n += 1
    if c_mesh or c_text:
        lines.append(StrategyLine(n=n, type="Context", text=f"({c_clause})")); n += 1
    if o_mesh or o_text:
        lines.append(StrategyLine(n=n, type="Outcome", text=f"({o_clause})")); n += 1

    # Combine: (Learner OR ?) & (Intervention ...) & Context & Outcome
    # More conservative: AND across facets; within facet already has ORs.
    if lines:
        # indices we added
        idxs = list(range(1, n))
        # Build "1 AND 2 AND 3 AND 4" but only for existing facets
        combine_expr = " AND ".join(str(idx) for idx in idxs)
        lines.append(StrategyLine(n=n, type="Combine", text=combine_expr)); n += 1

    if limits_clause:
        lines.append(StrategyLine(n=n, type="Limits", text=limits_clause)); n += 1

    for db in dbs:
        strategies[db.name] = PressStrategy(database=db.name, interface=db.interface, lines=lines)
        checklist[db.name] = _press_self_check_pubmed(lines, mesh_present, text_present, limits_present)

    return PressPlanResponse(
        question_lico=lico,
        strategies=strategies,
        checklist=checklist
    )
