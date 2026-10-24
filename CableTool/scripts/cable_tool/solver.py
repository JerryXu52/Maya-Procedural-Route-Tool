"""The cable solver: a Maya node that turns a route into the curve a real
cable would hang in.

    anchor world matrices + meshes, settings  ->  cableToolSolver  ->  curve

It works in two stages, every time an input changes:

1. Rest shape (analytic). The path runs start -> waypoints -> end. A mesh
   end sits on the surface point facing its neighbour and leaves in its
   exit direction (between the surface normal and the neighbour); a mesh
   waypoint is draped over (the top of its surface). Between path points
   the cable follows a Catmull-Rom spline (blended with straight lines by
   Corner Smoothing) and sags by a catenary weight times Sag times the
   span's horizontal length.

2. Relaxation (physical). The rest shape becomes a chain of particles
   whose segment lengths are fixed (the cable can't stretch). Verlet
   steps add gravity, keep the lengths, resist bending (Stiffness) and
   push particles out of every mesh the cable is attached to, so a cable
   draped over a box wraps its edges instead of cutting through it. The
   path points (and the first particle off each mesh end, which holds
   the exit direction) are pinned.

The particles become the CVs of the output curve. The last result is
kept and used as the next starting point, so dragging an anchor only
needs a few steps.
"""

import math

import numpy as np

import maya.api.OpenMaya as om

from cable_tool.config import (CATENARY_TENSION, DRAPE_PROBE_HEIGHT, EPSILON,
                               EXIT_TANGENT, LEAD_TANGENT)

NODE_NAME = "cableToolSolver"
# Maya reserves 0x00000-0x7ffff for local, unpublished plugins.
NODE_ID = om.MTypeId(0x0007F0C1)

POINTS_PER_SAMPLE = 3  # particles per span >= Smoothness * this
DIAMETERS_PER_POINT = 1.0  # ... and at least one per tube diameter
MAX_PER_SPAN = 80      # cap per span, for speed with many wires
MAX_POINTS = 600       # cap per wire
# Tuned offline (a 12-unit cable leaving two ports): these keep the
# cable within 1% of its length and its tightest bend at 6-8 radii, in
# ~50 ms from cold. Faster settling (more gravity, less damping) let the
# chain build up speed and stretch ~9%, which also sharpened the bends.
COLD_STEPS = 120       # relaxation steps from the rest shape
WARM_STEPS = 40        # ... from the previous result
ITERATIONS = 8         # constraint passes per step
DAMPING = 0.3          # velocity kept per step
GRAVITY = 0.003        # per step, as a fraction of a segment length
COLLISION_MARGIN = 1.2  # keep particles this many radii off surfaces


# -------------------------------------------------------------------------
# Rest shape (pure math, testable without Maya)
# -------------------------------------------------------------------------
def catenary_weight(t, tension=CATENARY_TENSION):
    """0 at both ends, 1 at mid-span: the shape of a hanging chain."""
    if tension < EPSILON:
        return 4.0 * t * (1.0 - t)
    return ((math.cosh(tension) - math.cosh(tension * (2.0 * t - 1.0)))
            / (math.cosh(tension) - 1.0))


def _eased(t, ease_start, ease_end):
    weight = catenary_weight(t)
    if ease_start:
        weight *= t * (2.0 - t)
    if ease_end:
        weight *= 1.0 - t * t
    return weight


def sag_weight(t, ease_start=False, ease_end=False):
    """Catenary drop at t, peaking at 1. An eased end leaves its point
    level instead of at the chain's angle, so where two spans meet at a
    waypoint the cable turns smoothly instead of forming a V."""
    if not (ease_start or ease_end):
        return catenary_weight(t)
    peak = max(_eased(k / 200.0, ease_start, ease_end) for k in range(201))
    return _eased(t, ease_start, ease_end) / peak


def hermite(p0, p1, m0, m1, t):
    """Point at t on the cubic from p0 to p1 with tangents m0, m1."""
    t2, t3 = t * t, t * t * t
    return ((2 * t3 - 3 * t2 + 1) * p0 + (t3 - 2 * t2 + t) * m0
            + (-2 * t3 + 3 * t2) * p1 + (t3 - t2) * m1)


def sample_parameters(samples):
    """Interior t values for one span, ends excluded, evenly spaced: a
    simulated chain wants segments of similar length. (Packing them near
    the ends made segments 100x shorter than their neighbours, and the
    chain buckled into waves.)"""
    return [float(k) / (samples + 1) for k in range(1, samples + 1)]


