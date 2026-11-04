"""
Utility to convert Pydantic schemas into Google Gemini-compatible responseSchema.
Recursively inlines all $defs and $ref pointers, removes unsupported JSON Schema keywords
(title, default, additionalProperties), and normalizes types to Gemini-supported format.
"""

from typing import Any, Dict, Type
from pydantic import BaseModel


def to_gemini_schema(model_class: Type[BaseModel]) -> Dict[str, Any]:
    """Converts a Pydantic model class to an inlined, Gemini-compliant responseSchema."""
    raw_schema = model_class.model_json_schema()
    defs = raw_schema.get("$defs", {})

    def resolve_node(node: Any) -> Any:
        if isinstance(node, dict):
            # Resolve $ref pointer
            if "$ref" in node:
                ref_key = node["$ref"].split("/")[-1]
                target_def = defs.get(ref_key, {})
                return resolve_node(target_def)

            clean_dict: Dict[str, Any] = {}
            for k, v in node.items():
                # Strip unsupported metadata fields
                if k in ["$defs", "$ref", "title", "default", "additionalProperties"]:
                    continue

                # Normalize type names to uppercase
                if k == "type" and isinstance(v, str):
                    clean_dict["type"] = v.upper()
                else:
                    clean_dict[k] = resolve_node(v)

            return clean_dict

        elif isinstance(node, list):
            return [resolve_node(item) for item in node]

        return node

    return resolve_node(raw_schema)

