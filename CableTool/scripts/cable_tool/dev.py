"""Development helpers. Cable Tool > Reload runs reload_tool()."""

import sys


def reload_tool():
    """Close the window, drop every cable_tool module so the next import
    reads the files fresh, then reopen the window. Cables already in the
    scene keep working: they are plain Maya nodes."""
    from cable_tool import ui
    ui.close(keep_host=True)  # stays docked where it was
    for name in [m for m in sys.modules
                 if m == "cable_tool" or m.startswith("cable_tool.")]:
        del sys.modules[name]
    from cable_tool import ui as fresh_ui
    fresh_ui.show()
    print("[CableTool] Reloaded.")


def interface_strings():
    """Every English string the interface can show: tr() and N_() literals
    in the package, plus the data-driven ones (setting labels and tips,
    mode names, sections, presets). The locale files must cover these."""
    import ast
    import os

    from cable_tool import config, generators, ui

    found = []

    def add(text):
        if text and text not in found:
            found.append(text)

    package = os.path.dirname(os.path.abspath(__file__))
    for folder, _dirs, files in os.walk(package):
        for name in sorted(files):
            if not name.endswith(".py"):
                continue
            with open(os.path.join(folder, name)) as handle:
                tree = ast.parse(handle.read())
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Name)
                        and node.func.id in ("tr", "N_") and node.args
                        and isinstance(node.args[0], ast.Constant)
                        and isinstance(node.args[0].value, str)):
                    add(node.args[0].value)

    add(config.TOOL_NAME)
    for tag in ui.STATUS_TAGS.values():
        add(tag)
    for spec in config.DEFAULTS.values():
        add(spec["label"])
        add(spec["tip"])
        for choice in spec.get("choices", ()):
            add(choice)
    for generator in generators.GENERATORS:
        for text in (generator.label, generator.summary, generator.noun,
                     generator.noun.capitalize()):
            add(text)
        for title, _keys in generator.sections:
            add(title)
        for preset, _values in generator.presets:
            add(preset)
        for _key, label, tip, _section in generator.extras:
            add(label)
            add(tip)
    return found
