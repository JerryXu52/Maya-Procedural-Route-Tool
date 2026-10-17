"""Development helpers. Cable Tool > Reload runs reload_tool()."""

import sys


def reload_tool():
    """Close the window, drop every cable_tool module so the next import
    reads the files fresh, then reopen the window. Cables already in the
    scene keep working: they are plain Maya nodes."""
    from cable_tool import ui
    ui.close()
    for name in [m for m in sys.modules
                 if m == "cable_tool" or m.startswith("cable_tool.")]:
        del sys.modules[name]
    from cable_tool import ui as fresh_ui
    fresh_ui.show()
    print("[CableTool] Reloaded.")
