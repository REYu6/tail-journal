"""A turned oak display stand for the studio's little corgi sculpture.

The face and edge grain blend around the turned rim. The finished GLB embeds
their shared atlas.
"""

from functools import lru_cache
from io import BytesIO

import numpy as np
import trimesh
from PIL import Image

_ATLAS_WIDTH = 704
_ATLAS_HEIGHT = 864
_TOP = (8, 8, 688, 688)
_EDGE = (8, 718, 688, 132)
_UNDERSIDE = (15, 15, 94, 94)  # Inside the unused corner of the round face UV.


def _noise(x, z, seed, period=None):
    """Smooth, repeatable 2D value noise in [0, 1]."""
    ix, iz = np.floor(x), np.floor(z)
    dx, dz = x - ix, z - iz
    dx = dx * dx * (3 - 2 * dx)
    dz = dz * dz * (3 - 2 * dz)

    def lattice(i, j):
        if period is not None:
            i = np.mod(i, period)
        return np.mod(np.sin(i * 127.1 + j * 311.7 + seed * 73.3) * 43758.5453, 1)

    left = lattice(ix, iz) * (1 - dz) + lattice(ix, iz + 1) * dz
    right = lattice(ix + 1, iz) * (1 - dz) + lattice(ix + 1, iz + 1) * dz
    return left * (1 - dx) + right * dx


def _oak_face(x, z):
    """A fine, gently wandering face grain in quartersawn honey oak."""
    drift = 0.023 * (_noise(x * 1.8, z * 1.2, 8) - 0.5)
    fiber = z + 0.065 * x + 0.021 * x * x + drift
    tone = 13 * (_noise(x * 1.5, fiber * 4, 21) - 0.5)
    fibers = 9 * (_noise(x * 3.5, fiber * 39, 31) - 0.5)
    short_pores = np.clip((_noise(x * 17, fiber * 161, 39) - 0.67) / 0.33, 0, 1)
    return tone + fibers - 20 * short_pores


def _oak_edge(turn, y):
    """Long broken traces wrap around the edge and meet at the UV seam."""
    drift = 0.015 * (_noise(turn * 4, y * 3, 16, period=4) - 0.5)
    fiber = y + drift
    tone = 12 * (_noise(turn * 6, fiber * 8, 23, period=6) - 0.5)
    fibers = 10 * (_noise(turn * 15, fiber * 68, 34, period=15) - 0.5)
    pores = np.clip((_noise(turn * 86, fiber * 176, 43, period=86) - 0.65) / 0.35, 0, 1)
    return tone + fibers - 19 * pores - 2


def _contact_shadow(x, z):
    """Ambient shading below the fixed figurine, in units of stand radius."""
    def footprint(x, z):
        seat = (x / 0.51) ** 2 + ((z + 0.34) / 0.50) ** 2
        front = ((np.abs(x) - 0.295) / 0.205) ** 2 + ((z - 0.554) / 0.238) ** 2
        rear = ((np.abs(x) - 0.478) / 0.211) ** 2 + ((z + 0.085) / 0.281) ** 2
        return np.minimum(np.minimum(front, rear), seat)

    contact = 42 * np.exp(-1.35 * footprint(x, z))
    soft_shadow = 16 * np.exp(-0.80 * footprint(x + 0.027, z + 0.043))
    return contact + soft_shadow


def _profile(height_ratio):
    """Radius, height and analytic normal from the underside to the top lip."""
    bevel = min(0.042, height_ratio * 0.19)
    angle = np.linspace(0, np.pi / 2, 6)
    lower = np.column_stack((
        1 - bevel + bevel * np.sin(angle),
        bevel * (1 - np.cos(angle)),
        np.sin(angle),
        -np.cos(angle),
    ))
    upper = np.column_stack((
        1 - bevel + bevel * np.cos(angle),
        height_ratio - bevel + bevel * np.sin(angle),
        np.cos(angle),
        np.sin(angle),
    ))
    return np.vstack((lower, upper))


def _surface_length(profile):
    lengths = np.linalg.norm(np.diff(profile[:, :2], axis=0), axis=1)
    cumulative = np.r_[0, np.cumsum(lengths)]
    return cumulative / cumulative[-1]


