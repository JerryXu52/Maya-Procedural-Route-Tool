# Procedural Pipe & Cable Generator for Maya

**Course:** Midterm Tool Pitch  
**Author:** [Your Name]  

---

### 1. The tool in one sentence
A Maya Python/Qt tool that procedurally generates customizable pipes and cables that route through picked objects, locators or mesh components, plug into surfaces along their normals, and stay live as anything they're attached to moves.

### 2. The chore it ends
It eliminates the manual, highly repetitive workflow of drawing CV curves, extruding geometry profiles, rigging endpoints, adjusting wire slack/sag, placing clamps and connectors, and fixing UVs by hand. Doing this manually takes 15–20 minutes per cable setup; this tool reduces the task to a few clicks and a few seconds.

### 3. The UI
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
- **Stretch (if time allows):** multi-wire bundles, noise variation.

### 6. The smallest version that still counts (MVP)
A Qt UI where selecting two objects generates a Sweep Mesh cable whose ends follow those objects live via `decomposeMatrix`, with working Radius and Sag sliders.

### 7. The riskiest part
Getting the cable to leave a picked vertex or face cleanly along its normal and stay attached while the mesh deforms — and keeping sag live alongside waypoints without the curve kinking. Moving to Sweep Mesh and `decomposeMatrix` removes the original risk (unstable history from extrusion and cluster rigs), so the remaining risk sits in the component-attachment math.
