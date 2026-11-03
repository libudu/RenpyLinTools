# A multiline text curtain: independent, anchored chains with mouse impulses.
init 1 python in lintools_text:
    from builtins import list as _curtain_list, dict as _curtain_dict
    from renpy.color import Color
    from renpy.display.model import Model
    from renpy.display.transform import Transform

    CURTAIN = {
        "cell": (None, 64.0, 24.0, 160.0),
        "size": (None, 42.0, 12.0, 120.0),
        "strength": (None, 0.65, 0.0, 3.0),
        "damping": (None, 2.0, 0.1, 12.0),
        "radius": (None, 20.0, 1.0, 100.0),
        "gravity": (None, 1100.0, 100.0, 4000.0),
        "margin": (None, 80.0, 20.0, 240.0),
        "subdivisions": (None, 8.0, 2.0, 16.0),
    }

    # A small uniform array per draw avoids uploading a full-sized CPU canvas.
    # Long chains are split with overlapping points to keep joins continuous.
    CURTAIN_ROPE_POINTS = 64
    renpy.register_shader("lintools.curtain_rope", variables="""
        attribute vec2 a_tex_coord;
        uniform mat4 u_transform;
        uniform vec2 u__points[64];
        uniform vec3 u__range;
        uniform vec4 u__color;
        uniform vec2 u_model_size;
        varying float v__edge;
        varying vec2 v__position;
    """, vertex_300="""
        float l__index = floor(a_tex_coord.y * (u__range.y - 1.0) + 0.5) + u__range.x;
        vec2 l__center = u__points[int(l__index)];
        vec2 l__before = u__points[int(max(0.0, l__index - 1.0))];
        vec2 l__after = u__points[int(min(u__range.z, l__index + 1.0))];
        vec2 l__direction = l__after - l__before;
        l__direction *= inversesqrt(max(dot(l__direction, l__direction), 0.000001));
        vec2 l__normal = vec2(-l__direction.y, l__direction.x);
        v__edge = a_tex_coord.x * 2.0 - 1.0;
        v__position = l__center + l__normal * v__edge + vec2(0.5);
        gl_Position = u_transform * vec4(v__position, 0.0, 1.0);
    """, fragment_300="""
        if (v__position.x < 0.0 || v__position.y < 0.0 ||
            v__position.x >= u_model_size.x || v__position.y >= u_model_size.y) discard;
        // A one-virtual-pixel line with a soft edge, including at subpixel positions.
        gl_FragColor = u__color * clamp(1.0 - abs(v__edge), 0.0, 1.0);
    """)

    def point_segment(point, start, end):
        dx, dy = end[0] - start[0], end[1] - start[1]
        length2 = dx*dx + dy*dy
        t = 0.0 if length2 < 0.000001 else max(0.0, min(1.0,
            ((point[0]-start[0])*dx + (point[1]-start[1])*dy) / length2))
        return math.hypot(point[0]-start[0]-t*dx, point[1]-start[1]-t*dy), t

    def swept_rope_distance(a, b, p, q):
        """Distance from the entire mouse stroke to a rope, plus rope parameter."""
        rx, ry = b[0]-a[0], b[1]-a[1]
        sx, sy = q[0]-p[0], q[1]-p[1]
        px, py = p[0]-a[0], p[1]-a[1]
        cross = rx*sy - ry*sx
        if abs(cross) > 0.000001:
            t = (px*sy - py*sx) / cross
            u = (px*ry - py*rx) / cross
            if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
                return 0.0, u
        candidates = [point_segment(a, p, q), point_segment(b, p, q),
            (point_segment(p, a, b)[0], 0.0), (point_segment(q, a, b)[0], 1.0)]
        return min(candidates, key=lambda item: item[0])

    class CurtainText(renpy.Displayable):
        STEP = 1.0 / 120.0
        SLEEP_STEPS = 60
        SLEEP_DISTANCE2 = 0.015 ** 2

        def __init__(self, text, cell=64, size=42, strength=0.65, damping=2,
                radius=20, gravity=1100, margin=80, style="default",
                color="#e8eee9", rope_color="#718b88", subdivisions=8, **properties):
            super(CurtainText, self).__init__(**properties)
            raw_options = dict(cell=cell, size=size, strength=strength,
                damping=damping, radius=radius, gravity=gravity, margin=margin,
                subdivisions=subdivisions)
            self.options = parse_parameters("ltcurtain",
                ";".join("%s=%s" % item for item in raw_options.items()), CURTAIN)
            if not self.options["subdivisions"].is_integer():
                raise ValueError("LinTools ltcurtain: subdivisions must be an integer.")
            subdivisions = int(self.options["subdivisions"])
            self.source = text.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
            self.rows = [list(clusters(line)) for line in self.source.split("\n")]
            self.columns = max((len(row) for row in self.rows), default=0)
            if not any(not char.isspace() for row in self.rows for char in row):
                raise ValueError("LinTools ltcurtain: include at least one visible character.")
            if any("\t" in row for row in self.rows):
                raise ValueError("LinTools ltcurtain: use fullwidth spaces instead of tabs.")
            self.rope_color = rope_color
            self.chains = []
            self.solvers = []
            self.glyphs = []
            self.rope_models = []
            self.letters = []
            cell, margin = self.options["cell"], self.options["margin"]
            for col in range(self.columns):
                occupied = [i for i, row in enumerate(self.rows)
                    if col < len(row) and not row[col].isspace()]
                if not occupied:
                    continue
                first, last = occupied[0], occupied[-1]
                x = margin + (col + 0.5) * cell
                anchor_y = margin + first * cell
                # x/y, previous x/y, incoming rest length, glyph, inverse mass,
                # rest distance from the anchor. The anchor has zero inverse mass.
                # Frame-local animation state must not use Ren'Py's list
                # literals: those track rollback on every coordinate write.
                anchor = _curtain_list((x, anchor_y, x, anchor_y, 0.0, None, 0.0, 0.0))
                nodes = []
                links = []
                bends = []
                spans = []
                previous = anchor
                for row in range(first, last + 1):
                    char = self.rows[row][col] if col < len(self.rows[row]) else ""
                    letter = None
                    if char and not char.isspace():
                        letter = Text(char.replace("{", "{{"), substitute=False,
                            slow=False, style=style, size=int(self.options["size"]),
                            color=color, outlines=[(1, "#101b22", 0, 0)])
                        self.letters.append(letter)
                    length = cell*0.5 if row == first else cell
                    count = max(1, int(math.ceil(subdivisions*length/cell)))
                    for part in range(count):
                        glyph = letter if part == count-1 else None
                        rest = previous[7] + length/count
                        y = anchor_y + rest
                        # Light rope particles, heavier glyphs; increasing the
                        # subdivision count does not add a full glyph's mass.
                        inverse_mass = 1.0/(1.0/subdivisions + (1.0 if glyph is not None else 0.0))
                        node = _curtain_list((x, y, x, y, length/count, glyph, inverse_mass, rest))
                        links.append((previous, node, length/count))
                        nodes.append(node)
                        previous = node
                points = [anchor] + nodes
                for a, b in zip(points, points[2:]):
                    bends.append((a, b, b[7]-a[7]))
                # Unilateral coarse constraints accelerate tension propagation
                # through long chains without forbidding slack or curved spans.
                stride = 2
                while stride < len(points):
                    for start in range(0, len(points)-1, stride):
                        end = min(start+stride, len(points)-1)
                        if end-start > 1:
                            a, b = points[start], points[end]
                            spans.append((a, b, b[7]-a[7]))
                    stride *= 2
                self.chains.append((anchor, nodes, links, bends, spans))
                for start in range(0, len(points)-1, CURTAIN_ROPE_POINTS-3):
                    end = min(start+CURTAIN_ROPE_POINTS-3, len(points)-1)
                    first = max(0, start-1)
                    chunk = tuple(points[first:min(len(points), end+2)])
                    rope = (Model(size=(int(self.columns*cell + margin*2),
                        int(len(self.rows)*cell + margin*2)))
                        .grid_mesh(2, end-start+1).shader("lintools.curtain_rope"))
                    self.rope_models.append((chunk,
                        (float(start-first), float(end-start+1), float(len(chunk)-1)), rope))
                self.solvers.append((self.prepare_constraints(bends, 0.04),
                    self.prepare_constraints(list(reversed(spans))),
                    self.prepare_constraints(links),
                    self.prepare_constraints(list(reversed(links)))))
                reach = max(1, subdivisions//2)
                for i, node in enumerate(nodes):
                    if node[5] is not None:
                        # Keep transforms alive so Ren'Py can reuse glyph renders.
                        tilted = Transform(node[5], subpixel=True)
                        tilted.rotate = 0.0
                        self.glyphs.append((node,
                            nodes[i-reach] if i >= reach else anchor,
                            nodes[min(len(nodes)-1, i+reach)], tilted))
            # Straight, untouched chains are already at rest. Wake only those
            # hit by the mouse and stop scheduling frames after they settle.
            self.active_chains = _curtain_dict()
            self.last_st = None
            self.accumulator = 0.0
            self.pointer = None

        def visit(self):
            return [glyph[3] for glyph in self.glyphs] + [item[2] for item in self.rope_models]

        def per_interact(self):
            self.last_st = None
            self.pointer = None
            renpy.redraw(self, 0)

        def reset(self):
            for anchor, nodes, links, bends, spans in self.chains:
                y = anchor[1]
                for node in nodes:
                    y += node[4]
                    node[0] = node[2] = anchor[0]
                    node[1] = node[3] = y
            self.last_st = None
            self.accumulator = 0.0
            self.pointer = None
            self.active_chains.clear()
            renpy.redraw(self, 0)

        @staticmethod
        def prepare_constraints(constraints, stiffness=1.0):
            return [(a, b, rest, rest*rest,
                stiffness*a[6]/(a[6]+b[6]), stiffness*b[6]/(a[6]+b[6]))
                for a, b, rest in constraints]

        @staticmethod
        def solve_constraints(constraints, tension_only=False):
            # Mass ratios and sweep order never change. Batch the hot loop
            # instead of making a Python method call for every single edge.
            hypot = math.hypot
            for a, b, rest, rest2, weight_a, weight_b in constraints:
                dx, dy = b[0]-a[0], b[1]-a[1]
                if tension_only and dx*dx + dy*dy <= rest2:
                    continue
                length = hypot(dx, dy)
                if length < 0.000001:
                    continue
                correction = (length-rest)/length
                cx, cy = dx*correction, dy*correction
                a[0] += cx*weight_a
                a[1] += cy*weight_a
                b[0] -= cx*weight_b
                b[1] -= cy*weight_b

        def simulate(self):
            dt = self.STEP
            drag = math.exp(-self.options["damping"] * dt)
            gravity = self.options["gravity"] * dt * dt
            solve = self.solve_constraints
            for index in tuple(self.active_chains):
                anchor, nodes, links, bends, spans = self.chains[index]
                for node in nodes:
                    x, y, old_x, old_y = node[0], node[1], node[2], node[3]
                    vx = max(-12.0, min(12.0, (x-old_x)*drag))
                    vy = max(-12.0, min(12.0, (y-old_y)*drag))
                    node[0], node[1], node[2], node[3] = x+vx, y+vy+gravity, x, y
                # A weak two-edge bending constraint suppresses tiny zigzags;
                # actual short segments still bend and receive mouse impulses.
                bend_pass, span_pass, forward, backward = self.solvers[index]
                solve(bend_pass)
                for iteration in range(10):
                    solve(span_pass, tension_only=True)
                    # Alternating sweep direction avoids favoring one end.
                    solve(forward if iteration % 2 == 0 else backward)
                quiet = all((node[0]-node[2])**2 + (node[1]-node[3])**2
                    < self.SLEEP_DISTANCE2 for node in nodes)
                self.active_chains[index] = self.active_chains[index]+1 if quiet else 0
                if self.active_chains[index] >= self.SLEEP_STEPS:
                    for node in nodes:
                        node[2], node[3] = node[0], node[1]
                    del self.active_chains[index]

        def draw_gpu_ropes(self, result, st, at):
            color = Color(self.rope_color).premultiplied
            width, height = result.get_size()
            for points, extent, rope in self.rope_models:
                data = tuple((node[0], node[1]) for node in points)
                data += (data[-1],) * (CURTAIN_ROPE_POINTS-len(data))
                # Reuse the static Model/mesh. Dynamic uniforms belong to a
                # fresh parent Render so cached child renders cannot go stale.
                layer = renpy.Render(width, height)
                layer.add_uniform("u_lintools_curtain_rope_points", data)
                layer.add_uniform("u_lintools_curtain_rope_range", extent)
                layer.add_uniform("u_lintools_curtain_rope_color", color)
                layer.blit(renpy.render(rope, width, height, st, at), (0, 0))
                result.blit(layer, (0, 0))

        def render(self, width, height, st, at):
            if self.active_chains and self.last_st is not None:
                self.accumulator += max(0.0, min(0.05, st-self.last_st))
            self.last_st = st
            while self.active_chains and self.accumulator >= self.STEP:
                self.simulate()
                self.accumulator -= self.STEP
            if not self.active_chains:
                self.accumulator = 0.0
            cell, margin = self.options["cell"], self.options["margin"]
            result = renpy.Render(int(self.columns*cell + margin*2),
                int(len(self.rows)*cell + margin*2))
            # Draw all ropes first so every character appears in front of its rope.
            self.draw_gpu_ropes(result, st, at)
            for node, before, after, tilted in self.glyphs:
                # Average the tangent around the glyph, as before.
                tilt = max(-28.0, min(28.0, -math.degrees(math.atan2(
                    after[0]-before[0], max(0.001, after[1]-before[1])))))
                if tilted.rotate != tilt:
                    tilted.rotate = tilt
                    tilted.update()
                glyph = renpy.render(tilted, int(cell*2), int(cell*2), st, at)
                w, h = glyph.get_size()
                result.blit(glyph, (node[0]-w/2.0, node[1]-h/2.0))
            if self.active_chains:
                renpy.redraw(self, 1.0/60.0)
            return result

        def impulse(self, node, vx, vy, weight):
            dt = self.STEP
            speed_x = (node[0]-node[2])/dt + vx*weight
            speed_y = (node[1]-node[3])/dt + vy*weight
            node[2] = node[0] - max(-900.0, min(900.0, speed_x))*dt
            node[3] = node[1] - max(-900.0, min(900.0, speed_y))*dt

        def event(self, ev, x, y, st):
            if ev.type != pygame.MOUSEMOTION:
                return None
            old_pointer = self.pointer
            self.pointer = (x, y, st)
            if old_pointer is None:
                return None
            elapsed = st-old_pointer[2]
            dx, dy = x-old_pointer[0], y-old_pointer[1]
            if elapsed < 0 or elapsed > 0.3 or math.hypot(dx, dy) < 0.5:
                return None
            elapsed = max(1.0/240.0, elapsed)
            speed = math.hypot(dx, dy)/elapsed
            scale = min(1.0, 1200.0/max(1.0, speed)) * self.options["strength"]
            vx, vy = dx/elapsed*scale, dy/elapsed*scale
            if scale <= 0.0:
                return None
            radius = self.options["radius"]
            left, right = min(old_pointer[0], x)-radius, max(old_pointer[0], x)+radius
            top, bottom = min(old_pointer[1], y)-radius, max(old_pointer[1], y)+radius
            was_active = bool(self.active_chains)
            changed = False
            for index, (anchor, nodes, links, bends, spans) in enumerate(self.chains):
                best = None
                previous = anchor
                for i, node in enumerate(nodes):
                    # Most segments cannot touch this mouse stroke. Reject
                    # their bounding boxes before the exact swept test.
                    if (max(previous[0], node[0]) < left or min(previous[0], node[0]) > right
                            or max(previous[1], node[1]) < top or min(previous[1], node[1]) > bottom):
                        previous = node
                        continue
                    distance, t = swept_rope_distance(old_pointer[:2], (x, y), previous, node)
                    if best is None or distance < best[0]:
                        best = (distance, t, i)
                    previous = node
                if best is None or best[0] >= radius:
                    continue
                distance, t, i = best
                force = (1.0-distance/radius) ** 2
                contact = nodes[i][7] - (1.0-t)*nodes[i][4]
                spread = max(self.options["radius"], self.options["cell"]*0.5)
                # A smooth kernel in rest-space keeps the response continuous
                # when contact crosses an edge boundary, at any subdivision.
                for node in nodes:
                    u = abs(node[7]-contact)/spread
                    if u < 1.0:
                        weight = (1.0-u*u)**2
                        self.impulse(node, vx, vy, force*weight)
                        changed = True
                        self.active_chains[index] = 0
            if changed:
                if not was_active:
                    self.last_st = st
                    self.accumulator = 0.0
                renpy.redraw(self, 0)
            return None

    def curtain_tag(tag, argument, contents):
        options, style_name = interactive_parameters(tag, argument, CURTAIN)
        chunks = []
        for kind, value in contents:
            if kind == renpy.TEXT_TEXT:
                chunks.append(value)
            elif kind == renpy.TEXT_PARAGRAPH:
                chunks.append("\n")
            else:
                raise ValueError("LinTools ltcurtain: use plain multiline text without nested tags.")
        return [(renpy.TEXT_DISPLAYABLE, CurtainText("".join(chunks), style=style_name, **options))]

    if "ltcurtain" in config.custom_text_tags or "ltcurtain" in config.self_closing_custom_text_tags:
        raise Exception("LinTools: text tag 'ltcurtain' is already registered.")
    config.custom_text_tags["ltcurtain"] = curtain_tag
