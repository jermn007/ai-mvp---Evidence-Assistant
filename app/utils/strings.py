def to_str(v): return v if isinstance(v, str) else ""
def strip_or_empty(v): return to_str(v).strip()
def norm_lower(v): return strip_or_empty(v).lower()