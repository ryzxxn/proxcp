import json
from typing import Any, List, Dict, Union

def to_toon(data: Any, indent: int = 0) -> str:
    """
    Converts a JSON-compatible object into TOON (Token-Oriented Object Notation).
    """
    spaces = "  " * indent
    
    if isinstance(data, dict):
        lines = []
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                if isinstance(value, list) and _is_uniform_list(value):
                    lines.append(f"{spaces}{key}{_format_toon_list_header(value)}:")
                    lines.append(_format_toon_list_rows(value, indent + 1))
                else:
                    lines.append(f"{spaces}{key}:")
                    lines.append(to_toon(value, indent + 1))
            else:
                lines.append(f"{spaces}{key}: {value}")
        return "\n".join([line for line in lines if line])

    elif isinstance(data, list):
        if _is_uniform_list(data):
            # If it's a top-level uniform list
            header = _format_toon_list_header(data)
            rows = _format_toon_list_rows(data, indent)
            return f"{header}:\n{rows}"
        else:
            lines = []
            for item in data:
                lines.append(f"{spaces}- {to_toon(item, indent + 1).strip()}")
            return "\n".join(lines)
            
    return str(data)

def _is_uniform_list(items: List[Any]) -> bool:
    """Checks if a list contains objects with the same keys."""
    if not items or not isinstance(items[0], dict):
        return False
    keys = set(items[0].keys())
    return all(isinstance(i, dict) and set(i.keys()) == keys for i in items)

def _format_toon_list_header(items: List[Dict[str, Any]]) -> str:
    count = len(items)
    if not items:
        return "[0]"
    keys = ",".join(items[0].keys())
    return f"[{count}]{{{keys}}}"

def _format_toon_list_rows(items: List[Dict[str, Any]], indent: int) -> str:
    spaces = "  " * indent
    lines = []
    for item in items:
        values = []
        for v in item.values():
            if v is None:
                values.append("")
            elif isinstance(v, bool):
                values.append(str(v).lower())
            else:
                values.append(str(v).replace(",", "\\,")) # Simple escaping
        lines.append(f"{spaces}{','.join(values)}")
    return "\n".join(lines)
