import hashlib
import json
from shapely.geometry import box, mapping, MultiPolygon
from app.extensions import db
from app.models import ParcelAnalysisResult
from app.services.cadastre import import_file
from app.services.geospatial import reproject
from conftest import login
from test_workflow_integration import seed_parcel, seed_result


def test_changed_parcel_geometry_invalidates_current_result_but_preserves_history(client, tmp_path):
    user = login(client)
    parcel = seed_parcel()
    result, _ = seed_result(parcel, user.id)
    geom = MultiPolygon([reproject(box(662000, 6194700, 662030, 6194720), 5382, 4326)])
    feature = {
        "type": "Feature",
        "id": "TEST.changed",
        "geometry": mapping(geom),
        "properties": {
            "coddepto": "P",
            "codloccat": "AA",
            "nomdepto": "LAVALLEJA",
            "nomloccat": "MINAS",
            "padron": "00012",
        },
    }
    path = tmp_path / "changed.ndjson"
    path.write_text(json.dumps(feature) + "\n", encoding="utf-8")
    path.with_suffix(".manifest.json").write_text(
        json.dumps(
            {
                "source": "SYNTHETIC TEST SNAPSHOT",
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "count": 1,
            }
        ),
        encoding="utf-8",
    )
    imported = import_file(path)
    db.session.refresh(parcel)
    assert parcel.current_result_id is None
    assert db.session.get(ParcelAnalysisResult, result.id) is not None
    from app.services.results import promote_result

    assert promote_result(result) is False
    db.session.commit()
    db.session.refresh(parcel)
    assert parcel.current_result_id is None
    response = client.get(
        f"/api/v1/cadastral/versions/{result.parcel_version_id}/differences/{imported['id']}"
    )
    assert response.status_code == 200
    assert response.json["items"][0]["change"] == "GEOMETRIA_MODIFICADA"
