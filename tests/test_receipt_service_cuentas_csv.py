"""Unit tests for receipt_service.cuentas_to_pipe_csv (pure sync function)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import services.receipt_service
from services.receipt_service import cuentas_to_pipe_csv


# ---------------------------------------------------------------------------
# Empty / None input
# ---------------------------------------------------------------------------

def test_empty_list_returns_minimal_header():
    result = cuentas_to_pipe_csv([])
    assert result == "numero|nombre\n"


def test_none_input_treated_as_empty():
    result = cuentas_to_pipe_csv(None)
    assert result == "numero|nombre\n"


# ---------------------------------------------------------------------------
# Filtering by 'numero'
# ---------------------------------------------------------------------------

def test_filters_out_accounts_starting_with_3():
    rows = [
        {"numero": "3001", "nombre": "Patrimonio"},
        {"numero": "1001", "nombre": "Caja"},
    ]
    result = cuentas_to_pipe_csv(rows)
    assert "Patrimonio" not in result
    assert "Caja" in result


def test_filters_out_accounts_starting_with_4():
    rows = [
        {"numero": "4001", "nombre": "Ingresos"},
        {"numero": "5001", "nombre": "Gastos"},
    ]
    result = cuentas_to_pipe_csv(rows)
    assert "Ingresos" not in result
    assert "Gastos" in result


def test_filters_out_accounts_starting_with_3_or_4_mixed():
    rows = [
        {"numero": "1001", "nombre": "Caja"},
        {"numero": "3005", "nombre": "Capital"},
        {"numero": "4010", "nombre": "Ventas"},
        {"numero": "2001", "nombre": "Proveedores"},
    ]
    result = cuentas_to_pipe_csv(rows)
    assert "Caja" in result
    assert "Proveedores" in result
    assert "Capital" not in result
    assert "Ventas" not in result


def test_keeps_all_rows_when_none_start_with_3_or_4():
    rows = [
        {"numero": "1001", "nombre": "Caja"},
        {"numero": "2001", "nombre": "Proveedores"},
        {"numero": "5001", "nombre": "Gastos"},
    ]
    result = cuentas_to_pipe_csv(rows)
    lines = result.strip().split("\n")
    assert len(lines) == 4  # header + 3 data rows


def test_all_rows_filtered_returns_only_header():
    rows = [
        {"numero": "3001", "nombre": "Patrimonio"},
        {"numero": "4001", "nombre": "Ingresos"},
    ]
    result = cuentas_to_pipe_csv(rows)
    lines = result.strip().split("\n")
    assert len(lines) == 1  # only header


# ---------------------------------------------------------------------------
# Excluded fields
# ---------------------------------------------------------------------------

def test_removes_cuenta_local():
    rows = [{"numero": "1001", "nombre": "Caja", "cuenta_local": "CL-001"}]
    result = cuentas_to_pipe_csv(rows)
    assert "cuenta_local" not in result
    assert "CL-001" not in result


def test_removes_pide_documento_referencia():
    rows = [{"numero": "1001", "nombre": "Caja", "pide_documento_referencia": True}]
    result = cuentas_to_pipe_csv(rows)
    assert "pide_documento_referencia" not in result


def test_removes_both_excluded_fields_at_once():
    rows = [{
        "numero": "1001",
        "nombre": "Caja",
        "cuenta_local": "CL",
        "pide_documento_referencia": True,
    }]
    result = cuentas_to_pipe_csv(rows)
    assert "cuenta_local" not in result
    assert "pide_documento_referencia" not in result
    assert "Caja" in result


def test_absent_excluded_fields_do_not_cause_error():
    rows = [{"numero": "1001", "nombre": "Caja"}]
    result = cuentas_to_pipe_csv(rows)
    assert "Caja" in result


# ---------------------------------------------------------------------------
# CSV format and delimiter
# ---------------------------------------------------------------------------

def test_uses_pipe_as_delimiter():
    rows = [{"numero": "1001", "nombre": "Caja"}]
    result = cuentas_to_pipe_csv(rows)
    header = result.split("\n")[0]
    assert "|" in header


def test_header_row_present():
    rows = [{"numero": "1001", "nombre": "Caja"}]
    result = cuentas_to_pipe_csv(rows)
    header = result.split("\n")[0]
    assert "numero" in header
    assert "nombre" in header


def test_data_row_values_correct():
    rows = [{"numero": "1001", "nombre": "Caja General"}]
    result = cuentas_to_pipe_csv(rows)
    assert "1001" in result
    assert "Caja General" in result


# ---------------------------------------------------------------------------
# Column order by first appearance
# ---------------------------------------------------------------------------

def test_column_order_by_first_appearance():
    rows = [
        {"numero": "1001", "nombre": "Caja", "extra": "X"},
        {"numero": "1002", "nombre": "Bancos", "otro": "Y"},
    ]
    result = cuentas_to_pipe_csv(rows)
    header = result.split("\n")[0]
    cols = header.split("|")
    assert cols[0] == "numero"
    assert cols[1] == "nombre"
    assert cols[2] == "extra"
    assert "otro" in cols


# ---------------------------------------------------------------------------
# None values → empty string
# ---------------------------------------------------------------------------

def test_none_field_value_becomes_empty_string():
    rows = [{"numero": "1001", "nombre": None}]
    result = cuentas_to_pipe_csv(rows)
    lines = result.strip().split("\n")
    data = lines[1].split("|")
    assert data[0] == "1001"
    assert data[1] == ""


# ---------------------------------------------------------------------------
# Non-string values stringified
# ---------------------------------------------------------------------------

def test_integer_value_is_stringified():
    rows = [{"numero": 1001, "nombre": "Caja"}]
    result = cuentas_to_pipe_csv(rows)
    assert "1001" in result


def test_boolean_value_is_stringified():
    rows = [{"numero": "1001", "nombre": "Caja", "activo": True}]
    result = cuentas_to_pipe_csv(rows)
    assert "True" in result
