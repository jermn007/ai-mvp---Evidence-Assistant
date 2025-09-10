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
    Uses ESearch + ESummary + EFetch for complete article metadata including abstracts.
    Honors NCBI API etiquette if NCBI_API_KEY/tool/email provided.
    """
    esearch = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    esummary = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
    efetch = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    
    base_params = {
        "db": "pubmed",
        "retmode": "json",
        "tool": os.getenv("NCBI_TOOL", "evidence-assistant"),
        "email": os.getenv("NCBI_EMAIL") or os.getenv("CROSSREF_MAILTO"),
    }
    if os.getenv("NCBI_API_KEY"):
        base_params["api_key"] = os.getenv("NCBI_API_KEY")

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, headers=DEFAULT_HEADERS) as client:
        # Step 1: Search for article IDs
        try:
            p = dict(base_params)
            p.update({"term": term, "retmax": max_n})
            r = await _get_json(client, esearch, params=p)
            ids = r.get("esearchresult", {}).get("idlist", []) or []
            if not ids:
                return []
        except Exception as e:
            logger.warning(f"PubMed ESearch error: {e}")
            return []

        # Step 2: Get summary data (title, year, authors, DOI)
        try:
            p2 = dict(base_params)
            p2.update({"id": ",".join(ids)})
            summary_data = await _get_json(client, esummary, params=p2)
        except Exception as e:
            logger.warning(f"PubMed ESummary error: {e}")
            return []
            
        # Step 3: Get abstracts via EFetch (optional - don't fail if this doesn't work)
        abstracts = {}
        try:
            logger.info(f"PubMed: Attempting EFetch for {len(ids)} PMIDs")
            p3 = {
                "db": "pubmed",
                "rettype": "abstract",
                "retmode": "xml", 
                "tool": os.getenv("NCBI_TOOL", "evidence-assistant"),
                "email": os.getenv("NCBI_EMAIL") or os.getenv("CROSSREF_MAILTO"),
                "id": ",".join(ids)
            }
            if os.getenv("NCBI_API_KEY"):
                p3["api_key"] = os.getenv("NCBI_API_KEY")
                
            abstract_response = await _get(client, efetch, params=p3)
            abstract_text = abstract_response.text
            logger.info(f"PubMed: EFetch returned {len(abstract_text)} characters")
            
            # Parse abstracts from XML response
            if abstract_text:
                root = ET.fromstring(abstract_text)
                for article in root.findall(".//PubmedArticle"):
                    pmid_elem = article.find(".//PMID")
                    abstract_elem = article.find(".//AbstractText")
                    if pmid_elem is not None and abstract_elem is not None:
                        pmid = pmid_elem.text
                        abstract = abstract_elem.text or ""
                        abstracts[pmid] = abstract.strip()
        except Exception as e:
            logger.warning(f"PubMed EFetch failed (non-fatal): {e}")
            # Continue without abstracts

    # Parse abstracts from XML response
    abstracts = {}
    try:
        if abstract_text:
            root = ET.fromstring(abstract_text)
            for article in root.findall(".//PubmedArticle"):
                pmid_elem = article.find(".//PMID")
                abstract_elem = article.find(".//AbstractText")
                if pmid_elem is not None and abstract_elem is not None:
                    pmid = pmid_elem.text
                    abstract = abstract_elem.text or ""
                    abstracts[pmid] = abstract.strip()
    except Exception as e:
        logger.warning(f"PubMed abstract parsing failed: {e}")

    result = summary_data.get("result", {}) if isinstance(summary_data, dict) else {}
    out: List[Dict] = []
    
    for pmid in ids:
        item = result.get(pmid) or {}
        title = (item.get("title") or "").strip().rstrip(".")
        
        # Skip records with no title
        if not title:
            continue
            
        pubdate = item.get("pubdate") or ""
        year = int(pubdate[:4]) if (pubdate and pubdate[:4].isdigit()) else None
        
        # Extract DOI
        doi = None
        eloc = item.get("elocationid") or ""
        if isinstance(eloc, str) and eloc.lower().startswith("doi:"):
            doi = eloc.split(":", 1)[1].strip()
        
        # Enhanced author extraction with multiple fallback strategies
        authors = []
        # Strategy 1: ESummary authors field
        if "authors" in item and isinstance(item["authors"], list):
            for author in item["authors"]:
                if isinstance(author, dict):
                    name = author.get("name") or author.get("authname") or ""
                    if name:
                        authors.append(name)
        
        # Strategy 2: ESummary authorlist field
        elif "authorlist" in item and isinstance(item["authorlist"], list):
            for author in item["authorlist"]:
                if isinstance(author, dict):
                    name = author.get("name") or author.get("authname") or ""
                    if name:
                        authors.append(name)
        
        # Strategy 3: Direct authname field (some API versions)
        elif "authname" in item and isinstance(item["authname"], str):
            # Split comma-separated author string
            author_names = [a.strip() for a in item["authname"].split(",") if a.strip()]
            authors.extend(author_names)
            
        authors_str = ", ".join(authors) if authors else None
        
        # Get abstract from parsed XML
        abstract = abstracts.get(pmid, "").strip() or None
        
        out.append({
            "record_id": f"pmid:{pmid}",
            "title": title,
            "abstract": abstract,
            "authors": authors_str,
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
        title = " ".join(it.get("title") or []).strip()
        
        # Skip records with no title
        if not title:
            continue
            
        year = None
        try:
            year = it.get("issued", {}).get("date-parts", [[None]])[0][0]
            if isinstance(year, float):
                year = int(year)
        except Exception:
            pass
            
        doi = it.get("DOI")
        url = it.get("URL")
        
        # Enhanced author extraction from Crossref response
        authors = []
        if "author" in it and isinstance(it["author"], list):
            for author in it["author"]:
                if isinstance(author, dict):
                    given = author.get("given", "").strip()
                    family = author.get("family", "").strip()
                    suffix = author.get("suffix", "").strip()
                    
                    # Build full name with proper formatting
                    name_parts = []
                    if given:
                        name_parts.append(given)
                    if family:
                        name_parts.append(family)
                    if suffix:
                        name_parts.append(suffix)
                    
                    if name_parts:
                        full_name = " ".join(name_parts)
                        authors.append(full_name)
                    elif "name" in author:
                        # Fallback to name field if available
                        name = author.get("name", "").strip()
                        if name:
                            authors.append(name)
        
        # Additional fallback for author extraction
        elif "editor" in it and isinstance(it["editor"], list):
            # Sometimes authors are listed as editors
            for editor in it["editor"]:
                if isinstance(editor, dict):
                    given = editor.get("given", "").strip()
                    family = editor.get("family", "").strip()
                    if given and family:
                        authors.append(f"{given} {family}")
                    elif family:
                        authors.append(family)
                        
        authors_str = ", ".join(authors) if authors else None
        
        out.append({
            "record_id": f"doi:{doi}" if doi else f"cr:{url}",
            "title": title,
            "abstract": it.get("abstract"),
            "authors": authors_str,
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

        # Extract authors from arXiv XML
        authors = []
        for author in entry.findall("atom:author", ns):
            name = author.findtext("atom:name", namespaces=ns)
            if name:
                authors.append(name.strip())
        authors_str = ", ".join(authors) if authors else None

        out.append({
            "record_id": f"arxiv:{arxiv_id}",
            "title": title,
            "abstract": summary,
            "authors": authors_str,
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
        
        # Extract authors from ERIC response
        authors = []
        author_field = (
            d.get("authors") or d.get("Authors") or 
            d.get("author") or d.get("Author") or
            d.get("AuthorContact") or []
        )
        if isinstance(author_field, list):
            for author in author_field:
                if isinstance(author, str):
                    authors.append(author.strip())
                elif isinstance(author, dict) and "name" in author:
                    authors.append(author["name"].strip())
        elif isinstance(author_field, str):
            # Handle comma-separated authors
            authors = [a.strip() for a in author_field.split(",") if a.strip()]
        authors_str = ", ".join(authors) if authors else None
        
        if not ext or not title:
            continue
        out.append({
            "record_id": f"eric:{ext}",
            "title": title,
            "abstract": abstract,
            "authors": authors_str,
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
    fields = "title,year,abstract,externalIds,url,authors"
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
        
        # Extract authors from Semantic Scholar response
        authors = []
        if "authors" in p and isinstance(p["authors"], list):
            for author in p["authors"]:
                if isinstance(author, dict) and "name" in author:
                    authors.append(author["name"])
        authors_str = ", ".join(authors) if authors else None

        rid = f"doi:{doi}" if doi else (f"s2:{s2id}" if s2id else "s2:" + hashlib.md5(title.encode("utf-8")).hexdigest())
        out.append({
            "record_id": rid,
            "title": title,
            "abstract": abstract,
            "authors": authors_str,
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
    results = data.get("organic_results") or []
    
    if not results:
        # Log what we got back to help debug
        logger.warning(f"Scholar(SerpAPI): No organic_results in response. Keys: {list(data.keys())}")
        error = data.get("error")
        if error:
            logger.error(f"Scholar(SerpAPI): API error: {error}")
        return []
    
    for r in results:
        title = (r.get("title") or "").strip()
        link = r.get("link")
        snippet = r.get("snippet") or r.get("summary") or ""
        
        # Skip records with insufficient data
        if not title or not link:
            continue
        
        # Enhanced year extraction
        year = None
        pub_info = r.get("publication_info", {})
        
        # Try multiple sources for year
        year_sources = [
            pub_info.get("summary", ""),
            snippet,
            title,
            str(pub_info)
        ]
        
        for source in year_sources:
            if year:
                break
            m = re.search(r"\b(19|20)\d{2}\b", str(source))
            if m:
                try:
                    year = int(m.group(0))
                    break
                except Exception:
                    continue
        
        # Enhanced author extraction from Google Scholar response
        authors_str = None
        
        # Strategy 1: Direct authors field
        if isinstance(pub_info, dict) and "authors" in pub_info:
            authors_field = pub_info["authors"]
            if isinstance(authors_field, list):
                # If it's a list of author objects
                authors_names = []
                for author in authors_field:
                    if isinstance(author, dict) and "name" in author:
                        authors_names.append(author["name"])
                    elif isinstance(author, str):
                        authors_names.append(author)
                if authors_names:
                    authors_str = ", ".join(authors_names)
            elif isinstance(authors_field, str) and authors_field.strip():
                authors_str = authors_field.strip()
        
        # Strategy 2: Parse from publication summary
        if not authors_str and isinstance(pub_info, dict):
            summary = pub_info.get("summary", "")
            if isinstance(summary, str) and " - " in summary:
                # Format: "Author1, Author2, Author3 - Journal Name, Year"
                parts = summary.split(" - ")
                if len(parts) >= 2:
                    potential_authors = parts[0].strip()
                    # Filter out non-author content
                    exclude_terms = [
                        "cited by", "related", "versions", "[pdf]", "[html]", 
                        "abstract", "full text", "download", "view", "google scholar"
                    ]
                    if potential_authors and not any(term in potential_authors.lower() for term in exclude_terms):
                        # Additional validation - should contain typical name patterns
                        if re.search(r"[A-Z][a-z]+", potential_authors):
                            authors_str = potential_authors
        
        # Strategy 3: Extract from snippet if it contains author-like patterns
        if not authors_str and snippet:
            # Look for patterns like "by Author Name" or "Author Name et al"
            author_patterns = [
                r"[Bb]y ([A-Z][a-z]+ [A-Z][a-z]+(?:, [A-Z][a-z]+ [A-Z][a-z]+)*)",
                r"([A-Z][a-z]+ [A-Z][a-z]+(?:, [A-Z][a-z]+ [A-Z][a-z]+)*) et al",
            ]
            
            for pattern in author_patterns:
                match = re.search(pattern, snippet)
                if match:
                    authors_str = match.group(1)
                    break
        
        rid = "scholar:" + hashlib.md5(link.encode("utf-8")).hexdigest()
        out.append({
            "record_id": rid,
            "title": title,
            "abstract": snippet,
            "authors": authors_str,
            "year": year,
            "doi": None,
            "url": link,
            "source": "GoogleScholar",
        })
    return out
