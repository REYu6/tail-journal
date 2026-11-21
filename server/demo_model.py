"""Procedural, watertight studio mascot used only in explicitly labelled demo orders."""
from __future__ import annotations

import json
import math
import struct
from functools import lru_cache


def _ellipsoid(x, y, z, center, radii):
    return sum(((v - c) / r) ** 2 for v, c, r in zip((x, y, z), center, radii)) - 1


def _field(x, y, z):
    # All parts overlap; sampling the union gives one shell, including ears and paws.
    torso = ((x / .54) ** 2 + ((y - .68) / .70) ** 2 + ((z + .08) / .46) ** 2) - 1
    head = ((x / .56) ** 2 + ((y - 1.43) / .48) ** 2 + ((z - .075) / .47) ** 2) - 1
    ear_y = y - 1.8
    ear_x = abs(x) - (.32 + .20 * ear_y)
    taper = max(.055, .24 - .52 * max(0, ear_y))
    ear = (ear_x / taper) ** 2 + (ear_y / .36) ** 2 + (z / (.12 + taper * .3)) ** 2 - 1
    paw = (((abs(x) - .24) / .22) ** 2 + ((y - .22) / .28) ** 2
           + ((z - .25) / .25) ** 2 - 1)
    tail = (((x - .46) / .21) ** 2 + ((y - .38) / .36) ** 2
            + ((z + .18) / .40) ** 2 - 1)
    return max(min(torso, head, ear, paw, tail), .047 - y)


def _color(x, y, z):
    if z > .36 and 1.17 < y < 1.7:
        if ((abs(x) - .224) / .067) ** 2 + ((y - 1.51) / .086) ** 2 < 1:
            return (59, 44, 39, 255)
        if (x / .09) ** 2 + ((y - 1.365) / .053) ** 2 < 1:
            return (173, 112, 97, 255)
        if (x / .32) ** 2 + ((y - 1.26) / .19) ** 2 < 1:
            return (248, 223, 183, 255)
    if y > 1.8 and z > .045 and abs(abs(x) - .34) < .115:
        return (222, 155, 137, 255)
    if 1.01 < y < 1.12:
        return (104, 143, 126, 255)
    if z > .24 and y < 1.05 and abs(x) < .24:
        return (244, 220, 184, 255)
    if y > 1.6 and z > .18 and (abs(x) < .048 or .21 < abs(x) < .27):
        return (180, 127, 80, 255)
    return (221, 174, 119, 255)


def _normal(v):
    mag = math.sqrt(sum(q * q for q in v)) or 1
    return tuple(q / mag for q in v)


def _sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def _cross(a, b):
    return (a[1]*b[2] - a[2]*b[1], a[2]*b[0] - a[0]*b[2], a[0]*b[1] - a[1]*b[0])


def _dot(a, b):
    return sum(x*y for x,y in zip(a,b))


