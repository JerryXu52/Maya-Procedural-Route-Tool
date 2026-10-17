# Procedural Pipe & Cable Generator for Maya

**Course:** Midterm Tool Pitch  
**Author:** [Your Name]  

---

### 1. The tool in one sentence
A Maya Python/Qt tool that procedurally generates customizable pipes and cables that route through picked objects, locators or mesh components, plug into surfaces along their normals, and stay live as anything they're attached to moves.

### 2. The chore it ends
It eliminates the manual, highly repetitive workflow of drawing CV curves, extruding geometry profiles, rigging endpoints, adjusting wire slack/sag, placing clamps and connectors, and fixing UVs by hand. Doing this manually takes 15–20 minutes per cable setup; this tool reduces the task to a few clicks and a few seconds.

### 3. The UI
- **Mode Selector:** dropdown at the top (`Cable / Pipe` for the midterm; `Fence` and `Road` greyed out until built — see section 9). The Route section stays shared; the controls below swap per mode.
- **Route Selection:** `Start` / `End` fields and an ordered `Waypoints` list, each with `Get Selected`. Accepts transforms, locators, vertices or faces.
- **Presets Dropdown:** `Single Industrial Pipe`, `Multi-Wire Bundle`, `Corrugated Hose`.
- **Shape Sliders** (drive Sweep Mesh attributes live):
  - Radius & Profile Sides
  - Twist & Taper
  - Sag / Slack Amount
  - Normal Lead-out Length (how far the cable leaves a surface before bending)
- **Hardware:** clamp/bracket/connector mesh picker, `Spacing` (every N units), `End Caps` checkbox.
- **UVs:** `Texture Repeat per Unit` so ribbed or striped textures tile along the length.
- **Action Buttons:** `Generate Cable`, `Bake to Static Mesh`, `Reset Settings`.

### 4. Why it's advanced
- **Sweep Mesh core:** Built on Maya's Sweep Mesh (`sweep` plugin, Maya 2022+) instead of extrusion, so radius, profile, twist and taper stay editable attributes with clean history.
- **Rig-free live following:** Curve points are driven by `decomposeMatrix` nodes connected to the picked objects' world matrices — no clusters or constraints to break.
- **Waypoint routing:** Cables pass through any number of picked objects/locators, so they can run along a wall and turn a corner.
- **Component attachment:** Picking a vertex or face makes the cable leave along that surface's normal, so it plugs into a port instead of floating near it.
- **Hardware along the length:** Clamps, brackets or connectors instanced at a set spacing and riding the curve, plus end caps.
- **Clean length-wise UVs:** UVs run along the cable and scale with its length, so tiling textures need no hand fixing.
- **Robust Execution:** Wrapped in single Undo chunks, with error popups for invalid selections; one-click bake to static geometry.

### 5. The three weeks
- **By Oct 13 — Sweep foundation:** PySide/Qt UI layout built; script calls `cmds.loadPlugin('sweep')` and generates a Sweep Mesh along a curve between two selected objects, with radius, profile, twist and taper sliders wired to the sweep attributes.
- **By Oct 20 — Live rig (core goal):** Curve end points driven by `decomposeMatrix` nodes from the picked objects, so the cable follows them with no rig. Sag/slack built into the node network so it stays live too. Then **waypoints**: an ordered list of extra locators/objects, each driving its own curve point the same way.
- **By Oct 26 — Components, hardware, UVs, polish:**
  - **Component attachment:** vertex/face picks give a position and normal; the cable leaves along the normal for a set lead-out length before bending, and stays attached when the mesh moves.
  - **Hardware:** clamps/brackets/connectors instanced every N units along the curve and following it live; end caps at both ends.
  - **UVs:** length-wise UVs scaled by curve length so textures tile evenly.
  - Presets, bake to static mesh, Undo chunking, edge-case error handling, UI polish.
- **Stretch (if time allows), in priority order:**
  1. Multi-wire bundles, noise variation.
  2. **Fence mode (basic):** posts instanced every N units plus swept rails, on flat ground.
  3. **Road mode (basic):** flat swept ribbon with length-wise lane-marking UVs — no terrain conforming or intersections.

### 6. The smallest version that still counts (MVP)
A Qt UI where selecting two objects generates a Sweep Mesh cable whose ends follow those objects live via `decomposeMatrix`, with working Radius and Sag sliders.

### 7. The riskiest part
Getting the cable to leave a picked vertex or face cleanly along its normal and stay attached while the mesh deforms — and keeping sag live alongside waypoints without the curve kinking. Moving to Sweep Mesh and `decomposeMatrix` removes the original risk (unstable history from extrusion and cluster rigs), so the remaining risk sits in the component-attachment math.

