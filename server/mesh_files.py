"""Mesh export and measurable geometric checks for the review workflow."""
from __future__ import annotations

import io

import numpy as np
import trimesh


def stl_from_glb(data: bytes, height_mm: float = 80.0) -> bytes:
    """Bake scene transforms; STL uses millimetres and a Z-up table plane."""
    scene = trimesh.load_scene(io.BytesIO(data), file_type="glb", skip_materials=True,
                               allow_remote=False, process=False)
    mesh = scene.to_geometry()
    if (not isinstance(mesh, trimesh.Trimesh) or not 0 < len(mesh.faces) <= 1_000_000
            or not np.isfinite(mesh.vertices).all()):
        raise ValueError("GLB 缺少可转换的三角网格")
    # glTF is Y-up; centre on the XY bed with the lowest Z exactly on the bed.
    mesh.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
    if mesh.extents[2] <= 0:
        raise ValueError("模型没有有效高度")
    mesh.apply_scale(height_mm / mesh.extents[2])
    low, high = mesh.bounds
    mesh.apply_translation((-(low[0]+high[0])/2, -(low[1]+high[1])/2, -low[2]))
    return mesh.export(file_type="stl")


def inspect_stl(data: bytes) -> dict:
    """Check closed topology and contour segments at three non-round layer heights.

    These checks supplement the operator's material, thickness, support and slicer
    review. A passed result alone makes no claim about an actual physical print.
    """
    try:
        mesh = trimesh.load_mesh(io.BytesIO(data), file_type="stl", process=False)
        if (not 0 < len(mesh.faces) <= 1_000_000 or not np.isfinite(mesh.vertices).all()
                or np.any(mesh.extents <= 0)):
            raise ValueError()
        mesh.merge_vertices()
        closed = bool(mesh.is_watertight and mesh.is_winding_consistent)
        slice_ok = True
        low, high = mesh.bounds
        tolerance = max(float(mesh.extents.max()) * 1e-8, 1e-7)
        for fraction in (.20371, .50917, .80237):
            z = low[2] + (high[2]-low[2])*fraction
            segments = trimesh.intersections.mesh_plane(mesh, (0,0,1), (0,0,z))
            if len(segments) == 0:
                slice_ok = False
                break
            endpoints = np.rint(segments.reshape((-1,3))[:,:2] / tolerance).astype(np.int64)
            _, counts = np.unique(endpoints, axis=0, return_counts=True)
            if not np.all(counts == 2):
                slice_ok = False
                break
        passed = bool(closed and slice_ok)
        return {"passed":passed, "watertight":closed, "slice_loops_ok":slice_ok,
                "faces":len(mesh.faces), "height_mm":round(float(mesh.extents[2]),2),
                "note":"几何与三层截面通过" if passed else "存在开口、方向或截面问题，请修复后复检"}
    except (TypeError, ValueError, IndexError, OSError):
        return {"passed":False, "watertight":False, "slice_loops_ok":False,
                "faces":0, "height_mm":0, "note":"无法解析有效 STL 三角网格"}
