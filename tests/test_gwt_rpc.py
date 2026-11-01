"""Unit tests for Daffron eBiz GWT-RPC serialization and response parsing."""
import pytest
from custom_components.cde_lightband.gwt_rpc import (
    build_gwt_payload,
    parse_gwt_response,
    CDE_MODULE_BASE,
    CDE_POLICY_ID,
)

def test_build_gwt_payload_structure():
    payload = build_gwt_payload(
        service="com.daffron.ebiz.client.EBizService",
        method="signIn",
        param_types=["java.lang.String/2004016611", "java.lang.String/2004016611", "java.lang.String/2004016611"],
        param_values=["testuser", "testpass", "[1920,1080]"]
    )
    assert payload.startswith("7|0|8|")
    assert CDE_MODULE_BASE in payload
    assert CDE_POLICY_ID in payload
    assert "com.daffron.ebiz.client.EBizService" in payload
    assert "signIn" in payload
    assert payload.endswith("|1|2|3|4|3|5|5|5|6|7|8|")

def test_build_gwt_payload_zero_params():
    payload = build_gwt_payload(
        service="com.daffron.ebiz.client.EBizService",
        method="getInitialData",
        param_types=[],
        param_values=[]
    )
    assert payload == f"7|0|4|{CDE_MODULE_BASE}|{CDE_POLICY_ID}|com.daffron.ebiz.client.EBizService|getInitialData|1|2|3|4|0|"

def test_parse_gwt_ok_response():
    resp = '//OK[0,2,1,["res1","res2"],0,7]'
    data = parse_gwt_response(resp)
    assert data["status"] == "OK"
    assert data["string_table"] == ["res1", "res2"]

def test_parse_gwt_ex_response():
    resp = '//EX[0,0,0,9,1,["com.daffron.shared.client.SignInException/3923402574"],0,7]'
    data = parse_gwt_response(resp)
    assert data["status"] == "EX"
    assert "SignInException" in data["exception"]

def test_parse_gwt_invalid_response():
    resp = 'The call failed on the server; see server log for details'
    data = parse_gwt_response(resp)
    assert data["status"] == "ERROR"
    assert "The call failed" in data["raw"]