### 8. Thought process: building on my previous tool
In September I built `CableHoseRigTool.py`, a one-shot cable generator: it computed every point in Python and built meshes with no history, so any change meant clearing and regenerating. This midterm turns that idea into a **live, node-based** tool. I reviewed the old tool to decide what to keep, what to drop, and what to fix.

**What I'm carrying over — UI**
- A scrolling settings panel above a **pinned footer**, so `Generate`, `Clear` and the status box never scroll out of reach.
- **Collapsible sections** (Route, Shape, Hardware, UVs, Shading).
- A colour-coded **status box** (`[OK]` / `[WARNING]` / `[ERROR]`) at a fixed height, mirrored to the Script Editor.
- **Actionable messages** that tell the artist how to fix a problem, not just that one exists.
- Sliders with a comfortable range plus a typed field with a hard safety cap; a tooltip on every control.
- Edit/Help menus, `Reset Settings`, and only one tool window open at a time.

**What I'm carrying over — functionality**
- **One undo chunk per action** in `try/finally`; for live sliders, one chunk per drag so a whole drag undoes with one Ctrl+Z.
- **Two-level error handling:** a custom error for limits I enforce, plus a catch-all at the UI layer, so Maya never sees an unhandled exception.
- **Input sanitising** of every UI value (empty values, text, NaN and infinity).
- **Selection checks** that report ignored items and catch anchors sitting on top of each other — extended to vertices and faces.
- **Sag scaled by span length**, so the slider feels the same at any scene scale — now live through a `distanceBetween` node.
- **Catenary shape, made live:** per-point catenary weights are computed once at build time; the node network does weight × sag × span length, so the cable keeps a real hanging-chain shape with no Python running per frame.
- One shared shader, a single top-level group, and the guide curve kept in the scene (now as the live driver).
- Chaining spans across several picks grows into true **waypoint routing** along one continuous curve.
- My command-port remote launcher, kept as a separate `launch.py` for development.

**What I'm leaving behind**
- Hand-built coordinate frames — Sweep Mesh orients the tube itself.
- Extrude / cylinder fallback with history turned off — the opposite of a live design. If the `sweep` plugin won't load, the tool shows a clear error.
- Collision relaxation and spatial hashing — they run after the build and can't keep up with a live rig. Sunflower packing may return with the bundle stretch goal.
- Assignment-specific features (Beta mode, Length Stagger, Slack Variation).

**What I'm fixing**
- **Selection order:** waypoints use `cmds.ls(orderedSelection=True)` so the cable follows the order I clicked.
- **Leftover nodes:** generating twice used to leave empty duplicate groups, and cleanup relied on name prefixes. Every node the tool creates is now **tagged with a custom attribute**, and Clear deletes by tag.
- **Duplicated defaults:** one `DEFAULTS` table feeds both the UI and Reset.
- **All-or-nothing clearing:** each cable stores its settings as attributes on its group, enabling `Delete Selected Cable` and `Load Selected Cable` for editing an existing cable.

### 9. Future modes: fences and roads
Cables, fences and roads are all **curve-driven procedural geometry**, so one tool with a mode switch can build all three. Most of the cable work carries straight over:

| Building block | Cable / Pipe | Fence | Road |
|---|---|---|---|
| Route picking, waypoints, live curve | ✅ | ✅ | ✅ |
| Sweep Mesh along the curve | the tube | rails (thin box profile) | road surface (flat, wide profile) |
| Hardware instanced every N units | clamps, brackets | **fence posts** | lamp posts, road markers |
| Length-wise UVs | ribbed / striped textures | rail wood grain | **lane markings** |
| Sag | ✅ | wire fences only | ❌ |

**Architecture (built into the midterm from the start)**
- **Shared route core:** start/end/waypoint picking (objects or components), the live curve, `decomposeMatrix` drivers, undo and error handling.
- **One generator per mode** — `CableGenerator`, `FenceGenerator`, `RoadGenerator` — each with the same interface: `build(route, settings)`, `update(settings)`, `bake()`, `delete()`.
- **GUI:** a mode dropdown on top; the Route section is always visible; a stacked panel swaps in each mode's controls; `Generate`, `Clear` and the status box stay in the shared footer.
- **Tagging:** every generated object records which mode built it, so `Load Selected` opens the right panel.

**Where each mode gets hard**
- **Fence:** posts must stay vertical and sit on uneven ground rather than following the curve's tilt; gaps and gates.
- **Road:** conforming to terrain, banking on curves, blending into the ground, and intersections — the hardest of the three.
- **Cable:** component attachment along normals (already the riskiest part of the midterm).

**Plan**
1. **Midterm:** build the mode architecture and dropdown, with only `Cable / Pipe` working.
2. **Stretch:** basic Fence mode, then basic Road mode (see section 5).
3. **After the midterm:** terrain conforming for fences and roads, gates, road intersections.