def _unit(v):
    length = np.linalg.norm(v)
    return v / length if length > EPSILON else v * 0.0


def rest_shape(points, exits, eases, settings):
    """Particles along the path before physics.

    points: (n, 3) path points. exits: per point, a unit exit direction
    (mesh ends) or None. eases: per point, whether the sag levels out
    there. Returns (particles, pinned index list)."""
    points = np.asarray(points, dtype=float)
    count = len(points)
    # Catmull-Rom tangents, mirrored past the ends. A mesh end uses its
    # exit direction instead.
    tangents = []
    for i in range(count):
        before = points[i - 1] if i > 0 else 2 * points[0] - points[1]
        after = (points[i + 1] if i + 1 < count
                 else 2 * points[-1] - points[-2])
        tangents.append(0.5 * (after - before))
    for i, exit_dir in ((0, exits[0]), (count - 1, exits[-1])):
        if exit_dir is None:
            continue
        neighbour = points[1] if i == 0 else points[-2]
        span = np.linalg.norm(neighbour - points[i])
        size = EXIT_TANGENT * span + LEAD_TANGENT * settings["leadOut"]
        tangents[i] = (exit_dir if i == 0 else -exit_dir) * size

    # Fine enough to follow contact: a point at least every tube
    # diameter, so a cable can wrap a support instead of folding over it.
    spacing = 2.0 * settings["radius"] * DIAMETERS_PER_POINT
    lengths = [np.linalg.norm(points[s + 1] - points[s]) * (1.0 + settings["sag"])
               for s in range(count - 1)]
    floor = int(settings["samples"]) * POINTS_PER_SAMPLE
    per_span = [max(floor, min(MAX_PER_SPAN, int(length / spacing)))
                for length in lengths]
    total = sum(per_span)
    if total > MAX_POINTS:
        per_span = [max(floor, n * MAX_POINTS // total) for n in per_span]
    smoothing = settings["smoothing"]
    particles, pinned = [], []
    for s in range(count - 1):
        a, b = points[s], points[s + 1]
        params = sample_parameters(per_span[s])
        pinned.append(len(particles))
        particles.append(a)
        level = np.array([b[0] - a[0], 0.0, b[2] - a[2]])
        drop = settings["sag"] * np.linalg.norm(level)
        for t in params:
            straight = a + (b - a) * t
            curved = hermite(a, b, tangents[s], tangents[s + 1], t)
            point = straight + (curved - straight) * smoothing
            point[1] -= drop * sag_weight(t, eases[s], eases[s + 1])
            particles.append(point)
    pinned.append(len(particles))
    particles.append(points[-1])
    return np.array(particles), pinned


# -------------------------------------------------------------------------
# Relaxation
# -------------------------------------------------------------------------
class Collider(object):
    """Closest point and normal on a mesh, in world space."""

    def __init__(self, mesh_obj, matrix):
        self.matrix = matrix
        self.inverse = matrix.inverse()
        self.intersector = om.MMeshIntersector()
        self.intersector.create(mesh_obj, om.MMatrix())
        # World-space bounds, from the points: mesh *data* (what a node
        # receives) has no boundingBox of its own.
        local = np.array([(p.x, p.y, p.z, 1.0) for p in
                          om.MFnMesh(mesh_obj).getPoints()])
        world = local.dot(np.array(matrix).reshape(4, 4))[:, :3]
        self.low = world.min(axis=0)
        self.high = world.max(axis=0)

    def closest(self, point):
        local = om.MPoint(*point) * self.inverse
        hit = self.intersector.getClosestPoint(local)
        world = om.MPoint(hit.point) * self.matrix
        normal = om.MVector(hit.normal).transformAsNormal(self.matrix)
        normal.normalize()
        return (np.array([world.x, world.y, world.z]),
                np.array([normal.x, normal.y, normal.z]))

    def push_out(self, particles, free, clearance):
        """Move free particles that are closer than clearance to (or
        inside) the surface out along the normal."""
        near = np.all((particles > self.low - clearance)
                      & (particles < self.high + clearance), axis=1) & free
        for i in np.nonzero(near)[0]:
            point, normal = self.closest(particles[i])
            depth = np.dot(particles[i] - point, normal)
            if depth < clearance:
                particles[i] += normal * (clearance - depth)


def _project_pairs(x, inv_mass, first, second, rest):
    """Move each (first[k], second[k]) pair toward distance rest[k]. Pairs
    must not share particles, so they can all move at once."""
    delta = x[second] - x[first]
    length = np.linalg.norm(delta, axis=1)
    length = np.maximum(length, EPSILON)
    error = (length - rest) / length
    total = inv_mass[first] + inv_mass[second]
    total = np.where(total > 0.0, total, 1.0)
    move = delta * (error / total)[:, None]
    x[first] += move * inv_mass[first][:, None]
    x[second] -= move * inv_mass[second][:, None]


def _bend(x, inv_mass, middle, stiffness):
    """Straighten each triplet (middle - 1, middle, middle + 1): a bend
    resists in proportion to how sharp it is.

    The bend is d = middle - midpoint of its neighbours. Moving the middle
    by -d and each neighbour by +d/2 removes it; the moves are shared by
    inverse mass, so a pinned middle (a waypoint, the end of a lead-out)
    straightens the cable by moving its neighbours instead. That is what
    rounds the kink where a cable leaves a fixed point. Middles must be at
    least 3 apart so no two triplets share a particle."""
    before, after = middle - 1, middle + 1
    bend = x[middle] - 0.5 * (x[before] + x[after])
    weight = (inv_mass[middle] + 0.25 * inv_mass[before]
              + 0.25 * inv_mass[after])
    weight = np.where(weight > 0.0, weight, 1.0)
    step = bend * (stiffness / weight)[:, None]
    x[middle] -= step * inv_mass[middle][:, None]
    x[before] += 0.5 * step * inv_mass[before][:, None]
    x[after] += 0.5 * step * inv_mass[after][:, None]


def relax(rest, pinned_positions, colliders, settings, start=None,
          steps=COLD_STEPS):
    """Settle the particle chain under gravity.

    rest: (n, 3) rest shape, which sets every segment's length.
    pinned_positions: {index: position} held fixed. start: positions to
    start from (the previous result) instead of the rest shape."""
    x = np.array(start if start is not None else rest, dtype=float)
    count = len(x)
    seg = np.linalg.norm(np.diff(rest, axis=0), axis=1)
    inv_mass = np.ones(count)
    pins = np.array(sorted(pinned_positions), dtype=int)
    pin_at = np.array([pinned_positions[i] for i in pins])
    inv_mass[pins] = 0.0
    free = inv_mass > 0.0
    x[pins] = pin_at

    stiffness = settings["stiffness"]
    # A little extra: collision moves the particles, and the smooth curve
    # through them can still clip a corner between two of them.
    clearance = settings["radius"] * COLLISION_MARGIN
    gravity = GRAVITY * float(np.mean(seg)) if len(seg) else 0.0
    index = np.arange(count - 1)
    stretch = [index[index % 2 == parity] for parity in (0, 1)]
    middles = np.arange(1, count - 1)
    bend = [middles[middles % 3 == group] for group in (0, 1, 2)]

    previous = x.copy()
    for _step in range(steps):
        velocity = (x - previous) * DAMPING
        previous = x.copy()
        x[free] += velocity[free]
        x[free, 1] -= gravity
        for _ in range(ITERATIONS):
            for pairs in stretch:
                _project_pairs(x, inv_mass, pairs, pairs + 1, seg[pairs])
            if stiffness > 0.0:
                for middle in bend:
                    _bend(x, inv_mass, middle, stiffness)
        for collider in colliders:
            collider.push_out(x, free, clearance)
        x[pins] = pin_at
    return x


# -------------------------------------------------------------------------
# Several wires per run
# -------------------------------------------------------------------------
OFFSET_DRAWS = 64  # random offsets drawn per wire (one per path point)


def _random(settings):
    """This wire's own random stream: the same Seed and wire index always
    give the same wire, whatever else changes."""
    return np.random.default_rng([max(int(settings["seed"]), 0),
                                  max(int(settings["wireIndex"]), 0)])


def wire_variation(settings):
    """This wire's sag and radius after Slack / Thickness Variation. A
    single cable is never varied: its Radius and Sag are exact."""
    if int(settings["wireCount"]) <= 1:
        return {"sag": settings["sag"], "radius": settings["radius"]}
    rng = _random(settings)
    slack, thickness = rng.uniform(-0.5, 1.0), rng.uniform(-0.5, 0.5)
    return {
        "sag": settings["sag"] * max(0.0, 1.0 + settings["slackVariation"]
                                     * slack),
        "radius": settings["radius"] * max(0.1, 1.0 + settings[
            "thicknessVariation"] * 2.0 * thickness),
    }


def wire_offsets(pivots, settings):
    """Where this wire meets each anchor, relative to the anchor's pivot,
    across the direction of travel. In a row (a pole's crossarm) the
    wires sit side by side, evenly spaced over Spread, and stay parallel;
    in a cluster each wire lands at a random spot within Spread at every
    anchor, so the wires cross and tangle."""
    count = len(pivots)
    wires = max(int(settings["wireCount"]), 1)
    spread = settings["spread"]
    zeros = [np.zeros(3) for _ in pivots]
    if wires == 1 or spread <= 0.0:
        return zeros
    up = np.array([0.0, 1.0, 0.0])
    rng = _random(settings)
    rng.uniform(size=2)  # skip the draws wire_variation uses
    angles = rng.uniform(0.0, 2.0 * math.pi, OFFSET_DRAWS)
    radii = np.sqrt(rng.uniform(0.0, 1.0, OFFSET_DRAWS)) * 0.5 * spread
    across = (int(settings["wireIndex"]) / float(wires - 1) - 0.5) * spread

    offsets = []
    for i, pivot in enumerate(pivots):
        travel = _unit(pivots[min(i + 1, count - 1)]
                       - pivots[max(i - 1, 0)])
        side = _unit(np.cross(travel, up))
        if not side.any():  # a vertical run: any horizontal side will do
            side = np.array([1.0, 0.0, 0.0])
        lift = np.cross(side, travel)
        if settings["spreadRow"]:
            offsets.append(side * across)
        else:
            k = i % OFFSET_DRAWS
            offsets.append(radii[k] * (side * math.cos(angles[k])
                                       + lift * math.sin(angles[k])))
    return offsets


# -------------------------------------------------------------------------
# The node
# -------------------------------------------------------------------------
def _translation(matrix):
    return np.array([matrix[12], matrix[13], matrix[14]])


class CableSolverNode(om.MPxNode):
    """Inputs: anchor[i].anchorMatrix / anchorMesh, the cable's settings
    and wireIndex (which wire of the run this node solves).
    Outputs: outCurve, the wire's curve in world space, and outRadius,
    its radius after Thickness Variation."""

    SETTINGS = ("radius", "sag", "smoothing", "samples", "attach", "leadOut",
                "drape", "stiffness", "wireCount", "spread", "spreadRow",
                "slackVariation", "thicknessVariation", "seed")
    BOOLS = ("attach", "drape", "spreadRow")
    INTS = ("samples", "wireCount", "seed", "wireIndex")

    def __init__(self):
        super(CableSolverNode, self).__init__()
        self._last = None  # previous particles, to warm-start from

    @staticmethod
    def creator():
        return CableSolverNode()

    @classmethod
    def initialize(cls):
        num = om.MFnNumericAttribute()
        typed = om.MFnTypedAttribute()
        matrix = om.MFnMatrixAttribute()
        compound = om.MFnCompoundAttribute()

        cls.anchorMatrix = matrix.create("anchorMatrix", "am")
        cls.anchorMesh = typed.create("anchorMesh", "ams",
                                      om.MFnData.kMesh)
        cls.anchor = compound.create("anchor", "an")
        compound.addChild(cls.anchorMatrix)
        compound.addChild(cls.anchorMesh)
        compound.array = True
        cls.addAttribute(cls.anchor)

        for name in cls.SETTINGS + ("wireIndex",):
            if name in cls.BOOLS:
                kind = om.MFnNumericData.kBoolean
            elif name in cls.INTS:
                kind = om.MFnNumericData.kInt
            else:
                kind = om.MFnNumericData.kDouble
            attr = num.create(name, name, kind, 0)
            num.keyable = True
            setattr(cls, name, attr)
            cls.addAttribute(attr)

        cls.outCurve = typed.create("outCurve", "oc",
                                    om.MFnData.kNurbsCurve)
        typed.writable = False
        typed.storable = False
        cls.addAttribute(cls.outCurve)
        cls.outRadius = num.create("outRadius", "or",
                                   om.MFnNumericData.kDouble, 0.1)
        num.writable = False
        num.storable = False
        cls.addAttribute(cls.outRadius)

        for name in ("anchor", "wireIndex") + cls.SETTINGS:
            cls.attributeAffects(getattr(cls, name), cls.outCurve)
        for name in ("radius", "thicknessVariation", "seed", "wireIndex"):
            cls.attributeAffects(getattr(cls, name), cls.outRadius)

    # -- compute ----------------------------------------------------------
    def compute(self, plug, data):
        if plug == self.outRadius:
            settings = self._read_settings(data)
            data.outputValue(self.outRadius).setDouble(
                wire_variation(settings)["radius"])
            data.setClean(plug)
            return None
        if plug != self.outCurve:
            return None
        settings = self._read_settings(data)
        settings.update(wire_variation(settings))
        anchors = self._read_anchors(data)
        out = data.outputValue(self.outCurve)
        if len(anchors) < 2:
            out.setMObject(om.MObject.kNullObj)
            data.setClean(plug)
            return None

        points, exits, eases, colliders = self._path(anchors, settings)
        rest, pinned = rest_shape(points, exits, eases, settings)
        pins = {i: rest[i] for i in pinned}
        path_points = set(pinned)
        # Hold each mesh end straight along its exit direction for the
        # Lead-out Length (at least one segment), like the stiff sleeve
        # where a real cable leaves its connector.
        last = len(rest) - 1
        for end, step, exit_dir in ((0, 1, exits[0]), (last, -1, exits[-1])):
            if exit_dir is None:
                continue
            reach, index = 0.0, end
            while reach < settings["leadOut"] or index == end:
                following = index + step
                if following in path_points:
                    break  # never move the next path point
                reach += np.linalg.norm(rest[following] - rest[index])
                index = following
                pins[index] = rest[end] + exit_dir * reach

        warm = self._last is not None and len(self._last) == len(rest)
        particles = relax(rest, pins, colliders, settings,
                          start=self._last if warm else None,
                          steps=WARM_STEPS if warm else COLD_STEPS)
        self._last = particles
        self._rest_len = float(np.sum(np.linalg.norm(np.diff(rest, axis=0),
                                                     axis=1)))

        out.setMObject(self._curve(particles))
        data.setClean(plug)
        return None

    def _read_settings(self, data):
        values = {}
        for name in self.SETTINGS + ("wireIndex",):
            handle = data.inputValue(getattr(self, name))
            if name in self.BOOLS:
                values[name] = handle.asBool()
            elif name in self.INTS:
                values[name] = handle.asInt()
            else:
                values[name] = handle.asDouble()
        return values

    def _read_anchors(self, data):
        handle = data.inputArrayValue(self.anchor)
        anchors = []
        for _ in range(len(handle)):
            element = handle.inputValue()
            matrix = element.child(self.anchorMatrix).asMatrix()
            mesh = element.child(self.anchorMesh).asMesh()
            anchors.append((handle.elementLogicalIndex(), matrix,
                            None if mesh.isNull() else mesh))
            if not handle.next():
                break
        anchors.sort(key=lambda item: item[0])
        return [(matrix, mesh) for _index, matrix, mesh in anchors]

    def _path(self, anchors, settings):
        pivots = [_translation(matrix) for matrix, _mesh in anchors]
        offsets = wire_offsets(pivots, settings)
        colliders = [Collider(mesh, matrix) if mesh is not None else None
                     for matrix, mesh in anchors]
        points = [p + o for p, o in zip(pivots, offsets)]
        exits = [None] * len(anchors)
        eases = [True] * len(anchors)
        up = np.array([0.0, 1.0, 0.0])

        for i, neighbour in ((0, 1), (len(anchors) - 1, len(anchors) - 2)):
            collider = colliders[i]
            if collider is None or not settings["attach"]:
                eases[i] = False  # a free end hangs at the chain's angle
                continue
            # The surface point facing the neighbour, shifted by this
            # wire's offset, so a run's wires spread over the surface.
            target = pivots[neighbour] + offsets[i]
            surface, normal = collider.closest(target)
            toward = _unit(target - surface)
            points[i] = surface
            exits[i] = _unit(normal + toward)

        for i in range(1, len(anchors) - 1):
            if colliders[i] is not None and settings["drape"]:
                top, _normal = colliders[i].closest(
                    points[i] + up * DRAPE_PROBE_HEIGHT)
                points[i] = top + up * settings["radius"]

        active = [c for i, c in enumerate(colliders) if c is not None
                  and (settings["drape"] if 0 < i < len(anchors) - 1
                       else settings["attach"])]
        return np.array(points), exits, eases, active

    @staticmethod
    def _curve(particles):
        # Clamped cubic: Maya wants CV count + 2 knots.
        count = len(particles)
        knots = [0.0] * 3 + [float(k) for k in range(1, count - 3)] + \
            [float(count - 3)] * 3
        cvs = om.MPointArray([om.MPoint(*p) for p in particles])
        data = om.MFnNurbsCurveData().create()
        om.MFnNurbsCurve().create(cvs, knots, 3, om.MFnNurbsCurve.kOpen,
                                  False, False, data)
        return data
