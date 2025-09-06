# app/sources.py
from __future__ import annotations
from typing import List, Dict, Optional, Any
import hashlib
import logging
import re
import os
import xml.etree.ElementTree as ET
import httpx

# ---- logging ----
logger = logging.getLogger("ai_mvp.sources")
if not logger.handlers:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

# ---- retry/backoff (tenacity) ----
try:
    from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
    _retry = retry(
        stop=stop_after_attempt(int(os.getenv("HTTP_RETRY_ATTEMPTS", "3"))),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
        retry=retry_if_exception_type(httpx.HTTPError),
        reraise=True,
    )
except Exception:
    # graceful fallback if tenacity isn't installed (no-op decorator)
    def _retry(fn):  # type: ignore
        return fn

# ---- shared HTTP defaults ----
DEFAULT_TIMEOUT = httpx.Timeout(
    connect=float(os.getenv("HTTP_TIMEOUT_CONNECT", "5")),
    read=float(os.getenv("HTTP_TIMEOUT_READ", "15")),
    write=float(os.getenv("HTTP_TIMEOUT_WRITE", "15")),
    pool=float(os.getenv("HTTP_TIMEOUT_POOL", "5")),
)

DEFAULT_HEADERS = {
    "User-Agent": os.getenv(
        "HTTP_USER_AGENT",
        "EvidenceAssistant/0.1 (+https://example.org; contact=ops@example.org)"
    )
}

def _merge_headers(extra: Dict[str, str] | None) -> Dict[str, str]:
    if not extra:
        return dict(DEFAULT_HEADERS)
    merged = dict(DEFAULT_HEADERS)
    merged.update(extra)
    return merged

@_retry
async def _get(client: httpx.AsyncClient, url: str, *, params: Dict[str, Any] | None = None,
               headers: Dict[str, str] | None = None) -> httpx.Response:
    resp = await client.get(url, params=params, headers=headers, follow_redirects=True)
    resp.raise_for_status()
    return resp

@_retry
async def _get_json(client: httpx.AsyncClient, url: str, *, params: Dict[str, Any] | None = None,
                    headers: Dict[str, str] | None = None) -> Any:
    resp = await client.get(url, params=params, headers=headers, follow_redirects=True)
    resp.raise_for_status()
    return resp.json()

# --- PubMed (E-utilities) ---
async def pubmed_search_async(term: str, max_n: int = 25) -> List[Dict]:
    """
    Uses ESearch + ESummary (abstract optional via EFetch; skipped for now).
    Honors NCBI API etiquette if NCBI_API_KEY/tool/email provided.
    """
    esearch = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    esummary = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
    base_params = {
        "db": "pubmed",
        "retmode": "json",
        "tool": os.getenv("NCBI_TOOL", "evidence-assistant"),
        "email": os.getenv("NCBI_EMAIL") or os.getenv("CROSSREF_MAILTO"),
    }
    if os.getenv("NCBI_API_KEY"):
        base_params["api_key"] = os.getenv("NCBI_API_KEY")

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, headers=DEFAULT_HEADERS) as client:
        try:
            p = dict(base_params)
            p.update({"term": term, "retmax": max_n})
            r = await _get_json(client, esearch, params=p)
            ids = r.get("esearchresult", {}).get("idlist", []) or []
            if not ids:
                return []

            p2 = dict(base_params)
            p2.update({"id": ",".join(ids)})
            data = await _get_json(client, esummary, params=p2)
        except Exception as e:
            logger.info("PubMed: returning [] (%s)", e)
            return []

    result = data.get("result", {}) if isinstance(data, dict) else {}
    out: List[Dict] = []
    for pmid in ids:
        item = result.get(pmid) or {}
        title = (item.get("title") or "").strip().rstrip(".")
        pubdate = item.get("pubdate") or ""
        year = int(pubdate[:4]) if (pubdate and pubdate[:4].isdigit()) else None
        doi = None
        eloc = item.get("elocationid") or ""
        if isinstance(eloc, str) and eloc.lower().startswith("doi:"):
            doi = eloc.split(":", 1)[1].strip()
        out.append({
            "record_id": f"pmid:{pmid}",
            "title": title,
            "abstract": None,
            "year": year,
            "doi": doi,
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            "source": "PubMed",
        })
    return out

