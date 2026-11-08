#!/bin/sh
# Downloads three.js into web/vendor so the game never depends on a CDN. Run once, then git add/commit/push.
set -e
cd "$(dirname "$0")/web"; mkdir -p vendor; cd vendor
curl -fsSL -o three.min.js https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js || curl -fsSL -o three.min.js https://cdn.jsdelivr.net/npm/three@0.128.0/build/three.min.js
for f in shaders/CopyShader shaders/LuminosityHighPassShader postprocessing/EffectComposer postprocessing/RenderPass postprocessing/ShaderPass postprocessing/UnrealBloomPass; do
  n=$(basename "$f").js
  curl -fsSL -o "$n" "https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/$f.js" || curl -fsSL -o "$n" "https://unpkg.com/three@0.128.0/examples/js/$f.js"
done
ls -la
