import numpy as np
import pytest
import torch
from types import SimpleNamespace
from unittest.mock import MagicMock

from app import create_app
from app import tasks
from app.models import ImageryScene, AIModelVersion
from app.schemas import AnalysisSchema
from app.services.inference import segment


class InspectInput(torch.nn.Module):
    def forward(self, data):
        # Building probability is determined by the normalized red channel.
        return torch.stack((torch.zeros_like(data[:, 0]), data[:, 0]), dim=1)


def test_unet_uses_rgb_scaled_to_unit_interval_and_building_channel_one():
    image = np.full((3, 64, 64), 255, dtype=np.uint8)
    result = segment(image, InspectInput(), window=64, overlap=32, architecture="unetpp_efficientnet_b4")
    assert result.shape == (64, 64)
    assert result == pytest.approx(np.full((64, 64), 1 / (1 + np.exp(-1)), dtype=np.float32), abs=1e-6)


def test_analysis_device_is_validated_and_defaults_to_cpu():
    data = {
        "parcel_ids": ["00000000-0000-4000-8000-000000000001"],
        "scene_id": "00000000-0000-4000-8000-000000000002",
        "model_version_id": "00000000-0000-4000-8000-000000000003",
    }
    assert AnalysisSchema().load(data)["device"] == "cpu"
    assert AnalysisSchema().load({**data, "device": "cuda"})["device"] == "cuda"
    assert "device" in AnalysisSchema().validate({**data, "device": "gpu"})


def test_gpu_unavailable_fails_before_parcels_are_modified(monkeypatch):
    session = MagicMock()
    session.execute.return_value.scalar_one.return_value = SimpleNamespace(
        scene_id="scene", model_version_id="model", parameters={"device": "cuda"}
    )
    session.get.side_effect = lambda model, _: (
        SimpleNamespace() if model is ImageryScene else SimpleNamespace(enabled=True, model_id="FLAIR")
    )
    monkeypatch.setattr(tasks, "db", SimpleNamespace(session=session))
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    with create_app("testing").app_context(), pytest.raises(ValueError, match="GPU NVIDIA no disponible"):
        tasks.analyze(SimpleNamespace(id="test"))
    session.add.assert_not_called()
    session.commit.assert_not_called()


def test_gpu_inference_failure_does_not_replace_prior_results(monkeypatch):
    from shapely.geometry import box
    from app.services import geospatial, imagery, inference

    session = MagicMock()
    run = SimpleNamespace(id="run", scene_id="scene", model_version_id="model", parameters={"device": "cuda"})
    session.execute.return_value.scalar_one.return_value = run
    session.execute.return_value.scalar_one_or_none.return_value = None
    parcel = SimpleNamespace(id="parcel", source_version_id="version", active=True, geom="geom")
    model = SimpleNamespace(enabled=True, model_id="FLAIR", filename="model.pth", sha256="hash")
    session.get.side_effect = lambda cls, _: (
        SimpleNamespace() if cls is ImageryScene else model if cls is AIModelVersion else parcel
    )
    monkeypatch.setattr(tasks, "db", SimpleNamespace(session=session))
    monkeypatch.setattr(tasks, "progress", lambda *args: None)
    monkeypatch.setattr(tasks, "to_shape", lambda _: box(0, 0, 5, 5))
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(geospatial, "reproject", lambda shape: shape)
    monkeypatch.setattr(imagery, "download_crop", lambda *args: (b"image", None))
    monkeypatch.setattr(imagery, "read_rgb", lambda _: (None, None, None, None))
    monkeypatch.setattr(inference, "load_model", lambda *args: object())

    def out_of_memory(*args, **kwargs):
        raise RuntimeError("CUDA out of memory")

    monkeypatch.setattr(inference, "segment", out_of_memory)
    with create_app("testing").app_context(), pytest.raises(ValueError, match="ejecutar el modelo"):
        tasks.analyze(SimpleNamespace(id="test", payload={"parcel_ids": ["parcel"]}))
    session.add.assert_not_called()
    session.commit.assert_not_called()