def _mesh():
    step = .067
    nx, ny, nz = 28, 36, 23
    coords = [(ix*step-.88, iy*step-.10, iz*step-.72)
              for ix in range(nx) for iy in range(ny) for iz in range(nz)]
    values = [_field(*p) for p in coords]
    corners = (0, ny*nz, ny*nz+nz, nz, 1, ny*nz+1, ny*nz+nz+1, nz+1)
    tets = ((0,5,1,6),(0,1,2,6),(0,2,3,6),(0,3,7,6),(0,7,4,6),(0,4,5,6))
    verts, faces, edge_ids = [], [], {}

    def interp(a, b):
        key = (min(a,b), max(a,b))
        if key not in edge_ids:
            t = values[a] / (values[a]-values[b])
            edge_ids[key] = len(verts)
            verts.append(tuple(p+(q-p)*t for p,q in zip(coords[a], coords[b])))
        return edge_ids[key]

    for x in range(nx-1):
        for y in range(ny-1):
            for z in range(nz-1):
                start = (x*ny+y)*nz+z
                ids = [start+d for d in corners]
                inside = [values[p] <= 0 for p in ids]
                if not any(inside) or all(inside):
                    continue
                for tet in tets:
                    pos = [ids[p] for p in tet if inside[p]]
                    neg = [ids[p] for p in tet if not inside[p]]
                    if not pos or not neg:
                        continue
                    hits = [interp(a,b) for a in pos for b in neg]
                    # Two inside, two outside: the 2x2 list must be walked around its perimeter.
                    tris = [hits] if len(hits)==3 else [[hits[0],hits[1],hits[3]], [hits[0],hits[3],hits[2]]]
                    outward = _sub(coords[neg[0]], coords[pos[0]])
                    for i,j,k in tris:
                        face_normal = _cross(_sub(verts[j],verts[i]), _sub(verts[k],verts[i]))
                        faces.append((i,j,k) if _dot(face_normal,outward)>0 else (i,k,j))
    normals = [[0.,0.,0.] for p in verts]
    for i,j,k in faces:
        n = _cross(_sub(verts[j],verts[i]), _sub(verts[k],verts[i]))
        for v in (i,j,k):
            for axis in range(3):
                normals[v][axis] += n[axis]
    return verts, [_normal(n) for n in normals], faces


@lru_cache(maxsize=1)
def demo_mesh() -> tuple[bytes, bytes]:
    verts, normals, faces = _mesh()
    positions = [(x*.04, (y-.047)*.04, z*.04) for x,y,z in verts]
    chunks = [
        b"".join(struct.pack("<3f", *p) for p in positions),
        b"".join(struct.pack("<3f", *p) for p in normals),
        b"".join(bytes(_color(*p)) for p in verts),
        b"".join(struct.pack("<3I", *face) for face in faces),
    ]
    vertices = len(verts)
    views, offset = [], 0
    for i, chunk in enumerate(chunks):
        views.append({"buffer":0,"byteOffset":offset,"byteLength":len(chunk),"target":34962 if i<3 else 34963})
        offset += len(chunk)
    attributes = [
        {"bufferView":0,"componentType":5126,"count":vertices,"type":"VEC3",
         "min":[min(col) for col in zip(*positions)],"max":[max(col) for col in zip(*positions)]},
        {"bufferView":1,"componentType":5126,"count":vertices,"type":"VEC3"},
        {"bufferView":2,"componentType":5121,"normalized":True,"count":vertices,"type":"VEC4"},
        {"bufferView":3,"componentType":5125,"count":len(faces)*3,"type":"SCALAR"},
    ]
    doc = {"asset":{"version":"2.0","generator":"Pet studio local demo"},"scene":0,"scenes":[{"nodes":[0]}],
           "nodes":[{"mesh":0,"name":"Demo kitten"}],"meshes":[{"primitives":[{"attributes":{
               "POSITION":0,"NORMAL":1,"COLOR_0":2},"indices":3,"material":0}]}],
           "materials":[{"pbrMetallicRoughness":{"metallicFactor":0,"roughnessFactor":.84}}],
           "buffers":[{"byteLength":offset}],"bufferViews":views,"accessors":attributes}
    js = json.dumps(doc, separators=(",",":")).encode()
    js += b" " * (-len(js)%4)
    glb = (struct.pack("<4sII",b"glTF",2,28+len(js)+offset) + struct.pack("<I4s",len(js),b"JSON") + js
           + struct.pack("<I4s",offset,b"BIN\0") + b"".join(chunks))
    stl = bytearray(b"Pet studio sample kitten; dimensions in mm".ljust(80,b"\0")+struct.pack("<I",len(faces)))
    flat = [(x*1000,-z*1000,y*1000) for x,y,z in positions]
    for i,j,k in faces:
        a,b,c = flat[i],flat[j],flat[k]
        n = _normal(_cross(_sub(b,a),_sub(c,a)))
        stl.extend(struct.pack("<12fH",*n,*a,*b,*c,0))
    return glb, bytes(stl)