# --- Crossref ---
async def crossref_search_async(term: str, max_n: int = 25, mailto: Optional[str] = None) -> List[Dict]:
    params = {"query": term, "rows": max_n}
    if mailto:
        params["mailto"] = mailto

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, headers=DEFAULT_HEADERS) as client:
        try:
            r = await _get_json(client, "https://api.crossref.org/works", params=params)
            items = r.get("message", {}).get("items", []) or []
        except Exception as e:
            logger.info("Crossref: returning [] (%s)", e)
            return []

    out: List[Dict] = []
    for it in items:
        title = " ".join(it.get("title") or [])
        year = None
        try:
            year = it.get("issued", {}).get("date-parts", [[None]])[0][0]
            if isinstance(year, float):
                year = int(year)
        except Exception:
            pass
        doi = it.get("DOI")
        url = it.get("URL")
        out.append({
            "record_id": f"doi:{doi}" if doi else f"cr:{url}",
            "title": title,
            "abstract": it.get("abstract"),
            "year": year,
            "doi": doi,
            "url": url,
            "source": "Crossref",
        })
    return out

# --- arXiv ---
async def arxiv_search_async(query: str, max_n: int = 25) -> List[Dict[str, Any]]:
    """
    Query arXiv Atom API and normalize to our RecordModel shape.
    Docs: https://export.arxiv.org/api_help/ (use HTTPS to avoid 301 redirects)
    """
    url = "https://export.arxiv.org/api/query"
    params = {
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": max_n,
        "sortBy": "relevance",
        "sortOrder": "descending",
    }
    out: List[Dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, headers=DEFAULT_HEADERS) as client:
        try:
            resp = await _get(client, url, params=params)
            text = resp.text
        except Exception as e:
            logger.info("arXiv: returning [] (%s)", e)
            return []

    try:
        root = ET.fromstring(text)
    except Exception as e:
        logger.info("arXiv: XML parse error -> [] (%s)", e)
        return []

    ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    for entry in root.findall("atom:entry", ns):
        title = (entry.findtext("atom:title", default="", namespaces=ns) or "").strip()
        summary = (entry.findtext("atom:summary", default="", namespaces=ns) or "").strip()
        id_url = entry.findtext("atom:id", default="", namespaces=ns) or ""
        published = entry.findtext("atom:published", default="", namespaces=ns) or ""
        year = int(published[:4]) if (published and len(published) >= 4 and published[:4].isdigit()) else None

        doi = entry.findtext("arxiv:doi", default=None, namespaces=ns)
        url_alt = None
        for link in entry.findall("atom:link", ns):
            if link.attrib.get("rel") == "alternate":
                url_alt = link.attrib.get("href")
                break
        url_final = url_alt or id_url
        arxiv_id = id_url.rsplit("/", 1)[-1] if id_url else None
        if not arxiv_id or not title:
            continue

        out.append({
            "record_id": f"arxiv:{arxiv_id}",
            "title": title,
            "abstract": summary,
            "year": year,
            "doi": doi,
            "url": url_final,
            "source": "arXiv",
        })
    return out

# --- ERIC ---
async def eric_search_async(query: str, max_n: int = 25, api_base: str | None = None) -> List[Dict[str, Any]]:
    """
    Try ERIC JSON API; normalize results. This is tolerant to schema variants.
    You can override the base via ERIC_API_BASE env if your gateway differs.
    """
    base = api_base or os.getenv("ERIC_API_BASE", "https://api.ies.ed.gov/eric/")
    params = {"search": query, "format": "json", "rows": max_n}

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, headers=DEFAULT_HEADERS) as client:
        try:
            data = await _get_json(client, base, params=params)
        except Exception as e:
            logger.info("ERIC: returning [] (%s)", e)
            return []

    docs = []
    if isinstance(data, dict):
        docs = (
            data.get("response", {}).get("docs")
            or data.get("docs")
            or data.get("records")
            or []
        )
    if not isinstance(docs, list):
        return []

    out: List[Dict[str, Any]] = []
    for d in docs:
        ext = (
            d.get("ericNumber")
            or d.get("ERICNumber")
            or d.get("id")
            or d.get("AccessionNumber")
            or ""
        )
        title = d.get("title") or d.get("Title") or d.get("TitleProper") or ""
        abstract = d.get("abstract") or d.get("Abstract") or d.get("description")
        year = d.get("publicationdateyear") or d.get("publicationYear") or d.get("Year")
        try:
            year = int(year) if year else None
        except Exception:
            year = None
        doi = d.get("doi") or d.get("DOI")
        url = (
            d.get("fullText")
            or d.get("url")
            or d.get("URL")
            or (f"https://eric.ed.gov/?id={ext}" if ext else None)
        )
        if not ext or not title:
            continue
        out.append({
            "record_id": f"eric:{ext}",
            "title": title,
            "abstract": abstract,
            "year": year,
            "doi": doi,
            "url": url,
            "source": "ERIC",
        })
    return out

