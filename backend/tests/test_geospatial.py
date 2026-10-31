import numpy as np
import pytest
from shapely.geometry import box, MultiPolygon, Polygon, GeometryCollection, mapping
from app.services.geospatial import measure, reproject, multipolygon, validate_wgs84
from app.services.inference import normalize, MEAN


@pytest.mark.parametrize(
    "buildings,expected",
    [
        ([box(2, 2, 4, 5)], 6),
        ([box(8, 0, 12, 10)], 20),
        ([box(0, 0, 5, 10), box(3, 0, 8, 10)], 80),
        ([box(-10, -10, 20, 20)], 100),
        ([], 0),
    ],
)
def test_exact_intersection_and_union(buildings, expected):
    result = measure(box(0, 0, 10, 10), buildings, box(0, 0, 10, 10), min_area=1)
    assert result["m2_huella_detectada"] == pytest.approx(expected)
    assert result["occupancy"] == pytest.approx(expected / 100)


def test_crosses_two_parcels_without_double_count():
    building = box(8, 2, 12, 8)
    first = measure(box(0, 0, 10, 10), [building], box(0, 0, 20, 10), min_area=1)
    second = measure(box(10, 0, 20, 10), [building], box(0, 0, 20, 10), min_area=1)
    assert first["m2_huella_detectada"] + second["m2_huella_detectada"] == 24


def test_multipolygon_and_partial_coverage():
    parcel = MultiPolygon([box(0, 0, 10, 10), box(20, 0, 30, 10)])
    result = measure(parcel, [box(0, 0, 30, 10)], box(0, 0, 5, 10), min_area=1)
    assert result["coverage"] == pytest.approx(0.25)
    assert result["m2_huella_detectada"] == 50
    assert result["state"] == "INDETERMINADO"


def test_no_imagery_is_not_empty_land():
    result = measure(box(0, 0, 10, 10), [], GeometryCollection())
    assert result["state"] == "INDETERMINADO"
    assert result["m2_huella_detectada"] is None


def test_invalid_polygon_is_repaired():
    invalid = Polygon([(0, 0), (5, 5), (5, 0), (0, 5), (0, 0)])
    assert not invalid.is_valid
    assert multipolygon(invalid).is_valid
    assert multipolygon(invalid).area == 12.5


def test_uruguay_crs_round_trip_and_metric_area():
    geom = box(-55.24, -34.38, -55.239, -34.379)
    metric = reproject(geom)
    assert 9000 < metric.area < 11000
    assert reproject(metric, 5382, 4326).hausdorff_distance(geom) < 1e-8
    with pytest.raises(ValueError):
        validate_wgs84(mapping(box(-34.38, -55.24, -34.37, -55.23)))


def test_rgb_normalization_does_not_divide_by_255():
    rgb = np.broadcast_to(MEAN, (3, 4, 4))
    np.testing.assert_array_equal(normalize(rgb), np.zeros((3, 4, 4), dtype=np.float32))


def test_probability_excludes_neighbouring_roofs_and_invalid_pixels():
    from rasterio.transform import from_origin
    from app.services.geospatial import parcel_confidence

    probabilities = np.full((4, 4), 0.95, dtype=np.float32)
    probabilities[:, :2] = 0.6
    valid = np.ones((4, 4), dtype=bool)
    binary = np.ones((4, 4), dtype=np.uint8)
    boundary = box(0, 0, 2, 4)
    affine = from_origin(0, 4, 1, 1)
    assert parcel_confidence(probabilities, binary, valid, boundary, affine) == pytest.approx(0.6)
    valid[:, :2] = False
    assert parcel_confidence(probabilities, binary, valid, boundary, affine) is None
