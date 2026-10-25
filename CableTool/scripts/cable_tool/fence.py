"""The fence builder: a Maya node that turns a route into a fence.

    anchor world matrices, ground mesh, settings  ->  fenceToolBuilder
        -> outPosts, outRails, outPickets (three meshes)

Every time an input changes it:

1. Lays out the path: straight runs between anchors, or a curve through
   them (Path Curve), at the anchors' heights.
2. Places posts at most Post Spacing apart, evenly, with one on every
   anchor (Post At Every Anchor) so a corner gets a post, like a real
   fence. With a Ground mesh, each post (and each picket) is dropped onto
   it, so the fence steps over the terrain.
3. Joins neighbouring posts with straight rails (real rails are straight
   lumber, even on a curved fence), mounted on the posts' front face (or
   through them) and mitred where the fence turns so they meet without
   gaps. Round rails
   are wires or pipes and can sag between posts.
4. Fills each span with pickets nailed to the front of the rails.
5. Hangs a gate in one run (Gate After Anchor) between two heavier gate
   posts: a braced frame in the fence's own style, with hinges, a latch
   and the fence's pickets, swung open by Gate Swing. Only the gate is
   rebuilt when it swings, so it can be animated cheaply.

Posts and pickets can be the artist's own meshes, scaled to Post Height
and Picket Height. Wear leans posts and pickets and varies their height,
from Seed, for an old fence.

All geometry is made directly here (no Sweep Mesh), so the number of
posts and pickets can change live as an anchor is dragged.
"""

import math

import numpy as np

import maya.api.OpenMaya as om

from cable_tool.config import EPSILON

NODE_NAME = "fenceToolBuilder"
# Maya reserves 0x00000-0x7ffff for local, unpublished plugins.
NODE_ID = om.MTypeId(0x0007F0C2)

PATH_SAMPLES = 32       # samples per anchor-to-anchor run, for arc length
MAX_POSTS = 2000        # cap, so a tiny Post Spacing can't hang Maya
MAX_PICKETS = 20000
ROUND_SIDES = 12        # sides of a round post
WIRE_SIDES = 8          # sides of a round rail
SAG_SEGMENTS = 12       # segments of a sagging rail between two posts
MITRE_LIMIT = 3.0       # longest mitre, in rail depths, at a sharp turn
POST_SINK = 0.5         # posts go this many post widths into the ground
PICKET_LIFT = 0.04      # pickets stop this fraction of Post Height above it
MAX_LEAN = math.radians(7.0)  # post lean at Wear 1
PICKET_LEAN = math.radians(3.0)
HEIGHT_JITTER = 0.06    # height varies by up to this fraction at Wear 1
GATE_POST_SCALE = 1.4   # gate posts are this much thicker
GATE_GAP = 0.25         # gap at hinge and latch, in post widths
GATE_LIFT = 0.05        # gate clears the higher ground by this x Post Height
HINGE_SIDES = 8
UP = np.array([0.0, 1.0, 0.0])


def _unit(v):
    length = np.linalg.norm(v)
    return v / length if length > EPSILON else v * 0.0


def _flat(v):
    """v with no vertical part, normalised (zero if v is vertical)."""
    return _unit(np.array([v[0], 0.0, v[2]]))


def _rotate(v, axis, angle):
    """v rotated by angle around the unit axis (Rodrigues)."""
    c, s = math.cos(angle), math.sin(angle)
    return v * c + np.cross(axis, v) * s + axis * np.dot(axis, v) * (1 - c)


def _random(seed, kind, index):
    """Element index's own random numbers: moving an anchor adds or
    removes posts at the end without reshuffling the rest."""
    return np.random.default_rng([max(int(seed), 0), kind, index])


# -------------------------------------------------------------------------
# Path and layout (pure math, testable without Maya)
# -------------------------------------------------------------------------
def path_runs(points, curve, samples=PATH_SAMPLES):
    """Dense samples of each run between anchors: a list (one per run) of
    arrays of points, first and last on the anchors. curve blends each
    run from a straight line (0) to a Catmull-Rom curve (1)."""
    points = [np.asarray(p, dtype=float) for p in points]
    last = len(points) - 1
    # A closed route curves smoothly through its start too.
    loop = last > 2 and np.linalg.norm(points[0] - points[-1]) < 1e-4
    runs = []
    for i in range(last):
        p0, p1 = points[i], points[i + 1]
        before = (points[i - 1] if i > 0 else
                  points[-2] if loop else p0 - (p1 - p0))
        after = (points[i + 2] if i + 1 < last else
                 points[1] if loop else p1 + (p1 - p0))
        m0, m1 = (p1 - before) * 0.5, (after - p0) * 0.5
        run = []
        for k in range(samples + 1):
            t = float(k) / samples
            t2, t3 = t * t, t * t * t
            spline = ((2 * t3 - 3 * t2 + 1) * p0 + (t3 - 2 * t2 + t) * m0
                      + (-2 * t3 + 3 * t2) * p1 + (t3 - t2) * m1)
            run.append(p0 + (p1 - p0) * t + (spline - p0 - (p1 - p0) * t)
                       * curve)
        runs.append(np.array(run))
    return runs


