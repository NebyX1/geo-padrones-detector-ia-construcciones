import io
import numpy as np
from PIL import Image
from rasterio.io import MemoryFile
from rasterio.warp import calculate_default_transform, reproject, Resampling, transform_bounds
from rasterio.transform import array_bounds
from .storage import storage


def preview_mask(result):
    if not result.mask_key:
        raise ValueError("La máscara no está disponible.")
    raw = storage().get(result.mask_key)
    with MemoryFile(raw) as memory:
        with memory.open() as src:
            affine, width, height = calculate_default_transform(
                src.crs, "EPSG:3857", src.width, src.height, *src.bounds
            )
            target = np.full((height, width), 255, dtype="uint8")
            reproject(
                src.read(1),
                target,
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=affine,
                dst_crs="EPSG:3857",
                src_nodata=255,
                dst_nodata=255,
                resampling=Resampling.nearest,
            )
            bounds = transform_bounds(
                "EPSG:3857", "EPSG:4326", *array_bounds(height, width, affine), densify_pts=21
            )
    rgba = np.zeros((height, width, 4), dtype="uint8")
    rgba[target == 1] = [24, 214, 157, 185]
    output = io.BytesIO()
    Image.fromarray(rgba).save(output, format="PNG")
    return output.getvalue(), list(bounds)
