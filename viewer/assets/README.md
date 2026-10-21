# Viewer assets

| File | Source | Licence |
|---|---|---|
| `kenney-character-male-a.glb` | Kenney, *Mini Characters* 1.0 (`Models/GLB format/character-male-a.glb`), https://kenney.nl/assets/mini-characters | CC0 1.0 (see `KENNEY-LICENSE.txt`) |

Modification: the external texture reference (`Textures/colormap.png`: images, textures, samplers and the
material's `baseColorTexture`) was removed and the base colour set to white, so the viewer can tint the
model per team without fetching a texture it does not use. Geometry, skin and animations are unchanged
(the binary chunk is copied byte for byte).

The viewer loads this one model and draws all 22 players as thin instances of it; if it cannot be
loaded, players fall back to capsules (`src/players.ts`). Credit: Kenney (www.kenney.nl), not required by CC0.
