# Maya Procedural Route Tool

**Author:** Jianrui(Jerry) Xu

A Maya 2027 Python/Qt plugin that builds live geometry along a route of picked objects, locators or mesh components. **Cable / Pipe** mode is the midterm; **Fence** and **Road** modes are planned (see [section 11](#11-future-modes-fences-and-roads)).

**Contents**
- [Try it (current build)](#try-it-current-build)
- **The Pitch:** [1. One sentence](#1-the-tool-in-one-sentence) · [2. The chore](#2-the-chore-it-ends) · [3. The UI](#3-the-ui) · [4. Why it's advanced](#4-why-its-advanced) · [5. The three weeks](#5-the-three-weeks) · [6. MVP](#6-the-smallest-version-that-still-counts-mvp) · [7. Riskiest part](#7-the-riskiest-part)
- **Design Notes:** [8. Technical design](#8-technical-design) · [9. Plugin & packaging](#9-plugin--packaging) · [10. Lessons from my previous tool](#10-lessons-from-my-previous-tool) · [11. Future modes](#11-future-modes-fences-and-roads)
- **Feedback:** [12. Peer run: Tong Lin](#12-peer-run-tong-lin) · [13. Fixes from the peer run](#13-fixes-from-the-peer-run) · [14. Physics solver and wire styles](#14-physics-solver-and-wire-styles)

---

## Try it (current build)
Weeks 1–2 are built: plugin, Qt window, live Sweep Mesh cable, live sag and waypoints. Version 0.3.0 adds the fixes from the peer run ([section 13](#13-fixes-from-the-peer-run)) and the mode architecture behind the **Mode** dropdown (only `Cable / Pipe` is built; `Fence` and `Road` are listed greyed out). Version 0.4.0 replaces the cable's node network with a **physics solver node** and adds **multi-wire runs** with presets for utility lines and cyberpunk tangles ([section 14](#14-physics-solver-and-wire-styles)).

1. In Maya 2027, open **Windows › Settings/Preferences › Plug-in Manager**, click **Browse** and pick `CableTool/plug-ins/cableTool.py`.
2. Open **Cable Tool › Open Cable Tool** from the main menu bar, or run `cmds.cableTool()`.
3. Select two or more locators or meshes in order, press **Use Selection Order**, then **Generate Cable**. Move one: the cable follows.

Or open the demo — a row of utility poles and a cyberpunk alley; call `demo("peer")` afterwards for the peer run's cone, cube, sphere and cylinder: run `exec(open("tests/demo_scene.py").read())` in the Script Editor (use the full path), or launch Maya with it:
```
open -n -a /Applications/Autodesk/maya2026/Maya.app --args -command \
  "evalDeferred -lowestPriority \"python(\\\"exec(open('$PWD/tests/demo_scene.py').read())\\\")\""
```

Run the tests headlessly (tested with Maya 2026; replace `maya2026` with `maya2027` for 2027):
```
MAYAPY=/Applications/Autodesk/maya2026/Maya.app/Contents/bin/mayapy
$MAYAPY tests/test_cable_rig.py
QT_QPA_PLATFORM=offscreen $MAYAPY tests/test_ui.py
```
Picking anchors turns on Maya's *track selection order* preference, which waypoint ordering needs.

---

## The Pitch

### 1. The tool in one sentence
A Maya Python/Qt plugin that procedurally generates customizable pipes and cables that route through picked objects, locators or mesh components, plug into surfaces along their normals, and stay live as anything they're attached to moves.

### 2. The chore it ends
Drawing CV curves, extruding profiles, rigging endpoints, adjusting sag, placing clamps and fixing UVs by hand takes 15–20 minutes per cable. This tool does it in a few clicks.

### 3. The UI
Loading the plugin adds a **Cable Tool** menu to Maya's main menu bar (`Open Cable Tool`, `Reload`, `About`); the window can also be opened with the `cableTool` command or a shelf button.

One window, top to bottom:

| Area | Controls |
|---|---|
| **Mode** | Dropdown: `Cable / Pipe` (`Fence` and `Road` greyed out until built — see [section 11](#11-future-modes-fences-and-roads)) |
| **Route** | `Start` / `End` fields and an ordered `Waypoints` list, each with `Get Selected`; accepts transforms, locators, vertices or faces |
| **Preset** | `Single Pipe`, `Utility Line`, `Cyberpunk Tangle` + `Apply` |
| **Shape** (live) | Radius & Profile Sides · Length Detail · Twist (degrees) & Taper |
| **Path** (live) | Sag · Stiffness · Corner Smoothing · Smoothness · Drape Over Mesh Waypoints |
| **Wires** (live) | Wire Count (rebuilds by itself on release) · Spread · Spread In A Row · Slack Variation · Thickness Variation · Seed |
| **Ends** (live) | Attach Ends to Surface · Lead-out Length |
| **Hardware** | Clamp/bracket/connector mesh picker · `Spacing` (every N units) · `End Caps` |
| **UVs** | `Texture Repeat per Unit` |
| **Footer** (pinned) | `Generate Cable` · `Rebuild Current` · `Bake to Static Mesh` · `Clear All` · colour-coded status box |

- Settings scroll in **collapsible sections**; the footer never scrolls out of reach.
- Status messages are tagged `[OK]` / `[WARNING]` / `[ERROR]` and say how to fix a problem, not just that one exists.
- Every control has a tooltip; sliders have a comfortable range plus a typed field with a hard safety cap.
- Edit menu: `Reset Settings`, `Load Selected Cable`, `Delete Selected Cable`.

### 4. Why it's advanced
- **Sweep Mesh core:** built on Maya's Sweep Mesh (`sweep` plugin) instead of extrusion, so radius, profile, twist and taper stay editable with clean history.
- **Rig-free live following:** curve points are driven by `decomposeMatrix` nodes from the picked objects — no clusters or constraints to break.
- **Waypoint routing:** cables pass through any number of picks, so they can run along a wall and turn a corner.
- **Component attachment:** a picked vertex or face makes the cable leave along the surface normal, plugging into a port instead of floating near it.
- **Hardware along the length:** clamps, brackets or connectors instanced at a set spacing and riding the curve, plus end caps.
- **Clean length-wise UVs:** scaled by cable length, so tiling textures need no hand fixing.

### 5. The three weeks
**By Oct 13 — Plugin shell + Sweep foundation**
- Module folder laid out (see [section 9](#9-plugin--packaging)); `cableTool.py` plugin loads from the Plug-in Manager, registers the `cableTool` command and adds the **Cable Tool** menu.
- Qt UI layout built, opened from that menu.
- `cmds.loadPlugin('sweep')`; a Sweep Mesh along a curve between two selected objects.
- Radius, profile, twist and taper sliders wired to the sweep attributes.

**By Oct 20 — Live rig (core goal)**
- Curve end points driven by `decomposeMatrix`, so the cable follows its objects.
- Sag built into the node network so it stays live.
- Waypoints: extra picks, each driving its own curve point the same way.

**By Oct 26 — Components, hardware, UVs, polish**
- Component attachment along normals, staying attached when the mesh moves.
- Hardware instanced every N units, following the curve live; end caps.
- Length-wise UVs.
- Presets, bake, undo, edge-case error handling, UI polish.
- **Packaging:** `.mod` file, drag-and-drop installer, shelf icon, clean unload (closes the window, removes the menu, deregisters the command); test install and reload on a fresh Maya prefs folder.

**Stretch (in priority order)**
1. Multi-wire bundles and noise variation.
2. Basic Fence mode — posts plus swept rails, on flat ground.
3. Basic Road mode — flat swept ribbon with lane-marking UVs.

### 6. The smallest version that still counts (MVP)
A plugin that loads from Maya's Plug-in Manager and opens a Qt UI where selecting two objects generates a Sweep Mesh cable whose ends follow those objects live via `decomposeMatrix`, with working Radius and Sag sliders.

### 7. The riskiest part
Getting the cable to leave a picked vertex or face cleanly along its normal and stay attached while the mesh deforms, and keeping sag live alongside waypoints without the curve kinking. Sweep Mesh and `decomposeMatrix` remove my original risk (unstable history from extrusion and cluster rigs), so what remains is the component-attachment math.

---

## Design Notes

### 8. Technical design
**Code structure**
- **Shared route core:** start/end/waypoint picking (using `cmds.ls(orderedSelection=True)` so the cable follows click order).
- **One generator per mode** — `CableGenerator` now, `FenceGenerator` / `RoadGenerator` later — each with `build(route, settings)`, `update(settings)`, `bake()`, `delete()`.
- **Thin plugin, real code in a package:** the plugin file only registers commands and the menu; all tool logic lives in the `cable_tool` Python package (see [section 9](#9-plugin--packaging)).
- **One `DEFAULTS` table** feeds both the UI and `Reset Settings`.

**Live network** (see [section 14](#14-physics-solver-and-wire-styles))
- **Per wire:** anchor `worldMatrix` + mesh `outMesh` → `cableToolSolver` (a custom `MPxNode` in the plugin) → `nurbsCurve` → `sweepMeshCreator` → mesh. Maya re-solves only when an anchor or a setting changes.
- **Settings live on the cable group:** every setting is a keyable attribute on the group, wired into each wire's solver and Sweep Mesh, so it can also be changed or animated from the Channel Box. Twist is shown in degrees and converted to the whole turns Sweep Mesh expects. Only Wire Count changes the network itself, so the generator rebuilds the run in place when it changes (after a slider drag is released); it is kept out of the Channel Box.
- **Tube:** Sweep Mesh in *Distance* interpolation with a ring every tube diameter / `Length Detail`, so the tube is smooth along its length at any scene scale.

**Scene safety**
- **One undo chunk per action** (`try/finally`); live sliders open a chunk on press and close it on release, so a whole drag undoes with one Ctrl+Z.
- **Two-level error handling:** a custom error for limits I enforce, plus a catch-all at the UI layer, so Maya never sees an unhandled exception.
- **Input sanitising** of every UI value (empty, text, NaN, infinity) and selection checks that report ignored items and overlapping anchors.
- **Tagged nodes:** everything the tool creates carries a custom attribute (including which mode built it), so `Clear` deletes by tag, never by name. Each cable stores its settings on its group, enabling `Load Selected Cable`.
- One shared shader per cable type, and one top-level group for all output.

### 9. Plugin & packaging
The tool ships as a **Maya module** containing a **Python plugin**, so artists install it once and load it from **Windows › Settings/Preferences › Plug-in Manager** — no Script Editor or command line.

**Folder layout** (✅ = built, ⏳ = week 3)
```
CableTool/
├── CableTool.mod            ✅ tells Maya where the module lives
├── install.py               ⏳ drag-and-drop installer
├── plug-ins/
│   └── cableTool.py         ✅ plugin entry point (thin)
├── scripts/
│   └── cable_tool/          ✅ the real code, as a Python package
│       ├── __init__.py
│       ├── config.py        ✅ DEFAULTS, ranges, sanitising, errors
│       ├── ui.py            ✅ Qt window
│       ├── route.py         ✅ shared route core
│       ├── solver.py        ✅ cableToolSolver node: rest shape + rope physics
│       ├── nodes.py         ✅ tagging, cleanup, undo, sweep dependency
│       ├── dev.py           ✅ Reload for development
│       └── generators/
│           ├── __init__.py  ✅ mode registry (dropdown order)
│           ├── base.py      ✅ shared generator: group, settings, load, rebuild, delete
│           ├── cable.py     ✅ CableGenerator
│           └── planned.py   ✅ Fence / Road placeholders
└── icons/
    └── cableTool.png        ⏳ menu / shelf icon
tests/
├── test_cable_rig.py        ✅ headless rig and physics tests (mayapy)
├── test_ui.py               ✅ headless window smoke test
└── demo_scene.py            ✅ utility poles, cyberpunk alley, peer-run scene
```

**Plugin steps**
1. **Entry point:** `plug-ins/cableTool.py` declares `maya_useNewAPI()` (Python API 2.0) and defines `initializePlugin` / `uninitializePlugin`, setting vendor, version and Maya 2027 as the required API version.
2. **Command:** register a `cableTool` command (`MPxCommand`) that opens or raises the window, so it works from the menu, a shelf button or a script.
3. **Menu:** on load, add a **Cable Tool** menu to Maya's main menu bar (`Open Cable Tool`, `Reload`, `About`).
4. **Dependencies:** on load, call `cmds.loadPlugin('sweep', quiet=True)`; if it fails, the plugin still loads but the window shows a clear `[ERROR]` instead of crashing.
5. **Clean unload:** `uninitializePlugin` closes the window, removes the menu and deregisters the command and the solver node, so unload → load works without restarting Maya. Maya refuses to unload a plugin while its nodes exist (including in the undo queue), so start a new scene first.
6. **Module file:** `CableTool.mod` adds `plug-ins/`, `scripts/` and `icons/` to Maya's paths automatically.
7. **Installer:** dragging `install.py` into the viewport (`onMayaDroppedPythonFile`) writes the `.mod` file into the user's `modules` folder and loads the plugin; tick **Auto load** in the Plug-in Manager to keep it on.
8. **Test:** install on a clean Maya prefs folder; check load, unload, reload, and that the tool's nodes still open correctly in a scene saved before reloading.

**Development loop:** a dev-only script unloads the plugin, reloads the `cable_tool` modules and loads it again in a running Maya, so I can iterate without restarting.

### 10. Lessons from my previous tool
In September I built `CableHoseRigTool.py`, a one-shot generator: it computed every point in Python and built meshes with no history, so any change meant clearing and regenerating. This midterm turns that idea into a **live, node-based** tool.

| Keep | Drop | Fix |
|---|---|---|
| Pinned footer, collapsible sections, colour-coded status box | Hand-built coordinate frames (Sweep Mesh orients the tube) | Selection order not guaranteed → `orderedSelection` |
| Actionable messages, tooltips, safety-capped fields | Extrude / cylinder fallback with history off | Generating twice left empty groups; cleanup by name prefix → tag-based cleanup |
| Undo chunks, two-level error handling, input sanitising | Collision relaxation and spatial hashing (too slow for a live rig; sunflower packing may return for bundles) | Defaults written twice → one `DEFAULTS` table |
| Sag scaled by span length; catenary shape | Assignment-only features (Beta mode, Length Stagger, Slack Variation) | Clear was all-or-nothing → per-cable Load / Delete |
| Multi-pick spans → grown into waypoint routing | | |
| Command-port remote launcher → dev-only script that reloads the plugin in a running Maya | | |

### 11. Future modes: fences and roads
Cables, fences and roads are all **curve-driven geometry**, so the mode architecture in [section 8](#8-technical-design) lets one tool build all three, reusing most of the cable work:

| Building block | Cable / Pipe | Fence | Road |
|---|---|---|---|
| Route, waypoints, live curve | ✅ | ✅ | ✅ |
| Sweep Mesh profile | round tube | thin box rails | flat, wide surface |
| Hardware every N units | clamps, brackets | **fence posts** | lamp posts, markers |
| Length-wise UVs | ribbed / striped | wood grain | **lane markings** |
| Sag | ✅ | wire fences only | ❌ |
| **Hard part** | component attachment | vertical posts on uneven ground; gaps and gates | terrain conforming, banking, intersections |

**Plan**
1. **Midterm:** mode architecture and dropdown, with only `Cable / Pipe` working. ✅ Built in 0.3.0: `generators.GENERATORS` lists every mode; the dropdown, its panels and the Generate button are built from it, and Load / Delete Selected find a build's generator from the mode stored on its group. A mode only declares its settings (`sections`) and builds its own node network; a planned mode refuses to build with a clear message.
2. **Stretch:** basic Fence, then basic Road (see [section 5](#5-the-three-weeks)).
3. **After the midterm:** terrain conforming, gates, road intersections.

---

## Feedback

### 12. Peer run: Tong Lin
1. **What I did:** I loaded the plug-in in Maya 2026, picked a cone, a cube, a sphere and a cylinder in order as start, waypoints and end, generated a few cables, and then changed the Twist and Smoothness settings and added more waypoints.
2. **What happened:** The cables were generated and followed the objects, but after changing Twist the tube became kinked and twisted into separate segments instead of a smooth cable, and where the cable meets the start and end objects the tube narrows to a sharp point and the cables cross each other.
3. **What confused me or broke:** Smoothness didn't update live like the other settings (I had to press Rebuild to see it), and when I added several waypoints the cable bent into sharp, tight corners around them instead of a smooth turn.

### 13. Fixes from the peer run
| Peer-run problem | Cause | Fix (0.3.0) |
|---|---|---|
| Twist kinked the tube into separate segments | Sweep Mesh counts Twist in whole turns, but the tool passed degrees, so 90 became 90 full turns | The slider stays in degrees and a node divides by 360 before Sweep Mesh |
| The tube narrowed to a point at the start/end objects and the cables crossed | Every cable ended at the object's pivot, inside it, so all cables met at one point (and the over-twisted ends pinched) | Mesh ends sit on the surface point facing the next anchor and leave along its normal (`Attach Ends to Surface`, `Lead-out Length`), and the spline keeps following the normal past the lead-out point instead of folding back toward the next anchor (live check in Maya: tightest bend off the demo cone went from 0.13 to 0.44 units, wider than the tube); twist fix above |
| Smoothness didn't update live | It changes the curve's point count, so it needed a manual Rebuild | Changing it rebuilds the cable in place, once a slider drag is released |
| Several waypoints made sharp, tight corners | Straight lines between waypoints, and each span's sag met the next in a V | A Catmull-Rom spline through the waypoints (`Corner Smoothing`) and sag that eases out level at waypoints |

The live re-test in Maya 2026 found more, all fixed in 0.4.0: the tube was a chain of creased straight pieces (Sweep Mesh's default ring placement), the cable kinked or folded where it left a surface, and cables routed through a mesh waypoint ran through its middle and then cut through its walls. Section 14 describes the fix.

### 14. Physics solver and wire styles
A node network can follow anchors live, but it can't make a cable *rest on* something. 0.4.0 moves the cable's shape into **`cableToolSolver`**, a Python API 2.0 node registered by the plugin, which works in two stages every time an input changes:

1. **Rest shape (analytic).** Mesh ends sit on the surface point facing the next anchor and leave between the surface normal and that anchor. Mesh waypoints are draped over (the top of the surface, lifted by the tube's radius). Between path points the cable follows a Catmull-Rom spline blended with straight lines (`Corner Smoothing`) and sags by a catenary weight × `Sag` × the span's **horizontal** length, so a vertical run hangs straight.
2. **Relaxation (rope physics).** The rest shape becomes a particle chain (a point every tube diameter, evenly spaced) whose segment lengths are fixed. Verlet steps add gravity; each step projects the length constraints, a bending constraint (`Stiffness`) that also straightens next to pinned points, and collision with every mesh the cable is attached to. Path points and a straight `Lead-out Length` off each mesh end are pinned. The last result warm-starts the next solve, so dragging needs fewer steps.

Tuned offline on a test cable: damping 0.3, gravity 0.003 segments/step, 8 constraint passes keep a cable within ~1% of its length with its tightest bend at several radii, in ~50 ms from cold.

**Several wires per run.** `Wire Count` builds one solver, curve and Sweep Mesh per wire. Each wire draws from its own random stream (`Seed` + wire index, so the same seed always gives the same wires):
- `Spread In A Row` on — wires sit side by side across `Spread` and stay parallel, like power lines on a crossarm.
- Off — each wire lands at a random spot within `Spread` at every anchor, so the wires cross and tangle.
- `Slack Variation` and `Thickness Variation` give each wire its own sag and radius (a single cable is never varied).

**Presets:** `Single Pipe` (one stiff tube), `Utility Line` (4 parallel, nearly taut, limp wires) and `Cyberpunk Tangle` (14 clustered wires, very uneven slack and thickness).

**Measured in Maya 2026** (peer-run scene): no cable passes through any object, lengths stay within ~1.5%, and tightest bends are 1.7–4.8 tube radii. The showcase (44 wires) builds in ~3 s; moving one crossarm re-solves its wires in ~0.16 s.
