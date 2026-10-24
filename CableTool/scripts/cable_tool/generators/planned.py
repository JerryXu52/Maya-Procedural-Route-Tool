"""Modes that are listed in the dropdown but not built yet. They follow
the same interface as Cable / Pipe, so building one later only means
filling in _build_network and its settings (see README section 11)."""

from cable_tool.generators.base import PlannedGenerator


class FenceGenerator(PlannedGenerator):
    mode = "fence"
    label = "Fence"
    noun = "fence"
    summary = ("Posts every N units along the route, joined by swept "
               "rails. Planned after the midterm's Cable / Pipe mode.")


class RoadGenerator(PlannedGenerator):
    mode = "road"
    label = "Road"
    noun = "road"
    summary = ("A flat swept ribbon along the route with lane-marking "
               "UVs. Planned after Fence mode.")
