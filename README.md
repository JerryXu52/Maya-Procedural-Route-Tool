# Procedural Pipe & Cable Generator for Maya

**Course:** Midterm Tool Pitch  
**Author:** [Your Name]  

---

### 1. The tool in one sentence
A Maya Python/Qt tool that procedurally generates customizable pipes and cable bundles between selected objects or components and dynamically rigs them to update seamlessly as the objects move.

### 2. The chore it ends
It eliminates the manual, highly repetitive workflow of drawing CV curves, extruding geometry profiles, creating clusters/constraints for endpoints, and adjusting wire slack/sag by hand. Doing this manually takes 15–20 minutes per cable setup; this tool reduces the task to two clicks and a few seconds.

### 3. The UI
- **Object Selection:** `Source Object` / `Target Object` input fields with `Get Selected` buttons.
- **Presets Dropdown:** `Single Industrial Pipe`, `Multi-Wire Bundle`, `Corrugated Hose`.
- **Parameters Sliders:**
  - Cable Radius & Subdivisions
  - Sag / Slack Amount
  - Bundle Count & Radius
  - Noise / Twist Variations
- **Checkboxes:** `Enable Dynamic Rigging`, `Assign Default Shader`.
- **Action Buttons:** `Generate Cable`, `Bake to Static Mesh`, `Reset Settings`.

### 4. Why it's advanced
- **Live Dynamic Rigging:** Cables live-deform in real-time as attached objects move in the scene.
- **Parametric UI Control:** Tweak sag, thickness, and profile settings on the fly without deleting or recreating nodes.
- **Non-Destructive Workflow:** Offers a one-click bake option to freeze procedural setups into clean, lightweight static geometry.
- **Robust Execution:** Fully integrated into Maya's Undo/Redo stack with error-handling popups that prevent crashes when selections are invalid.

### 5. The three weeks
- **By Oct 13:** PySide/Qt UI layout built; basic Python script generating a simple 2-point curve and extruded pipe between two selected objects.
- **By Oct 20:** Endpoint constraint system fully integrated (locators/clusters for dynamic object tracking) and mathematical curve sag controls linked to UI sliders.
- **By Oct 26:** Multi-cable bundle generation, presets system, Maya Undo queue integration, edge-case error handling, and UI polishing.

### 6. The smallest version that still counts (MVP)
A functional Qt UI where selecting two objects generates a procedural pipe with working Radius and Sag sliders, even if the dynamic live-following rig fails and requires manual re-baking.

### 7. The riskiest part
Maintaining clean Maya dependency graph history so that live parameter updates (such as sag or radius) remain stable and responsive after dynamic constraints and cluster rigs have been built into the scene.
