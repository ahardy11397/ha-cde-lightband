"""Google Web Toolkit Remote Procedure Call (GWT-RPC) serializer and parser.

Tailored for CDE Lightband / Daffron eBusiness (eBiz) client interface.
"""
from __future__ import annotations

import json
import re
from typing import Any

CDE_MODULE_BASE = "https://myaccount.clarksvillede.com/ebusiness/"
CDE_RPC_ENDPOINT = "https://myaccount.clarksvillede.com/ebusiness/ebiz"
CDE_POLICY_ID = "9B0246073475961F003BC947C4A4B6CF"
CDE_PERMUTATION = "64365524BBB2AFDF21B13502E153DBD9"
CDE_SERVICE_INTERFACE = "com.daffron.ebiz.client.EBizService"

GWT_STRING_TYPE = "java.lang.String/2004016611"
GWT_JSON_DATA_TYPE = "com.daffron.shared.shared.JsonData/1630149208"


def build_gwt_payload(
    service: str,
    method: str,
    param_types: list[str],
    param_values: list[str],
    module_base: str = CDE_MODULE_BASE,
    policy: str = CDE_POLICY_ID,
) -> str:
    """Build a GWT RPC version 7 payload string."""
    strings: list[str] = []

    def get_str_idx(s: str) -> int:
        if s not in strings:
            strings.append(s)
        return strings.index(s) + 1

    mb_idx = get_str_idx(module_base)
    pol_idx = get_str_idx(policy)
    svc_idx = get_str_idx(service)
    mth_idx = get_str_idx(method)

    payload_indices: list[int] = []
    # 1. Parameter type descriptors
    for pt in param_types:
        payload_indices.append(get_str_idx(pt))
    # 2. Parameter values
    for pv in param_values:
        payload_indices.append(get_str_idx(pv))

    str_table = "|".join(strings)
    param_count = len(param_types)
    header = f"7|0|{len(strings)}|{str_table}|"
    indices_str = "|".join(str(i) for i in payload_indices)
    if indices_str:
        body = f"{mb_idx}|{pol_idx}|{svc_idx}|{mth_idx}|{param_count}|{indices_str}|"
    else:
        body = f"{mb_idx}|{pol_idx}|{svc_idx}|{mth_idx}|0|"

    return header + body


def parse_gwt_response(raw_text: str) -> dict[str, Any]:
    """Parse GWT-RPC response string (e.g. //OK[...] or //EX[...])."""
    text = raw_text.strip()
    if text.startswith("//OK"):
        json_part = text[4:]
        try:
            parsed = json.loads(json_part)
            # Typical GWT RPC format: [flags, ..., [string_table], ...]
            string_table = []
            for item in parsed:
                if isinstance(item, list) and all(isinstance(x, str) for x in item):
                    string_table = item
                    break
            return {
                "status": "OK",
                "raw": raw_text,
                "parsed": parsed,
                "string_table": string_table,
            }
        except Exception:
            return {"status": "OK", "raw": raw_text, "string_table": []}

    elif text.startswith("//EX"):
        json_part = text[4:]
        try:
            parsed = json.loads(json_part)
            exception_name = ""
            for item in parsed:
                if isinstance(item, list):
                    for elem in item:
                        if isinstance(elem, str) and ("Exception" in elem or "Error" in elem):
                            exception_name = elem
                            break
            return {
                "status": "EX",
                "raw": raw_text,
                "parsed": parsed,
                "exception": exception_name or "UnknownException",
            }
        except Exception:
            return {"status": "EX", "raw": raw_text, "exception": "ParseException"}

    return {
        "status": "ERROR",
        "raw": raw_text,
        "error": raw_text,
    }