@lru_cache(maxsize=2)
def _wood_atlas(height_ratio):
    profile = _profile(height_ratio)
    distance = _surface_length(profile)
    yy, xx = np.mgrid[:_ATLAS_HEIGHT, :_ATLAS_WIDTH]
    col, row, w, h = _TOP
    x, z = (xx - col) / w * 2 - 1, (yy - row) / h * 2 - 1
    light = _oak_face(x, z) - _contact_shadow(x, z)
    # The underside uses its own small unshaded island.
    col, row, w, h = _UNDERSIDE
    underside = np.s_[row-3:row+h+4, col-3:col+w+4]
    x = (xx[underside] - col) / w * 2 - 1
    z = (yy[underside] - row) / h * 2 - 1
    light[underside] = _oak_face(x, z)
    col, row, w, h = _EDGE
    margin = row - 8
    turn = (xx[margin:] - col) / w
    theta = np.pi * (2 * turn - 1)
    along = np.clip(1 - (yy[margin:] - row) / h, 0, 1)
    radius = np.interp(along, distance, profile[:, 0])
    height = np.interp(along, distance, profile[:, 1])
    x, z = radius * np.sin(theta), radius * np.cos(theta)
    cap = _oak_face(x, z)
    cap -= _contact_shadow(x, z) * (height / height_ratio)
    edge = _oak_edge(turn, height)
    radial = np.interp(along, distance, profile[:, 2])
    light[margin:] = (1 - radial) * cap + radial * edge
    honey_oak = np.array([176, 129, 82])
    color = np.clip(honey_oak + light[..., None] * [1.03, 0.9, 0.7], 0, 255).astype("uint8")
    # The exporter preserves the JPEG container in the self-contained GLB.
    source = BytesIO()
    Image.fromarray(color).save(source, format="JPEG", quality=89)
    source.seek(0)
    return Image.open(source)


def _uv(x, y):
    return ((x + 0.5) / _ATLAS_WIDTH, 1 - (y + 0.5) / _ATLAS_HEIGHT)


def oak_plinth(radius, height, center=(0, 0, 0)):
    """Return a textured Y-up mesh centered at the given bottom-face point."""
    if radius <= 0 or height <= 0:
        raise ValueError("Stand radius and height must be positive")
    ratio = height / radius
    profile = _profile(ratio)
    distance = _surface_length(profile)
    segments = 128
    angles = np.linspace(-np.pi, np.pi, segments + 1)
    positions, normals, coordinates, faces = [], [], [], []
    px, py, width, strip_height = _EDGE

    for i, (r, y, nr, ny) in enumerate(profile):
        for j, a in enumerate(angles):
            s, c = np.sin(a), np.cos(a)
            positions.append((r * s, y, r * c))
            normals.append((nr * s, ny, nr * c))
            coordinates.append(_uv(px + width * j / segments, py + (1 - distance[i]) * strip_height))
            if i and j:
                lo = (i - 1) * (segments + 1) + j - 1
                hi = lo + segments + 1
                faces.extend(((lo, lo + 1, hi), (lo + 1, hi + 1, hi)))

    for i, direction in ((0, -1), (-1, 1)):
        px, py, width, tile_height = _TOP if direction > 0 else _UNDERSIDE
        r, y = profile[i, :2]
        start = len(positions)
        positions.append((0, y, 0))
        normals.append((0, direction, 0))
        coordinates.append(_uv(px + width / 2, py + tile_height / 2))
        for j, a in enumerate(angles):
            x, z = r * np.sin(a), r * np.cos(a)
            positions.append((x, y, z))
            normals.append((0, direction, 0))
            coordinates.append(_uv(px + (x + 1) * width / 2, py + (z + 1) * tile_height / 2))
            if j:
                f = (start, start + j, start + j + 1)
                faces.append(f if direction > 0 else f[::-1])

    material = trimesh.visual.material.PBRMaterial(
        name="Satin oak",
        baseColorTexture=_wood_atlas(ratio),
        metallicFactor=0.0,
        roughnessFactor=0.87,
        doubleSided=False,
    )
    visuals = trimesh.visual.TextureVisuals(uv=np.array(coordinates), material=material)
    return trimesh.Trimesh(
        vertices=np.asarray(positions) * radius + center,
        faces=faces,
        vertex_normals=normals,
        visual=visuals,
        process=False,
    )
