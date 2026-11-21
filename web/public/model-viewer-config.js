// Configure lazily imported model-viewer before its first element is created.
self.ModelViewerElement = {
  ...self.ModelViewerElement,
  dracoDecoderLocation: "/decoders/draco/",
  ktx2TranscoderLocation: "/decoders/basis/",
  meshoptDecoderLocation: "/decoders/meshopt.js",
};
