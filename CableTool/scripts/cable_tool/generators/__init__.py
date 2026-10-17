from cable_tool.generators.cable import CableGenerator

# Mode name -> generator class. Fence and Road register here later.
GENERATORS = {
    CableGenerator.mode: CableGenerator,
}
