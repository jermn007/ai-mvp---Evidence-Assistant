# app/press_hits.py
from __future__ import annotations
from typing import List, Dict, Optional
import os
import re
import time
import httpx

from app.press_contract import PressStrategy, StrategyLine

EUTILS_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"

def _env_ncbi():
    return {
        "api_key": os.getenv("NCBI_API_KEY") or None,
        "tool": os.getenv("NCBI_TOOL", "evidence-assistant"),
        "email": os.getenv("NCBI_EMAIL") or os.getenv("CROSSREF_MAILTO") or "na@example.org",
    }

def _rate_delay(api_key: Optional[str]) -> float:
    # NCBI guidance: ~3 req/s with key, ~1 req/s without
    return 0.11 if api_key else 0.34

def _expand_lines_to_queries(lines: List[StrategyLine]) -> Dict[int, str]:
    """
    For each line number, build a PubMed query string:
      - Non-Combine/Non-Limits: use the clause as-is.
      - Combine: replace numbers with '(<line text>)'.
      - Limits: apply to the last Combine (or last line) if present; else return limits alone.
    """
    text_by_n: Dict[int, str] = {l.n: l.text for l in lines}
    query_by_n: Dict[int, str] = {}
    last_combine_n: Optional[int] = None

    # First pass: simple lines
    for l in lines:
        if l.type not in {"Combine", "Limits"}:
            query_by_n[l.n] = l.text

    # Second: Combine
    for l in lines:
        if l.type == "Combine":
            def repl(m):
                k = int(m.group(1))
                return f"({query_by_n.get(k) or text_by_n.get(k,'')})"
            expr = re.sub(r"\b(\d+)\b", repl, l.text)
            query_by_n[l.n] = expr
            last_combine_n = l.n

    # Third: Limits
    for l in lines:
        if l.type == "Limits":
            base = query_by_n.get(last_combine_n) or query_by_n.get(l.n - 1) or ""
            query_by_n[l.n] = f"({base}) AND ({l.text})" if base else l.text

    return query_by_n

async def _pubmed_count(term: str, api_key: Optional[str], tool: str, email: str) -> int:
    params = {
        "db": "pubmed",
        "retmode": "json",
        "rettype": "count",
        "term": term,
        "tool": tool,
        "email": email,
    }
    if api_key:
        params["api_key"] = api_key
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(EUTILS_ESEARCH, params=params)
        r.raise_for_status()
        data = r.json()
        return int(data.get("esearchresult", {}).get("count", "0"))

async def fill_hits_for_pubmed(strategy: PressStrategy) -> PressStrategy:
    """
    Returns a copy of the given strategy with `hits` populated for each line.
    Only applies when interface == PubMed (MEDLINE).
    """
    if (strategy.interface or "").lower() != "pubmed":
        return strategy

    env = _env_ncbi()
    delay = _rate_delay(env["api_key"])
    qmap = _expand_lines_to_queries(strategy.lines)

    # copy lines and populate hits
    new_lines: List[StrategyLine] = []
    for l in strategy.lines:
        q = qmap.get(l.n, l.text)
        try:
            count = await _pubmed_count(q, env["api_key"], env["tool"], env["email"])
        except Exception:
            count = None
        new_lines.append(StrategyLine(n=l.n, type=l.type, text=l.text, hits=count))
        # basic pacing
        await _async_sleep(delay)

    return PressStrategy(database=strategy.database, interface=strategy.interface, lines=new_lines)

async def _async_sleep(seconds: float):
    # tiny awaitable sleep (httpx is async, so use asyncio.sleep)
    import asyncio
    await asyncio.sleep(max(0.0, seconds))
