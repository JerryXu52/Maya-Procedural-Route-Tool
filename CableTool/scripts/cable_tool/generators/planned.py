"""Modes that are listed in the dropdown but not built yet. They follow
the same interface as Cable / Pipe and Fence, so building one later only
means filling in _build_network and its settings."""

from cable_tool.generators.base import PlannedGenerator


class RoadGenerator(PlannedGenerator):
    mode = "road"
    label = "Road"
    noun = "road"
    summary = ("A flat swept ribbon along the route with lane-marking "
               "UVs. Planned next.")
