from types import SimpleNamespace as Obj
import pytest
from app.services.comparisons import compare
from app.services.csv_import import boolean, number, preview, validate_mapping
from app.services.exports import safe_cell


@pytest.mark.parametrize(
    "declared,state,expected",
    [
        (False, "CON_CONSTRUCCION_VISIBLE", "POSIBLE_CONSTRUCCION_NO_DECLARADA"),
        (True, "CON_CONSTRUCCION_VISIBLE", "CONCORDANCIA"),
        (True, "SIN_CONSTRUCCION_VISIBLE", "CONSTRUCCION_DECLARADA_NO_VISIBLE"),
        (False, "SIN_CONSTRUCCION_VISIBLE", "CONCORDANCIA"),
        (False, "INDETERMINADO", "REVISION_REQUERIDA"),
        (False, "ERROR_ANALISIS", "REVISION_REQUERIDA"),
    ],
)
def test_comparison_scenarios(declared, state, expected):
    declaration = Obj(parcel_id="parcel", issues=[], declared_building=declared, declared_m2=None)
    assert compare(declaration, Obj(state=state))["state"] == expected


def test_floor_area_does_not_automatically_compare_to_roof_footprint():
    declaration = Obj(parcel_id="parcel", issues=[], declared_building=True, declared_m2=300)
    result = Obj(state="CON_CONSTRUCCION_VISIBLE", m2_huella_detectada=100)
    assert compare(declaration, result)["state"] == "CONCORDANCIA"
    assert compare(declaration, result)["warning"]
    assert compare(declaration, result, comparable_area=True)["state"] == "DIFERENCIA_DE_SUPERFICIE"


def test_missing_parcel_and_missing_result():
    d = Obj(parcel_id=None, issues=[])
    assert compare(d, None)["state"] == "NO_CONCILIADO"
    d.parcel_id = "parcel"
    assert compare(d, None)["state"] == "REVISION_REQUERIDA"


@pytest.mark.parametrize(
    "value,expected",
    [
        ("SÍ", True),
        ("SI", True),
        ("TRUE", True),
        ("1", True),
        ("BALDÍO", False),
        ("SIN CONSTRUCCIÓN", False),
        ("0", False),
        ("", None),
    ],
)
def test_boolean_aliases(value, expected):
    assert boolean(value) is expected


@pytest.mark.parametrize("payload", ["NaN", "Infinity", "-1", "1,2,3"])
def test_invalid_number(payload):
    with pytest.raises((ValueError, TypeError)):
        number(payload)


def test_locale_numbers_and_utf8_bom_tsv():
    assert number("1.234,50") == 1234.5
    assert number("1234.50", ".") == 1234.5
    raw = '\ufeffcoddepto\tcodloccat\tpadron\tnotas\nP\tAA\t00012\t"área, con comas"\n'.encode()
    data = preview(raw)
    assert data["delimiter"] == "\t"
    assert data["rows"][0]["padron"] == "00012"
    assert data["rows"][0]["notas"] == "área, con comas"


@pytest.mark.parametrize("value", ["=1+2", "+SUM(A1)", "-cmd", "@test", ' \t=HYPERLINK("x")', "\r=2"])
def test_csv_formula_injection(value):
    assert safe_cell(value).startswith("'")


def test_reject_ambiguous_mapping_and_binary_payload():
    with pytest.raises(ValueError):
        validate_mapping({"padron": "p"}, ["p"])
    with pytest.raises(ValueError):
        preview(b"a,b\n1,\x00\n")