# --- Semantic Scholar (S2) ---
async def s2_search_async(query: str, max_n: int = 25) -> List[Dict[str, Any]]:
    """
    Semantic Scholar Graph API search.
    Uses x-api-key when S2_API_KEY is present.
    If S2_REQUIRE_KEY=true and key missing -> skip (return []).
    """
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    fields = "title,year,abstract,externalIds,url"
    params = {"query": query, "limit": max_n, "fields": fields}
    headers = {}
    api_key = os.getenv("S2_API_KEY")
    require = (os.getenv("S2_REQUIRE_KEY", "false").lower() == "true")

    if api_key:
        headers["x-api-key"] = api_key
        logger.info("S2: using x-api-key header")
    elif require:
        logger.info("S2: S2_REQUIRE_KEY=true but no key present; skipping")
        return []
    else:
        logger.info("S2: no key present; attempting anonymous (may be rate-limited)")

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, headers=_merge_headers(headers)) as client:
        try:
            data = await _get_json(client, url, params=params)
        except Exception as e:
            logger.info("S2: returning [] (%s)", e)
            return []

    out: List[Dict[str, Any]] = []
    for p in (data.get("data") or []):
        title = (p.get("title") or "").strip()
        if not title:
            continue
        ext = p.get("externalIds") or {}
        doi = ext.get("DOI") or None
        s2id = p.get("paperId") or None
        url_final = p.get("url") or (f"https://doi.org/{doi}" if doi else None)
        year = p.get("year") if isinstance(p.get("year"), int) else None
        abstract = p.get("abstract")

        rid = f"doi:{doi}" if doi else (f"s2:{s2id}" if s2id else "s2:" + hashlib.md5(title.encode("utf-8")).hexdigest())
        out.append({
            "record_id": rid,
            "title": title,
            "abstract": abstract,
            "year": year,
            "doi": doi,
            "url": url_final,
            "source": "SemanticScholar",
        })
    return out

# --- Google Scholar via SerpAPI ---
async def scholar_serpapi_async(query: str, max_n: int = 25, year_min: int | None = None) -> List[Dict[str, Any]]:
    api_key = os.getenv("SERPAPI_KEY")
    if not api_key:
        logger.info("Scholar: no SERPAPI_KEY set; skipping")
        return []

    url = "https://serpapi.com/search.json"
    params = {"engine": "google_scholar", "q": query, "api_key": api_key, "num": max_n}
    if year_min:
        params["as_ylo"] = year_min

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, headers=DEFAULT_HEADERS) as client:
        try:
            data = await _get_json(client, url, params=params)
        except Exception as e:
            logger.info("Scholar(SerpAPI): returning [] (%s)", e)
            return []

    out: List[Dict[str, Any]] = []
    for r in (data.get("organic_results") or []):
        title = (r.get("title") or "").strip()
        link = r.get("link")
        snippet = r.get("snippet") or r.get("summary") or ""
        year = None
        text_for_year = " ".join([str(r.get("publication_info", {}).get("summary") or ""), snippet])
        m = re.search(r"\b(19|20)\d{2}\b", text_for_year)
        if m:
            try:
                year = int(m.group(0))
            except Exception:
                year = None

        if not title or not link:
            continue
        rid = "scholar:" + hashlib.md5(link.encode("utf-8")).hexdigest()
        out.append({
            "record_id": rid,
            "title": title,
            "abstract": snippet,
            "year": year,
            "doi": None,
            "url": link,
            "source": "GoogleScholar",
        })
    return out