def _at_lengths(samples, lengths):
    """Points at the given arc lengths along a polyline."""
    steps = np.linalg.norm(np.diff(samples, axis=0), axis=1)
    cumulative = np.concatenate([[0.0], np.cumsum(steps)])
    result = []
    for target in lengths:
        k = int(np.clip(np.searchsorted(cumulative, target) - 1, 0,
                        len(steps) - 1))
        t = (target - cumulative[k]) / max(steps[k], EPSILON)
        result.append(samples[k] + (samples[k + 1] - samples[k])
                      * min(max(t, 0.0), 1.0))
    return result


def _evenly(samples, spacing):
    """Points along samples at most spacing apart, evenly, including the
    first but not the last."""
    length = float(np.sum(np.linalg.norm(np.diff(samples, axis=0), axis=1)))
    count = max(1, int(math.ceil(length / max(spacing, EPSILON) - 1e-9)))
    return _at_lengths(samples, [length * k / count for k in range(count)])


def post_positions(runs, spacing, at_anchors, gate_run=None):
    """Where the posts go, from the first anchor to the last, and which
    post the gate hangs from (None without a gate). At anchors: each run
    is divided on its own, so every anchor gets a post. Else the whole
    path is divided evenly. The gate's run gets no posts in between: a
    gate post on each anchor and the gate across."""
    if at_anchors:
        groups = [[run] for run in runs]
    elif gate_run is None:
        groups = [runs]
    else:
        groups = [group for group in (runs[:gate_run], [runs[gate_run]],
                                      runs[gate_run + 1:]) if group]
    posts, gate_post = [], None
    for group in groups:
        if gate_run is not None and group[0] is runs[gate_run]:
            gate_post = len(posts)
            posts.append(group[0][0])
            continue
        whole = np.concatenate([group[0]] + [run[1:] for run in group[1:]])
        posts.extend(_evenly(whole, spacing))
    posts.append(runs[-1][-1])
    # Two anchors on the same spot would give two posts in one place.
    kept, kept_gate = [posts[0]], 0 if gate_post == 0 else None
    for k, point in enumerate(posts[1:], 1):
        if np.linalg.norm(point - kept[-1]) > EPSILON:
            kept.append(point)
        if k == gate_post:
            kept_gate = len(kept) - 1
    if kept_gate is not None and kept_gate >= MAX_POSTS - 1:
        kept_gate = None
    return kept[:MAX_POSTS], kept_gate


def spans(count, closed):
    """(first post, second post) of each span; a closed fence has one
    more, from the last post back to the first."""
    pairs = [(i, i + 1) for i in range(count - 1)]
    return pairs + [(count - 1, 0)] if closed else pairs


def span_frames(posts, flip, closed=False):
    """Per span: (horizontal direction, front side). Per post: the
    horizontal direction it faces along (the bisector at a corner)."""
    directions = []
    for i, j in spans(len(posts), closed):
        a, b = posts[i], posts[j]
        direction = _flat(b - a)
        if not direction.any():  # a vertical span: keep the last heading
            direction = directions[-1] if directions else np.array(
                [1.0, 0.0, 0.0])
        directions.append(direction)
    sides = [np.cross(d, UP) * (-1.0 if flip else 1.0) for d in directions]
    facing = []
    for i in range(len(posts)):
        near = [directions[j % len(directions)] for j in (i - 1, i)
                if closed or 0 <= j < len(directions)]
        heading = _unit(sum(near)) if near else np.array([1.0, 0.0, 0.0])
        facing.append(heading if heading.any() else near[-1])
    return directions, sides, facing


def mitre(sides, i, closed=False):
    """At post i: the horizontal direction to step out from the post's
    centre line so that rails from both neighbouring spans meet, and how
    far to step per unit of offset."""
    near = [sides[j % len(sides)] for j in (i - 1, i)
            if closed or 0 <= j < len(sides)]
    if len(near) == 1:
        return near[0], 1.0
    out = _unit(near[0] + near[1])
    if not out.any():  # the fence doubles back on itself
        return near[1], 1.0
    return out, min(1.0 / max(np.dot(out, near[1]), EPSILON), MITRE_LIMIT)


