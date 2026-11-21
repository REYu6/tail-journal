import { copyFile, mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../", import.meta.url));
const libraries = join(root, "node_modules/three/examples/jsm/libs");
const decoders = join(root, "public/decoders");
const assets = [
  ["draco/gltf/draco_decoder.js", "draco/draco_decoder.js"],
  ["draco/gltf/draco_wasm_wrapper.js", "draco/draco_wasm_wrapper.js"],
  ["draco/gltf/draco_decoder.wasm", "draco/draco_decoder.wasm"],
  ["draco/README.md", "draco/README.md"],
  ["basis/basis_transcoder.js", "basis/basis_transcoder.js"],
  ["basis/basis_transcoder.wasm", "basis/basis_transcoder.wasm"],
  ["basis/README.md", "basis/README.md"],
];
for (const [source, destination] of assets) {
  const target = join(decoders, destination);
  await mkdir(dirname(target), { recursive: true });
  await copyFile(join(libraries, source), target);
}
// model-viewer's URL setting expects a classic script. Three ships the same
// decoder in an ESM wrapper; preserve the implementation and its MIT notice.
const meshopt = await readFile(join(libraries, "meshopt_decoder.module.js"), "utf8");
const classic = meshopt.replace(/export\s*\{\s*MeshoptDecoder\s*\}\s*;?\s*$/, "");
if (classic === meshopt) throw new Error("Three meshopt export changed; check the classic script bundle");
await writeFile(join(decoders, "meshopt.js"), classic);
