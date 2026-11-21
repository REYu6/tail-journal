"""Build the public corgi collectible. Run with .venv/bin/python scripts/sculpt_corgi.py.

The dog is a single blended implicit sculpture with inset ears, a softly modelled
muzzle, individual toe lobes and hand-painted markings. Only small facial
features and the turned wood stand are separate parts, as on a resin miniature.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import trimesh
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SCALE = 0.041  # sculpture units to metres


def fade(a, b, x):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def ell(x, y, z, cx, cy, cz, rx, ry, rz):
    return (
        np.sqrt(((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 + ((z - cz) / rz) ** 2)
        - 1.0
    ) * np.minimum(np.minimum(rx, ry), rz)


def blend(a, b, width):
    h = np.maximum(width - np.abs(a - b), 0.0) / width
    return np.minimum(a, b) - width * 0.25 * h * h


def ears(x, y, z):
    t = (y - 2.285) / 0.37
    dx = np.abs(x) - (0.395 + 0.48 * (y - 2.28))
    dz = z - (0.236 - 0.07 * t + 0.15 * dx)
    width = 0.211 * (1.0 - 0.40 * np.clip(t, -1.0, 1.0))
    outer = (np.sqrt((dx / width) ** 2 + t * t + (dz / 0.117) ** 2) - 1.0) * 0.117
    inner = (
        np.sqrt(
            ((dx + 0.008) / (0.155 * (1.0 - 0.3 * np.clip(t, -1, 1)))) ** 2
            + ((y - 2.305) / 0.277) ** 2
            + ((dz - 0.207) / 0.182) ** 2
        )
        - 1.0
    ) * 0.13
    return -blend(-outer, inner, 0.020)


def head(x, y, z):
    height = (y - 1.846) / 0.484
    width = 0.565 * (1.0 - 0.20 * np.clip(height, -0.85, 0.95))
    skull = (
        np.sqrt((x / width) ** 2 + height * height + ((z - 0.286) / 0.460) ** 2) - 1.0
    ) * 0.46
    cheek = ell(np.abs(x), y, z, 0.302, 1.723, 0.423, 0.284, 0.227, 0.295)
    skull = blend(skull, cheek, 0.055)
    chin = ell(x, y, z, 0, 1.690, 0.621, 0.271, 0.156, 0.245)
    skull = blend(skull, chin, 0.085)
    snout = ell(x, y, z, 0, 1.823, 0.665, 0.235, 0.182, 0.242)
    skull = blend(skull, snout, 0.088)
    lip = ell(np.abs(x), y, z, 0.100, 1.766, 0.766, 0.177, 0.126, 0.178)
    return blend(blend(skull, lip, 0.049), ears(x, y, z), 0.043)


def torso(x, y, z):
    ax = np.abs(x)
    rump = ell(x, y, z, 0, 0.744, -0.29, 0.499, 0.573, 0.618)
    seat = ell(x, y, z, 0, 0.404, -0.355, 0.454, 0.295, 0.480)
    rump = blend(rump, seat, 0.082)
    chest = ell(x, y, z, 0, 1.095, 0.111, 0.437, 0.628, 0.415)
    body = blend(rump, chest, 0.130)
    neck = ell(x, y, z, 0, 1.447, 0.218, 0.386, 0.373, 0.351)
    body = blend(body, neck, 0.095)
    # A broad collar of cream fur narrowing toward a pendulous chest tuft.
    w = 0.352 + 0.19 * np.clip(y - 1.18, -0.4, 0.38)
    bib = ell(x, y, z, 0, 1.255, 0.386, w, 0.440, 0.265)
    body = blend(body, bib, 0.065)
    haunch = ell(ax, y, z, 0.345, 0.593, -0.299, 0.281, 0.445, 0.412)
    body = blend(body, haunch, 0.070)
    rear_foot = ell(ax, y, z, 0.449, 0.350, -0.102, 0.194, 0.157, 0.283)
    body = blend(body, rear_foot, 0.051)
    fore_leg = ell(
        ax, y, z + 0.20 * (y - 0.70), 0.263, 0.780, 0.330, 0.176, 0.423, 0.184
    )
    body = blend(body, fore_leg, 0.055)
    shin = ell(ax, y, z + 0.20 * (y - 0.56), 0.272, 0.553, 0.402, 0.159, 0.258, 0.160)
    body = blend(body, shin, 0.046)
    front_foot = ell(ax, y, z, 0.277, 0.356, 0.479, 0.184, 0.148, 0.219)
    body = blend(body, front_foot, 0.049)
    for off in (-0.091, 0.0, 0.091):
        toe = ell(
            ax, y, z, 0.277 + off, 0.347, 0.601 - 0.24 * abs(off), 0.065, 0.099, 0.111
        )
        body = blend(body, toe, 0.013)
    # Shallow creases separate the weight-bearing toes near the end of each paw.
    crease_ends = fade(0.589, 0.676, z) * fade(0.237, 0.29, y) * fade(0.464, 0.373, y)
    for between in (-0.050, 0.050):
        press = np.exp(-(((ax - 0.277 - between) / 0.024) ** 2))
        body += 0.013 * press * crease_ends
    tail = ell(
        x - 0.40 * (y - 0.77),
        y,
        z + 0.28 * (y - 0.77),
        0.140,
        0.768,
        -0.838,
        0.156,
        0.202,
        0.160,
    )
    body = blend(body, tail, 0.038)
    return np.maximum(body, 0.233 - y)


PIVOT = np.array([0.0, 1.69, 0.22])
head_matrix = trimesh.transformations.euler_matrix(0, np.radians(-3), np.radians(-4))[
    :3, :3
]


def head_space(x, y, z):
    p = (x - PIVOT[0], y - PIVOT[1], z - PIVOT[2])
    return tuple(
        PIVOT[i] + sum(head_matrix[j, i] * p[j] for j in range(3)) for i in range(3)
    )


def head_world(p):
    return (np.asarray(p) - PIVOT) @ head_matrix.T + PIVOT


def field(x, y, z):
    return blend(torso(x, y, z), head(*head_space(x, y, z)), 0.075)


def color_srgb(x, y, z):
    hx, hy, hz = head_space(x, y, z)
    hweight = fade(-0.055, 0.055, torso(x, y, z) - head(hx, hy, hz))
    hxabs = np.abs(hx)
    # Markings are painted in object space so the blaze continues over the forehead.
    edge = (
        1.690
        + 0.188 * np.exp(-((hxabs / 0.239) ** 2))
        + 0.092 * fade(0.54, 0.84, hz)
        + 0.029 * np.sin(hx * 7.0)
        + 0.035 * (hz - 0.6)
    )
    mask_muzzle = fade(-0.012, 0.012, edge - hy) * fade(0.20, 0.415, hz)
    blaze_width = (
        0.068
        + 0.083 * np.exp(-(((hy - 1.90) / 0.24) ** 2))
        + 0.028 * np.exp(-(((hy - 2.27) / 0.15) ** 2))
    )
    blaze_center = 0.014 + 0.056 * (hy - 2.01) + 0.012 * np.sin((hy - 1.9) * 12)
    blaze = fade(-0.009, 0.009, blaze_width - np.abs(hx - blaze_center)) * fade(
        0.27, 0.40, hz
    )
    hcream = np.maximum(mask_muzzle, blaze)
    chest_border = 0.475 - 0.30 * fade(0.96, 1.51, y) + 0.44 * x * x
    bcream = fade(-0.018, 0.018, z - chest_border) * fade(0.70, 0.91, y)
    front_socks = fade(
        -0.015, 0.015, 0.678 + 0.086 * np.cos(x * 7.0) + 0.039 * np.sin(z * 8) - y
    ) * fade(0.15, 0.265, z)
    rear_socks = fade(-0.01, 0.01, 0.469 + 0.035 * np.cos(z * 13) - y) * fade(
        -0.53, -0.31, z
    )
    bcream = np.maximum(bcream, np.maximum(front_socks, rear_socks))
    # An irregular white collar follows the nape into the bib. Rust shades
    # gather along the spine and feather to a lighter fawn on the breeches.
    nape = 1.430 + 0.16 * (z + 0.09) + 0.065 * np.sin(4 * x + 0.4)
    width = (
        0.062
        + 0.115 * fade(-0.17, 0.41, z)
        + 0.049 * np.exp(-(((x + 0.13) / 0.22) ** 2))
    )
    collar = fade(-0.023, 0.023, width - np.abs(y - nape))
    tail_tip = fade(-0.958, -0.980, z - 0.18 * (y - 0.78))
    bcream = np.maximum(bcream, np.maximum(collar, tail_tip))
    cream = bcream * (1 - hweight) + hcream * hweight
    ear_t = (hy - 2.285) / 0.37
    ear_dx = np.abs(hx) - (0.395 + 0.48 * (hy - 2.28))
    ear_dz = hz - (0.236 - 0.07 * ear_t + 0.15 * ear_dx)
    inner_shape = (
        (ear_dx + 0.008) / (0.151 * (1.0 - 0.30 * np.clip(ear_t, -1, 1)))
    ) ** 2 + ((hy - 2.305) / 0.270) ** 2
    pink = (
        (1 - fade(0.86, 1.06, inner_shape))
        * fade(0.001, 0.034, ear_dz)
        * fade(2.11, 2.20, hy)
        * hweight
    )
    # Fine, low-contrast brush movement instead of a flat uniform body colour.
    movement = (
        1.7 * np.sin(17 * x + 13 * y + 5 * z)
        + 1.3 * np.cos(29 * z - 6 * x + 8 * y)
        + 0.6 * np.sin(72 * x + 37 * z)
    )
    honey = fade(-0.60, 0.60, z) * 0.42 + fade(1.48, 2.40, y) * 0.4
    base = (
        np.array([191.0, 116.0, 59.0])
        + (np.array([222.0, 153.0, 84.0]) - np.array([191.0, 116.0, 59.0]))
        * honey[:, None]
    )
    saddle = (
        fade(0.46, 0.02, np.abs(x + 0.033)) * fade(0.05, -0.52, z) * fade(0.61, 1.14, y)
    )
    flanks = fade(0.16, 0.57, np.abs(x)) * fade(0.35, -0.35, z) * fade(0.87, 0.40, y)
    base += saddle[:, None] * [-21.0, -18.0, -14.0] + flanks[:, None] * [
        17.0,
        17.0,
        16.0,
    ]
    snoutlight = fade(-0.2, 0.9, z)
    ivory = np.array([233.0, 211.0, 177.0]) + snoutlight[:, None] * np.array(
        [11.0, 14.0, 17.0]
    )
    color = base * (1 - cream[:, None]) + ivory * cream[:, None]
    inner = np.array([226.0, 175.0, 137.0]) + fade(0.85, 0.06, inner_shape)[
        :, None
    ] * np.array([17.0, 22.0, 21.0])
    color = color * (1 - pink[:, None]) + inner * pink[:, None]
    return np.clip(color + movement[:, None] * np.array([1.0, 0.8, 0.6]), 0, 255)


def linear_bytes(srgb):
    a = np.asarray(srgb, dtype=float) / 255.0
    return np.rint(
        255 * np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)
    ).astype(np.uint8)


def flock_material():
    # Tileable filtered noise describes both the colour and the slopes of the
    # fine flock, keeping soft relief and mottling consistent as the light moves.
    n = 192
    rng = np.random.default_rng(41)
    ky, kx = np.meshgrid(np.fft.fftfreq(n), np.fft.rfftfreq(n), indexing="ij")

    def grain(horizontal, vertical):
        filt = np.exp(-2 * np.pi**2 * ((horizontal * kx) ** 2 + (vertical * ky) ** 2))
        noise = np.fft.irfft2(
            np.fft.rfft2(rng.normal(size=(n, n))) * filt, s=(n, n), axes=(0, 1)
        )
        return noise / np.std(noise)

    fur = 0.58 * grain(0.57, 1.45) + 0.32 * grain(1.22, 2.65) + 0.18 * grain(0.66, 0.71)
    dx = (np.roll(fur, -1, axis=1) - np.roll(fur, 1, axis=1)) * 0.10
    dy = (np.roll(fur, -1, axis=0) - np.roll(fur, 1, axis=0)) * 0.10
    tangent = np.stack((-dx, dy, np.ones_like(dx)), axis=2)
    tangent /= np.linalg.norm(tangent, axis=2, keepdims=True)
    relief = Image.fromarray(np.rint((tangent + 1) * 127.5).astype(np.uint8))
    pigment = np.clip(249 + 2.7 * fur, 226, 255).astype(np.uint8)
    albedo = Image.fromarray(np.repeat(pigment[:, :, None], 3, axis=2))
    return trimesh.visual.material.PBRMaterial(
        name="Hand-painted short pile",
        baseColorFactor=[255] * 4,
        baseColorTexture=albedo,
        normalTexture=relief,
        roughnessFactor=0.96,
        metallicFactor=0.0,
    )


def painted_surface(pts, faces, normals, colors):
    # Box projection keeps grain size constant on the underside, ears and legs.
    # Split only at a projection boundary and retain the common sculpt normals.
    dominant = np.argmax(np.abs(normals[faces].mean(axis=1)), axis=1)
    charts, indices = np.unique(
        np.stack(
            (faces, np.broadcast_to(dominant[:, None], faces.shape)), axis=2
        ).reshape(-1, 2),
        axis=0,
        return_inverse=True,
    )
    vertex, axis = charts.T
    pos = pts[vertex]
    u = np.where(axis == 0, pos[:, 2], pos[:, 0])
    v = np.where(axis == 1, pos[:, 2], pos[:, 1])
    uv = np.column_stack((u, v)) / 0.83
    visual = trimesh.visual.TextureVisuals(uv=uv, material=flock_material())
    rgba = np.column_stack((colors, np.full(len(colors), 255, np.uint8)))
    visual.vertex_attributes["color"] = rgba[vertex]
    return trimesh.Trimesh(
        vertices=pos,
        faces=indices.reshape(-1, 3),
        vertex_normals=normals[vertex],
        visual=visual,
        process=False,
    )


def net_mesh(step=0.0215):
    # Surface nets share one interpolated vertex at each sign-changing cell.
    coords = [
        np.arange(lo, hi, step, dtype=np.float32)
        for lo, hi in [(-0.81, 0.81), (0.191, 2.76), (-1.12, 1.13)]
    ]
    X, Y, Z = np.ix_(*coords)
    sdf = field(X, Y, Z)
    shape = tuple(n - 1 for n in sdf.shape)
    accum = np.zeros((*shape, 3), np.float32)
    count = np.zeros(shape, np.uint8)

    def sliced(offset):
        return sdf[tuple(slice(o, o + n) for o, n in zip(offset, shape))]

    for axis in range(3):
        other = [i for i in range(3) if i != axis]
        for a in (0, 1):
            for b in (0, 1):
                c = [0, 0, 0]
                c[other[0]] = a
                c[other[1]] = b
                d = list(c)
                d[axis] = 1
                v, w = sliced(c), sliced(d)
                hit = (v < 0) != (w < 0)
                ci = np.where(hit)
                count[ci] += 1
                for k in range(3):
                    accum[ci + (np.full(len(ci[0]), k),)] += c[k]
                accum[ci + (np.full(len(ci[0]), axis),)] += v[ci] / (v[ci] - w[ci])
    mask = count > 0
    xyz = np.column_stack(np.where(mask))
    pts = (xyz + accum[mask] / count[mask, None]) * step + np.array(
        [v[0] for v in coords]
    )
    ids = np.full(shape, -1, np.int32)
    ids[mask] = np.arange(len(pts))
    triangles = []
    for axis in range(3):
        i, j = (axis + 1) % 3, (axis + 2) % 3
        diff = np.diff(sdf < 0, axis=axis)
        q = np.array(np.where(diff)).T
        q = q[
            (q[:, i] > 0) & (q[:, j] > 0) & (q[:, i] < shape[i]) & (q[:, j] < shape[j])
        ]
        seq = []
        for oi, oj in [(0, 0), (-1, 0), (-1, -1), (0, -1)]:
            c = q.copy()
            c[:, i] += oi
            c[:, j] += oj
            seq.append(ids[tuple(c.T)])
        face = np.stack(seq, axis=1)
        outside = sdf[tuple(q.T)] >= 0
        face[outside] = face[outside, ::-1]
        triangles.extend((face[:, [0, 1, 2]], face[:, [0, 2, 3]]))
    faces = np.vstack(triangles)
    normals = np.array(
        [
            (
                field(*(pts + np.eye(3)[k] * 0.0005).T)
                - field(*(pts - np.eye(3)[k] * 0.0005).T)
            )
            / 0.001
            for k in range(3)
        ]
    ).T
    normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-6)
    cols = linear_bytes(color_srgb(*pts.T))
    return painted_surface(pts, faces, normals, cols)


def pbr(mesh, color, roughness):
    material = trimesh.visual.material.PBRMaterial(
        baseColorFactor=[*linear_bytes(color), 255],
        metallicFactor=0.0,
        roughnessFactor=roughness,
    )
    mesh.visual = trimesh.visual.TextureVisuals(material=material)
    return mesh


def sphere(center, radii, color, rough=0.53):
    m = trimesh.creation.uv_sphere(count=[18, 28])
    m.vertices = head_world(m.vertices * np.array(radii) + np.array(center))
    return pbr(m, color, rough)


def front_z(x, y):
    x, y = np.broadcast_arrays(x, y)
    lo = np.full(x.shape, 0.40)
    hi = np.full(x.shape, 1.15)
    for _ in range(32):
        mid = (lo + hi) * 0.5
        inside = head(x, y, mid) < 0
        lo = np.where(inside, mid, lo)
        hi = np.where(inside, hi, mid)
    return (lo + hi) * 0.5


def nose():
    m = trimesh.creation.uv_sphere(count=[24, 40])
    x, y, z = m.vertices.T
    coords = np.column_stack(
        (0.123 * x * (1.0 + 0.38 * y), 1.841 + 0.083 * y, 0.934 + 0.069 * z)
    )
    m.vertices = head_world(coords)
    return pbr(m, [53, 42, 36], 0.52)


def line(points, radii, color):
    pts = np.array(points)
    tangents = np.gradient(pts, axis=0)
    tangents /= np.linalg.norm(tangents, axis=1)[:, None]
    right = np.cross(tangents, [0, 0, 1])
    right /= np.maximum(np.linalg.norm(right, axis=1)[:, None], 1e-8)
    up = np.cross(tangents, right)
    theta = np.linspace(0, 2 * np.pi, 9)[:-1]
    rings = pts[:, None, :] + radii[:, None, None] * (
        right[:, None, :] * np.cos(theta)[None, :, None]
        + up[:, None, :] * np.sin(theta)[None, :, None]
    )
    faces = []
    for n in range(len(pts) - 1):
        for j in range(8):
            a, b = n * 8 + j, n * 8 + (j + 1) % 8
            faces.extend([[a, b, a + 8], [b, b + 8, a + 8]])
    m = trimesh.Trimesh(
        vertices=head_world(rings.reshape(-1, 3)), faces=faces, process=False
    )
    return pbr(m, color, 0.90)


def make():
    scene = trimesh.Scene()

    def add(mesh, name):
        scene.add_geometry(mesh, geom_name=name, node_name=name)

    add(net_mesh(), "Hand-painted corgi")
    for sign, side in [(-1, "left"), (1, "right")]:
        eye_x = sign * 0.245
        eye_y = 1.970
        z = float(front_z(eye_x, eye_y))
        add(
            sphere(
                [eye_x, eye_y, z - 0.004], [0.059, 0.061, 0.050], [47, 37, 30], 0.235
            ),
            side + " amber eye",
        )
        add(
            sphere(
                [eye_x - 0.012, eye_y + 0.018, z + 0.043],
                [0.008, 0.009, 0.004],
                [225, 214, 184],
                0.29,
            ),
            side + " eye glint",
        )
        t = np.linspace(0, 1, 35)
        x = sign * 0.219 * t
        y = 1.752 - 0.028 * np.sin(np.pi * t) + 0.027 * t * t
        add(
            line(
                np.column_stack([x, y, front_z(x, y) + 0.0005]),
                0.0050 * (0.04 + 0.96 * np.sqrt(1 - t)),
                [89, 62, 43],
            ),
            side + " smile",
        )
    t = np.linspace(0, 1, 15)
    y = 1.75 + 0.031 * t
    add(
        line(
            np.column_stack([np.zeros_like(t), y, front_z(0 * t, y) + 0.001]),
            np.full(len(t), 0.0041),
            [88, 60, 41],
        ),
        "Philtrum",
    )
    add(nose(), "Satin nose")
    from corgi_plinth import oak_plinth

    add(oak_plinth(0.94, 0.235, (0, 0, -0.02)), "Turned oak plinth")
    scene.apply_transform(trimesh.transformations.scale_matrix(SCALE))

    def finish(tree):
        body = next(
            material
            for material in tree["materials"]
            if material.get("name") == "Hand-painted short pile"
        )
        body["extensions"] = {"KHR_materials_specular": {"specularFactor": 0.24}}
        tree.setdefault("extensionsUsed", []).append("KHR_materials_specular")

    def compact_indices(buffers, tree):
        # Every part fits the core glTF unsigned-short index format.
        views = list(buffers)
        for accessor in tree["accessors"].values():
            if (
                accessor["componentType"] != 5125
                or accessor["type"] != "SCALAR"
                or accessor["max"][0] > 65535
            ):
                continue
            key = views[accessor["bufferView"]]
            packed = (
                np.frombuffer(buffers[key], dtype="<u4", count=accessor["count"])
                .astype("<u2")
                .tobytes()
            )
            buffers[key] = packed + bytes((-len(packed)) % 4)
            accessor["componentType"] = 5123

    out = ROOT / "web/public/media/studio-corgi.glb"
    out.write_bytes(
        trimesh.exchange.gltf.export_glb(
            scene, tree_postprocessor=finish, buffer_postprocessor=compact_indices
        )
    )
    print(out.name, out.stat().st_size, "bytes", scene.bounds.tolist())


if __name__ == "__main__":
    make()