# -------------------------------------------------------------------------
# Mesh building
# -------------------------------------------------------------------------
def _sub3(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot3(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross3(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _norm3(a):
    length = math.sqrt(_dot3(a, a))
    if length <= EPSILON:
        return (0.0, 0.0, 0.0)
    return (a[0] / length, a[1] / length, a[2] / length)


class MeshBuilder(object):
    """Collects polygons, then makes one Maya mesh. Faces added with
    face() have their own vertices, so their edges are hard (boards);
    a tube() shares vertices around its sides, so it shades round."""

    def __init__(self, uv_scale):
        self.uv_scale = uv_scale
        self.points = []
        self.counts = []
        self.connects = []
        self.us, self.vs, self.uv_ids = [], [], []
        self.normals = []  # (face, vertex, normal) to lock

    @property
    def face_count(self):
        return len(self.counts)

    def _uv(self, u, v):
        self.us.append(u * self.uv_scale)
        self.vs.append(v * self.uv_scale)
        self.uv_ids.append(len(self.us) - 1)

    def face(self, corners, along):
        """A flat polygon with its own vertices. UVs are its corners in
        scene units on its own plane, U along `along` where it can be, so
        wood grain runs the length of a board. (Plain Python maths: on
        3-vectors it is several times faster than numpy calls, and a
        picket fence has thousands of faces.)"""
        corners = [tuple(c) for c in corners]
        origin = corners[0]
        normal = _norm3(_cross3(_sub3(corners[1], origin),
                                _sub3(corners[2], origin)))
        along = tuple(along)
        lean = _dot3(along, normal)
        u_axis = _norm3(_sub3(along, tuple(n * lean for n in normal)))
        if u_axis == (0.0, 0.0, 0.0):
            u_axis = _norm3(_sub3(corners[1], origin))
        v_axis = _cross3(normal, u_axis)
        base = len(self.points)
        for corner in corners:
            self.points.append(corner)
            offset = _sub3(corner, origin)
            self._uv(_dot3(offset, u_axis), _dot3(offset, v_axis))
        self.counts.append(len(corners))
        self.connects.extend(range(base, base + len(corners)))

    def prism(self, first, second, along, apex=None):
        """A solid between two matching loops of corners (one at each end):
        a board, a post or a picket. With an apex, the second end is a
        pyramid up to it instead of flat. Faces point outward whichever
        way round the loops are given."""
        first = [tuple(c) for c in first]
        second = [tuple(c) for c in second]
        loop = first + second
        centre = tuple(sum(c[a] for c in loop) / len(loop) for a in range(3))
        count = len(first)
        faces = [first]
        if apex is None:
            faces.append(second[::-1])
        else:
            apex = tuple(apex)
        for k in range(count):
            n = (k + 1) % count
            faces.append([first[k], first[n], second[n], second[k]])
            if apex is not None:
                faces.append([second[k], second[n], apex])
        for corners in faces:
            normal = _cross3(_sub3(corners[1], corners[0]),
                             _sub3(corners[2], corners[0]))
            middle = tuple(sum(c[a] for c in corners) / len(corners)
                           for a in range(3))
            if _dot3(normal, _sub3(middle, centre)) < 0:
                corners = corners[::-1]
            self.face(corners, along)

    def tube(self, path, radius, sides, up=UP, caps=True):
        """A round tube along a polyline: rings share vertices, so the
        sides shade smooth; U runs around, V along, in scene units."""
        path = [np.asarray(p, dtype=float) for p in path]
        rings = []
        for i, point in enumerate(path):
            tangent = _unit(path[min(i + 1, len(path) - 1)]
                            - path[max(i - 1, 0)])
            side = _unit(np.cross(tangent, up))
            if not side.any():
                side = _unit(np.cross(tangent, np.array([1.0, 0.0, 0.0])))
            lift = np.cross(side, tangent)
            base = len(self.points)
            for k in range(sides):
                angle = 2.0 * math.pi * k / sides
                self.points.append(point + radius * (side * math.cos(angle)
                                                     + lift * math.sin(angle)))
            rings.append(base)
        lengths = np.concatenate([[0.0], np.cumsum(np.linalg.norm(
            np.diff(np.array(path), axis=0), axis=1))])
        around = 2.0 * math.pi * radius
        for i in range(len(path) - 1):
            for k in range(sides):
                n = (k + 1) % sides
                self.counts.append(4)
                self.connects.extend([rings[i] + k, rings[i + 1] + k,
                                      rings[i + 1] + n, rings[i] + n])
                for u, v in ((k, i), (k, i + 1), (k + 1, i + 1),
                             (k + 1, i)):
                    self._uv(around * u / sides, lengths[v])
        if caps:
            # A ring runs clockwise seen from ahead: as is, it faces back.
            for ring, flip in ((rings[0], False), (rings[-1], True)):
                corners = [np.array(self.points[ring + k])
                           for k in range(sides)]
                self.face(corners[::-1] if flip else corners, up)

    def instance(self, source, matrix, height):
        """The artist's mesh (a SourceMesh), placed by matrix after being
        scaled to height. Keeps its UVs and its hard and soft edges."""
        scale = height / max(source.height, EPSILON)
        local = (source.points - source.base) * scale
        world = local.dot(matrix[:3, :3].T) + matrix[3, :3]
        base = len(self.points)
        self.points.extend(world)
        first_face = len(self.counts)
        self.counts.extend(source.counts)
        self.connects.extend(base + source.connects)
        uv_base = len(self.us)
        self.us.extend(source.us)
        self.vs.extend(source.vs)
        self.uv_ids.extend(uv_base + source.uv_ids)
        rotation = matrix[:3, :3]  # no scale, so normals turn with it
        for face, vertex, normal in source.normals:
            self.normals.append((first_face + face, base + vertex,
                                 _unit(normal.dot(rotation))))

    def mesh(self):
        """The collected polygons as Maya mesh data (empty if none)."""
        data = om.MFnMeshData().create()
        fn = om.MFnMesh()
        if not self.counts:
            fn.create([], [], [], parent=data)
            return data
        fn.create([om.MPoint(*p) for p in self.points], self.counts,
                  self.connects, self.us, self.vs, parent=data)
        fn.assignUVs(self.counts, self.uv_ids)
        if self.normals:
            faces, vertices, normals = zip(*self.normals)
            fn.setFaceVertexNormals([om.MVector(*n) for n in normals],
                                    list(faces), list(vertices))
        return data


class SourceMesh(object):
    """An artist's post or picket mesh, read once per compute: its points
    with the bottom centre at the origin, faces, UVs and normals."""

    def __init__(self, mesh_obj):
        fn = om.MFnMesh(mesh_obj)
        self.points = np.array([[p.x, p.y, p.z] for p in fn.getPoints()])
        low, high = self.points.min(axis=0), self.points.max(axis=0)
        self.base = np.array([(low[0] + high[0]) * 0.5, low[1],
                              (low[2] + high[2]) * 0.5])
        self.height = high[1] - low[1]
        counts, connects = fn.getVertices()
        self.counts = list(counts)
        self.connects = np.array(connects, dtype=int)
        us, vs = fn.getUVs()
        uv_counts, uv_ids = fn.getAssignedUVs()
        if len(uv_ids) == len(self.connects) and len(us):
            self.us, self.vs = list(us), list(vs)
            self.uv_ids = np.array(uv_ids, dtype=int)
        else:  # no UVs: every corner at 0, 0
            self.us, self.vs = [0.0], [0.0]
            self.uv_ids = np.zeros(len(self.connects), dtype=int)
        normal_counts, normal_ids = fn.getNormalIds()
        all_normals = fn.getNormals()
        self.normals = []
        corner = 0
        for face, count in enumerate(self.counts):
            for k in range(count):
                n = all_normals[normal_ids[corner]]
                self.normals.append((face, int(self.connects[corner]),
                                     np.array([n.x, n.y, n.z])))
                corner += 1


def _frame(origin, x_axis, y_axis):
    """A 4x4 row-vector matrix (Maya's convention) from an origin, an X
    axis and an approximate Y axis."""
    x_axis = _unit(x_axis)
    z_axis = _unit(np.cross(x_axis, y_axis))
    y_axis = np.cross(z_axis, x_axis)
    matrix = np.identity(4)
    matrix[0, :3], matrix[1, :3], matrix[2, :3] = x_axis, y_axis, z_axis
    matrix[3, :3] = origin
    return matrix


# -------------------------------------------------------------------------
# The fence
# -------------------------------------------------------------------------
class Ground(object):
    """Drops points onto a mesh: the nearest surface straight above or
    below. Works in the mesh's object space (see Collider in solver.py
    for why the mesh comes in as outMesh + matrix)."""

    def __init__(self, mesh_obj, matrix):
        self.fn = om.MFnMesh(mesh_obj)
        self.matrix = matrix
        self.inverse = matrix.inverse()
        self.accel = self.fn.autoUniformGridParams()
        self.down = om.MFloatVector(om.MVector(0.0, -1.0, 0.0)
                                    * self.inverse)

    def height(self, point):
        """The ground's height under (or over) point, or None if the
        ground doesn't reach there."""
        local = om.MPoint(*point) * self.inverse
        hit = self.fn.closestIntersection(
            om.MFloatPoint(local.x, local.y, local.z), self.down,
            om.MSpace.kObject, 1e7, True, accelParams=self.accel)
        if not hit:
            return None
        found = om.MPoint(hit[0]) * self.matrix
        return found.y


def build_fence(anchor_points, settings, ground=None, post_source=None,
                picket_source=None):
    """The three meshes' builders (posts, rails, pickets), the post count
    and the gate's layout for build_gate (None without a gate), for
    anchor positions and settings."""
    s = settings
    uv = s["fenceUvRepeat"]
    posts_mesh, rails_mesh, pickets_mesh = (MeshBuilder(uv), MeshBuilder(uv),
                                            MeshBuilder(uv))
    runs = path_runs(anchor_points, s["fenceCurve"])
    count = len(anchor_points)
    loop = count > 3 and np.linalg.norm(
        np.asarray(anchor_points[0]) - np.asarray(anchor_points[-1])) < 1e-4
    # Gate After Anchor n: the run from anchor n to n + 1 (Start is 1).
    # On an open route, the last anchor closes the gap back to Start.
    gate_after = int(s["gateAnchor"])
    gate_run = gate_after - 1 if 1 <= gate_after <= len(runs) else None
    closing = gate_after == count and not loop and count >= 3
    centres, gate_post = post_positions(runs, s["postSpacing"],
                                        s["cornerPosts"], gate_run)
    # A route that ends where it started (a yard) closes into a ring.
    closed = (len(centres) > 3
              and np.linalg.norm(centres[0] - centres[-1]) < 1e-4)
    if closed:
        centres = centres[:-1]
    if closing and len(centres) >= 3:
        closed, gate_post = True, len(centres) - 1
    if len(centres) < 2:
        return posts_mesh, rails_mesh, pickets_mesh, len(centres), None
    pairs = spans(len(centres), closed)
    gate_span = gate_post if gate_post is not None and \
        gate_post < len(pairs) else None
    gate_posts = set(pairs[gate_span]) if gate_span is not None else set()
    directions, sides, facing = span_frames(centres, s["fenceFlip"], closed)

    def ground_at(point):
        if ground is None:
            return point
        height = ground.height(point)
        if height is None:
            return point
        return np.array([point[0], height, point[2]])

    wear = s["wear"]
    width = s["postWidth"]
    widths = [width * GATE_POST_SCALE if i in gate_posts else width
              for i in range(len(centres))]
    bases, axes, heights = [], [], []
    for i, centre in enumerate(centres):
        rng = _random(s["fenceSeed"], 1, i)
        lean_dir, lean, stretch = (rng.uniform(0.0, 2.0 * math.pi),
                                   rng.normal(0.0, 0.5),
                                   rng.uniform(-1.0, 1.0))
        tilt = np.array([math.cos(lean_dir), 0.0, math.sin(lean_dir)])
        axis = _rotate(UP, _unit(np.cross(UP, tilt)),
                       float(np.clip(lean, -1.0, 1.0)) * MAX_LEAN * wear)
        bases.append(ground_at(centre))
        if i in gate_posts:  # set true, or the gate would bind
            axis, stretch = UP, 0.0
        axes.append(axis)
        heights.append(s["postHeight"] * (1.0 + HEIGHT_JITTER * wear
                                          * stretch))

    # Posts.
    for i, (base, axis, height) in enumerate(zip(bases, axes, heights)):
        width = widths[i]
        sink = width * POST_SINK
        bottom = base - axis * sink
        if post_source is not None:
            posts_mesh.instance(post_source, _frame(bottom, facing[i], axis),
                                height + sink)
        elif s["roundPosts"]:
            posts_mesh.tube([bottom, base + axis * height], width * 0.5,
                            ROUND_SIDES, up=facing[i])
        else:
            side = _unit(np.cross(facing[i], axis))
            along = _unit(np.cross(axis, side))
            square = [along * x + side * z for x, z in
                      ((-1, -1), (1, -1), (1, 1), (-1, 1))]
            cap = s["postCap"] * width * 0.5
            top = base + axis * (height - cap)
            posts_mesh.prism([bottom + c * width * 0.5 for c in square],
                             [top + c * width * 0.5 for c in square], axis,
                             apex=top + axis * cap if cap > EPSILON else None)

    width = s["postWidth"]

    # Rails: from post to post on the posts' front face, mitred.
    rails = int(s["railCount"])
    round_rails = bool(s["roundRails"])
    depth = s["railSize"] if round_rails else s["railDepth"]
    # Rail centre, out from the post's centre line: on its front face, or
    # through the post's middle.
    face = 0.0 if s["railInline"] else width * 0.5 + depth * 0.5
    levels = []
    if rails:
        low = min(s["railBottom"], s["railTop"])
        high = max(s["railBottom"], s["railTop"])
        levels = [low + (high - low) * k / max(rails - 1, 1)
                  for k in range(rails)] if rails > 1 else [high]

    def rail_point(i, level, out):
        """Where a rail's centre line meets post i: on the post's axis at
        the rail's height (so rails follow a leaning post), stepped out
        to its front face along the mitre."""
        height = min(level, heights[i])
        point = bases[i] + axes[i] * (height / max(axes[i][1], 0.2))
        return point + mitres[i][0] * out * mitres[i][1]

    mitres = [mitre(sides, i, closed) for i in range(len(centres))]
    # An open fence's end rails run on to the far side of the end post,
    # and so do the rails either side of a gate.
    ends_at = set(gate_posts) | (set() if closed else
                                 {0, len(centres) - 1})
    for k, level in enumerate(levels):
        for i, (first, second) in enumerate(pairs):
            if i == gate_span:
                continue
            ends = []
            for j, inward in ((first, 1.0), (second, -1.0)):
                extend = (widths[j] * 0.5 * -inward * directions[i]
                          if j in ends_at else 0.0)
                ends.append(lambda out, j=j, extend=extend:
                            rail_point(j, level, out) + extend)
            if round_rails:
                start, end = ends[0](face), ends[1](face)
                sag = s["railSag"] * np.linalg.norm(end - start)
                segments = SAG_SEGMENTS if sag > EPSILON else 1
                path = [start + (end - start) * t - UP * sag * 4 * t * (1 - t)
                        for t in np.linspace(0.0, 1.0, segments + 1)]
                rails_mesh.tube(path, s["railSize"] * 0.5, WIRE_SIDES,
                                caps=True)
            else:
                half = s["railSize"] * 0.5
                loops = []
                for end in ends:
                    loops.append([end(face + d * depth * 0.5) + UP * h * half
                                  for d, h in ((-1, -1), (1, -1), (1, 1),
                                               (-1, 1))])
                rails_mesh.prism(loops[0], loops[1], directions[i])

    # Pickets: across each span, nailed to the front of the rails.
    if s["pickets"]:
        picket_w = s["picketWidth"]
        pitch = picket_w + s["picketGap"]
        thick = s["picketThickness"]
        out = (max(width * 0.5, depth * 0.5) if s["railInline"] else
               width * 0.5 + (depth if rails else 0.0)) + thick * 0.5
        point = min(s["picketPoint"], 1.0) * picket_w * 0.5
        lift = PICKET_LIFT * s["postHeight"]
        made = 0
        for i, (first, second) in enumerate(pairs):
            if i == gate_span:
                continue
            a = bases[first] + mitres[first][0] * out * mitres[first][1]
            b = bases[second] + mitres[second][0] * out * mitres[second][1]
            length = np.linalg.norm((b - a) * [1.0, 0.0, 1.0])
            count = max(1, int(round(length / max(pitch, EPSILON))))
            for j in range(count):
                if made >= MAX_PICKETS:
                    break
                t = (j + 0.5) / count
                foot = ground_at(a + (b - a) * t)
                rng = _random(s["fenceSeed"], 2, made)
                height = s["picketHeight"] * (1.0 + HEIGHT_JITTER * wear
                                              * rng.uniform(-1.0, 1.0))
                up = _rotate(UP, sides[i], PICKET_LEAN * wear
                             * float(np.clip(rng.normal(0.0, 0.5), -1, 1)))
                along = directions[i]
                bottom = foot + UP * lift
                made += 1
                if picket_source is not None:
                    # Its +Z faces the front, whichever side that is.
                    facing_x = along if np.dot(np.cross(along, up),
                                               sides[i]) > 0 else -along
                    pickets_mesh.instance(picket_source,
                                          _frame(bottom, facing_x, up), height)
                    continue
                outline = [(-0.5 * picket_w, 0.0), (0.5 * picket_w, 0.0),
                           (0.5 * picket_w, height - point)]
                if point > EPSILON:
                    outline.append((0.0, height))
                outline.append((-0.5 * picket_w, height - point))
                front = [bottom + along * x + up * y + sides[i] * thick * 0.5
                         for x, y in outline]
                back = [p - sides[i] * thick for p in front]
                pickets_mesh.prism(front, back, up)

    gate = None
    if gate_span is not None:
        first, second = pairs[gate_span]
        gate = {"hinge": bases[first], "latch": bases[second],
                "front": sides[gate_span], "postWidth": widths[first],
                "plane": face if rails or s["railInline"] else 0.0,
                "levels": levels}
    return posts_mesh, rails_mesh, pickets_mesh, len(centres), gate


def build_gate(gate, settings):
    """The gate's mesh, from build_fence's layout of it and the settings.
    Kept apart so swinging the gate rebuilds only this."""
    s = settings
    mesh = MeshBuilder(s["fenceUvRepeat"])
    if gate is None:
        return mesh
    hinge, latch = gate["hinge"], gate["latch"]
    if s["gateHingeFlip"]:
        hinge, latch = latch, hinge
    along = _flat(latch - hinge)
    front = gate["front"]
    gap = GATE_GAP * s["postWidth"]
    offset = gate["postWidth"] * 0.5 + gap  # post centre to gate edge
    opening = np.linalg.norm((latch - hinge) * [1.0, 0.0, 1.0]) - 2 * offset
    if opening < s["postWidth"] or not along.any():
        return mesh  # the gate posts are too close for a gate
    # Level, clearing the higher ground; heights above the ground as the
    # fence measures them (from the gate posts' mean ground height).
    ground = (hinge[1] + latch[1]) * 0.5
    bottom = max(hinge[1], latch[1]) + GATE_LIFT * s["postHeight"]
    levels = list(gate["levels"])
    if len(levels) < 2:
        levels = sorted({min(s["railBottom"], s["railTop"]),
                         max(s["railBottom"], s["railTop"])} | set(levels))
        if len(levels) < 2:
            levels = [levels[0] * 0.3, levels[0]]
    levels = [max(ground + level - bottom, s["railSize"] * 0.5)
              for level in levels]
    picket_top = ground + s["picketHeight"] - bottom
    if s["gateDouble"]:
        width = (opening - gap) * 0.5
        leaves = ((hinge, along, width, True), (latch, -along, width, False))
    else:
        leaves = ((hinge, along, opening, True),)
    angle = math.radians(s["gateSwing"])
    for origin, x_dir, width, latched in leaves:
        pivot = (np.array([origin[0], bottom, origin[2]]) + x_dir * offset
                 + front * gate["plane"])
        _gate_leaf(mesh, s, pivot, x_dir, front, angle, width, levels,
                   picket_top, gap, latched)
    return mesh


def _gate_leaf(mesh, s, pivot, x_dir, front, angle, width, levels,
               picket_top, gap, latched):
    """One leaf, built in its own frame (X from the hinge across the
    opening, Y up, Z to the front) and swung by angle about the hinge."""
    cos, sin = math.cos(angle), math.sin(angle)

    def at(x, y, z):
        return (pivot + x_dir * (x * cos - z * sin) + UP * y
                + front * (x * sin + z * cos))

    grain = at(1.0, 0.0, 0.0) - at(0.0, 0.0, 0.0)
    size = s["railSize"]
    low, high = levels[0], levels[-1]

    def box(x0, x1, y0, y1, z0, z1, along):
        mesh.prism([at(x0, y0, z0), at(x0, y1, z0), at(x0, y1, z1),
                    at(x0, y0, z1)],
                   [at(x1, y0, z0), at(x1, y1, z0), at(x1, y1, z1),
                    at(x1, y0, z1)], along)

    def bar(start, end, half, depth):
        """A board between two (x, y) points, half as wide, depth thick."""
        d = np.subtract(end, start) / max(np.linalg.norm(
            np.subtract(end, start)), EPSILON)
        n = np.array([-d[1], d[0]]) * half
        loops = [[at(px + sx * n[0], py + sx * n[1], sz * depth * 0.5)
                  for sx, sz in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
                 for px, py in (start, end)]
        mesh.prism(loops[0], loops[1], grain)

    if s["roundRails"]:
        # A tubular steel gate: a frame of pipes, rails and a brace.
        radius = max(size, s["postWidth"] * 0.35) * 0.5
        depth = radius * 2.0
        y0, y1 = low - radius, high + radius
        for path in ([(radius, y0), (radius, y1)],
                     [(width - radius, y0), (width - radius, y1)],
                     [(radius, low), (width - radius, high)]) + tuple(
                         [(radius, y), (width - radius, y)] for y in levels):
            mesh.tube([at(x, y, 0.0) for x, y in path], radius, WIRE_SIDES)
    else:
        # A framed board gate: stiles at both ends, a rail at each of the
        # fence's rail heights and a brace from the bottom of the hinge
        # side up to the latch side, which holds the latch end up.
        depth = s["railDepth"]
        y0, y1 = low - size * 0.5, high + size * 0.5
        for x0 in (0.0, width - size):
            box(x0, x0 + size, y0, y1, -depth * 0.5, depth * 0.5, UP)
        for y in levels:
            box(size, width - size, y - size * 0.5, y + size * 0.5,
                -depth * 0.5, depth * 0.5, grain)
        if width > 3 * size:
            bar((size * 1.5, low), (width - size * 1.5, high), size * 0.4,
                depth * 0.9)

    if s["pickets"]:
        picket_w = s["picketWidth"]
        thick = s["picketThickness"]
        count = max(1, int(round(width / max(picket_w + s["picketGap"],
                                             EPSILON))))
        point = min(s["picketPoint"], 1.0) * picket_w * 0.5
        z = depth * 0.5 + thick * 0.5
        for j in range(count):
            x = width * (j + 0.5) / count
            outline = [(x - 0.5 * picket_w, 0.0), (x + 0.5 * picket_w, 0.0),
                       (x + 0.5 * picket_w, picket_top - point)]
            if point > EPSILON:
                outline.append((x, picket_top))
            outline.append((x - 0.5 * picket_w, picket_top - point))
            mesh.prism([at(px, py, z + thick * 0.5) for px, py in outline],
                       [at(px, py, z - thick * 0.5) for px, py in outline],
                       UP)

    # Hardware: a T-hinge strap and barrel at the top and bottom rail, and
    # a latch on the free end.
    plate = max(depth * 0.15, 0.004)
    barrel = max(gap * 0.35, size * 0.12)
    for y in (low, high):
        mesh.tube([at(-gap * 0.5, y - size * 0.8, 0.0),
                   at(-gap * 0.5, y + size * 0.8, 0.0)], barrel, HINGE_SIDES)
        box(-gap * 0.5, width * 0.3, y - size * 0.2, y + size * 0.2,
            depth * 0.5, depth * 0.5 + plate, grain)
    if latched:
        box(width - size * 0.8, width + gap * 0.9, high - size * 0.25,
            high + size * 0.25, depth * 0.5, depth * 0.5 + plate * 3, grain)


# -------------------------------------------------------------------------
# The node
# -------------------------------------------------------------------------
class FenceBuilderNode(om.MPxNode):
    """Inputs: anchor[i] (matrix, and mesh + component for a vertex or
    face anchor), groundMesh + groundMatrix, postMesh, picketMesh and the
    fence's settings. Outputs: outPosts, outRails, outPickets, outGate
    (meshes in world space) and outPostCount."""

    SETTINGS = ("postSpacing", "cornerPosts", "fenceCurve", "fenceFlip",
                "postHeight", "postWidth", "roundPosts", "postCap",
                "railCount", "railBottom", "railTop", "railSize", "railDepth",
                "roundRails", "railInline", "railSag", "pickets", "picketHeight",
                "picketWidth", "picketGap", "picketThickness", "picketPoint",
                "wear", "fenceSeed", "fenceUvRepeat", "gateAnchor",
                "gateDouble", "gateHingeFlip", "gateSwing")
    BOOLS = ("cornerPosts", "fenceFlip", "roundPosts", "roundRails",
             "railInline", "pickets", "gateDouble", "gateHingeFlip")
    INTS = ("railCount", "fenceSeed", "gateAnchor")
    OUTPUTS = ("outPosts", "outRails", "outPickets", "outGate")
    # Settings that change only the gate: swinging it (or animating the
    # swing) rebuilds the gate alone, not the whole fence.
    GATE_ONLY = ("gateDouble", "gateHingeFlip", "gateSwing")

    def __init__(self):
        super(FenceBuilderNode, self).__init__()
        self._gate = None     # the gate's layout from the last full build
        self._built = False   # ... and whether there has been one

    @staticmethod
    def creator():
        return FenceBuilderNode()


    @classmethod
    def initialize(cls):
        num = om.MFnNumericAttribute()
        typed = om.MFnTypedAttribute()
        matrix = om.MFnMatrixAttribute()
        compound = om.MFnCompoundAttribute()

        cls.anchorMatrix = matrix.create("anchorMatrix", "am")
        cls.anchorMesh = typed.create("anchorMesh", "ams", om.MFnData.kMesh)
        # 0 = the whole object, 1 = vertex anchorIndex, 2 = face.
        cls.anchorKind = num.create("anchorKind", "ak",
                                    om.MFnNumericData.kInt, 0)
        cls.anchorIndex = num.create("anchorIndex", "ai",
                                     om.MFnNumericData.kInt, 0)
        cls.anchor = compound.create("anchor", "an")
        for child in (cls.anchorMatrix, cls.anchorMesh, cls.anchorKind,
                      cls.anchorIndex):
            compound.addChild(child)
        compound.array = True
        cls.addAttribute(cls.anchor)

        inputs = [cls.anchor]
        for name in ("groundMesh", "postMesh", "picketMesh"):
            attr = typed.create(name, name, om.MFnData.kMesh)
            setattr(cls, name, attr)
            cls.addAttribute(attr)
            inputs.append(attr)
        cls.groundMatrix = matrix.create("groundMatrix", "gm")
        cls.addAttribute(cls.groundMatrix)
        inputs.append(cls.groundMatrix)

        gate_only = []
        for name in cls.SETTINGS:
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
            (gate_only if name in cls.GATE_ONLY else inputs).append(attr)

        outputs = []
        for name in cls.OUTPUTS:
            attr = typed.create(name, name, om.MFnData.kMesh)
            typed.writable = False
            typed.storable = False
            setattr(cls, name, attr)
            cls.addAttribute(attr)
            outputs.append(attr)
        cls.outPostCount = num.create("outPostCount", "opc",
                                      om.MFnNumericData.kInt, 0)
        num.writable = False
        num.storable = False
        cls.addAttribute(cls.outPostCount)
        outputs.append(cls.outPostCount)

        for source in inputs:
            for target in outputs:
                cls.attributeAffects(source, target)
        for source in gate_only:
            cls.attributeAffects(source, cls.outGate)

    def compute(self, plug, data):
        outputs = [getattr(self, name) for name in self.OUTPUTS] + [
            self.outPostCount]
        if plug.attribute() not in outputs:
            return None
        settings = self._read_settings(data)
        if plug.attribute() == self.outGate and self._built and all(
                data.isClean(attr) for attr in outputs if attr != self.outGate):
            # Only a gate setting changed: the fence is as it was.
            data.outputValue(self.outGate).setMObject(
                build_gate(self._gate, settings).mesh())
            data.setClean(self.outGate)
            return None
        points = [anchor_point(*anchor) for anchor in self._read_anchors(data)]

        def mesh(attr):
            obj = data.inputValue(attr).asMesh()
            return None if obj.isNull() else obj

        ground = mesh(self.groundMesh)
        if ground is not None:
            ground = Ground(ground, data.inputValue(
                self.groundMatrix).asMatrix())
        sources = [SourceMesh(m) if m is not None and om.MFnMesh(m).numPolygons
                   else None for m in (mesh(self.postMesh),
                                       mesh(self.picketMesh))]
        if len(points) >= 2:
            built = build_fence(points, settings, ground, *sources)
        else:
            empty = MeshBuilder(1.0)
            built = (empty, empty, empty, 0, None)
        self._gate, self._built = built[4], True
        built = built[:3] + (build_gate(self._gate, settings),) + built[3:4]
        for attr, builder in zip(outputs[:4], built[:4]):
            data.outputValue(attr).setMObject(builder.mesh())
            data.setClean(attr)
        data.outputValue(self.outPostCount).setInt(built[4])
        data.setClean(self.outPostCount)
        return None

    def _read_settings(self, data):
        values = {}
        for name in self.SETTINGS:
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
            mesh = element.child(self.anchorMesh).asMesh()
            mesh = None if mesh.isNull() else mesh
            anchors.append((handle.elementLogicalIndex(),
                            element.child(self.anchorMatrix).asMatrix(), mesh,
                            element.child(self.anchorKind).asInt()
                            if mesh else 0,
                            element.child(self.anchorIndex).asInt()))
            if not handle.next():
                break
        anchors.sort(key=lambda item: item[0])
        return [anchor[1:] for anchor in anchors]


def anchor_point(matrix, mesh, kind, index):
    """An anchor's world position: its vertex or face centre for a
    component anchor, else its pivot."""
    from cable_tool.solver import Anchor
    port = Anchor(matrix, mesh, kind, index).port()
    if port is not None:
        return port[0]
    return np.array([matrix[12], matrix[13], matrix[14]])
