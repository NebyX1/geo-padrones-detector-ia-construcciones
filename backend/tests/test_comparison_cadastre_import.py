"""Imports are additive: a prepared comparison dataset never rewrites WFS history."""
import hashlib
import json

import pytest
from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import MultiPolygon, Polygon, mapping
from sqlalchemy import select

from app.extensions import db
from app.models import CadastralDatasetVersion, CadastralLocality, Parcel, ParcelGeometryVersion
from app.services.cadastre import import_file
from app.services.comparison_cadastre_import import import_geojson_parcels


def feature(loc, number, geom, kind="urbano_suburbano"):
    identity = f"P:{loc}:{number}"
    return {"type": "Feature", "id": identity, "geometry": mapping(geom) if geom else None,
            "properties": {"id_catastral": identity, "codigo_departamento": "P", "padron": number,
                           "codigo_localidad": None if kind == "rural" else loc,
                           "localidad": "MINAS" if kind != "rural" else None,
                           "tipo_padron_catastral": kind}}


def source_file(path, features, truncated=False):
    # Same one-feature-per-line format as scripts/generar_catastro_lavalleja.py.
    content = '{"type":"FeatureCollection","metadata":{},"features":[\n'
    content += ",\n".join(json.dumps(f) for f in features)
    content += "\n" if truncated else "\n]}\n"
    path.write_text(content, encoding="utf-8")
    return path


def test_import_adds_only_missing_geometry_and_is_idempotent(context, tmp_path):
    old_version = CadastralDatasetVersion(sha256="a" * 64, source="WFS", count=1, metadata_json={})
    loc = CadastralLocality(coddepto="P", codloccat="AA", name="MINAS")
    db.session.add_all([old_version, loc])
    db.session.flush()
    old_shape = MultiPolygon([Polygon([(-55.24, -34.37), (-55.239, -34.37),
                                        (-55.239, -34.369), (-55.24, -34.37)])])
    old = Parcel(coddepto="P", codloccat="AA", padron="10", locality_id=loc.id,
                 geom=from_shape(old_shape, srid=4326), m2_parcela=100,
                 source_version_id=old_version.id)
    db.session.add(old)
    db.session.commit()
    old_id, old_version_id = old.id, old_version.id

    new_shape = Polygon([(-55.25, -34.38), (-55.249, -34.38), (-55.249, -34.379), (-55.25, -34.38)])
    path = source_file(tmp_path / "catastro.geojson", [
        feature("AA", 10, new_shape), feature("AA", 11, new_shape),
        feature("R", 10, new_shape, "rural"), feature("R", 11, None, "rural"),
    ])
    result = import_geojson_parcels(path)
    assert result["importadas"] == 2
    assert result["urbanas"] == result["rurales"] == 1
    assert result["existentes"] == result["sin_geometria"] == 1
    persisted_old = db.session.get(Parcel, old_id)
    assert persisted_old.source_version_id == old_version_id
    assert to_shape(persisted_old.geom).equals(old_shape)
    assert db.session.scalar(select(Parcel.id).where(Parcel.codloccat == "R", Parcel.padron == "10"))
    assert len(db.session.scalars(select(ParcelGeometryVersion)).all()) == 2
    repeated = import_geojson_parcels(path)
    assert repeated["idempotent"] is True
    assert repeated["id"] == result["id"]
    assert len(db.session.scalars(select(Parcel)).all()) == 3


def test_truncated_file_rolls_back_all_changes(context, tmp_path):
    geom = Polygon([(-55.25, -34.38), (-55.249, -34.38), (-55.249, -34.379), (-55.25, -34.38)])
    path = source_file(tmp_path / "bad.geojson", [feature("R", 1, geom, "rural")], truncated=True)
    with pytest.raises(ValueError, match="truncado"):
        import_geojson_parcels(path)
    assert db.session.scalars(select(Parcel)).all() == []
    assert db.session.scalars(select(CadastralDatasetVersion)).all() == []


def test_urban_refresh_does_not_retire_rural(context, tmp_path):
    version = CadastralDatasetVersion(sha256="b" * 64, source="precedente", count=2, metadata_json={})
    urban = CadastralLocality(coddepto="P", codloccat="AA", name="MINAS")
    rural = CadastralLocality(coddepto="P", codloccat="R", name="Rural")
    db.session.add_all([version, urban, rural])
    db.session.flush()
    geom = MultiPolygon([Polygon([(-55.25, -34.38), (-55.249, -34.38),
                                  (-55.249, -34.379), (-55.25, -34.38)])])
    db.session.add_all([
        Parcel(coddepto="P", codloccat=loc.codloccat, padron="1", locality_id=loc.id,
               geom=from_shape(geom, srid=4326), m2_parcela=100, source_version_id=version.id)
        for loc in (urban, rural)
    ])
    db.session.commit()
    next_feature = {"type": "Feature", "id": "feature-urban-new", "geometry": mapping(geom),
                    "properties": {"coddepto": "P", "codloccat": "AA", "padron": "2",
                                   "nomdepto": "LAVALLEJA", "nomloccat": "MINAS"}}
    data = tmp_path / "urban.ndjson"
    data.write_text(json.dumps(next_feature) + "\n", encoding="utf-8")
    data.with_suffix(".manifest.json").write_text(json.dumps({
        "sha256": hashlib.sha256(data.read_bytes()).hexdigest(), "source": "WFS",
        "complete": True, "bbox": None,
    }), encoding="utf-8")
    result = import_file(data)
    assert result["retired"] == 1
    assert db.session.scalar(select(Parcel.active).where(Parcel.codloccat == "R")) is True
    assert db.session.scalar(select(Parcel.active).where(Parcel.codloccat == "AA", Parcel.padron == "1")) is False
