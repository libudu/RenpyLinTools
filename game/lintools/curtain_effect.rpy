# A multiline text curtain: independent, anchored chains with mouse impulses.
init 1 python in lintools_text:
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
                anchor = [x, anchor_y, x, anchor_y, 0.0, None, 0.0, 0.0]
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
                        node = [x, y, x, y, length/count, glyph, inverse_mass, rest]
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
            self.last_st = None
            self.accumulator = 0.0
            self.pointer = None

        def visit(self):
            return self.letters

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
            renpy.redraw(self, 0)

        @staticmethod
        def constrain(a, b, rest, stiffness=1.0, tension_only=False):
            dx, dy = b[0]-a[0], b[1]-a[1]
            length = math.hypot(dx, dy)
            if length < 0.000001 or (tension_only and length <= rest):
                return
            correction = stiffness*(length-rest)/(length*(a[6]+b[6]))
            cx, cy = dx*correction, dy*correction
            a[0] += cx*a[6]
            a[1] += cy*a[6]
            b[0] -= cx*b[6]
            b[1] -= cy*b[6]

        def simulate(self):
            dt = self.STEP
            drag = math.exp(-self.options["damping"] * dt)
            gravity = self.options["gravity"] * dt * dt
            for anchor, nodes, links, bends, spans in self.chains:
                for node in nodes:
                    x, y, old_x, old_y = node[:4]
                    vx = max(-12.0, min(12.0, (x-old_x)*drag))
                    vy = max(-12.0, min(12.0, (y-old_y)*drag))
                    node[:4] = [x+vx, y+vy+gravity, x, y]
                # A weak two-edge bending constraint suppresses tiny zigzags;
                # actual short segments still bend and receive mouse impulses.
                for a, b, rest in bends:
                    self.constrain(a, b, rest, stiffness=0.04)
                for iteration in range(10):
                    for a, b, rest in reversed(spans):
                        self.constrain(a, b, rest, tension_only=True)
                    # Alternating sweep direction avoids favoring one end.
                    for a, b, rest in (links if iteration % 2 == 0 else reversed(links)):
                        self.constrain(a, b, rest)

        def render(self, width, height, st, at):
            if self.last_st is not None:
                self.accumulator += max(0.0, min(0.05, st-self.last_st))
            self.last_st = st
            while self.accumulator >= self.STEP:
                self.simulate()
                self.accumulator -= self.STEP
            cell, margin = self.options["cell"], self.options["margin"]
            result = renpy.Render(int(self.columns*cell + margin*2),
                int(len(self.rows)*cell + margin*2))
            canvas = result.canvas()
            # Draw all ropes first so every character appears in front of its rope.
            for anchor, nodes, links, bends, spans in self.chains:
                previous = anchor
                for node in nodes:
                    canvas.line(self.rope_color,
                        (int(round(previous[0])), int(round(previous[1]))),
                        (int(round(node[0])), int(round(node[1]))), 1)
                    previous = node
            for anchor, nodes, links, bends, spans in self.chains:
                for i, node in enumerate(nodes):
                    if node[5] is not None:
                        # Average the tangent around the glyph rather than
                        # letting a single short edge make the letter jitter.
                        reach = max(1, int(self.options["subdivisions"])//2)
                        before = nodes[i-reach] if i >= reach else anchor
                        after = nodes[min(len(nodes)-1, i+reach)]
                        tilt = -math.degrees(math.atan2(after[0]-before[0],
                            max(0.001, after[1]-before[1])))
                        tilted = Transform(node[5], rotate=max(-28.0, min(28.0, tilt)),
                            subpixel=True)
                        glyph = renpy.render(tilted, int(cell*2), int(cell*2), st, at)
                        w, h = glyph.get_size()
                        result.blit(glyph, (node[0]-w/2.0, node[1]-h/2.0))
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
            for anchor, nodes, links, bends, spans in self.chains:
                best = None
                previous = anchor
                for i, node in enumerate(nodes):
                    distance, t = swept_rope_distance(old_pointer[:2], (x, y), previous, node)
                    if best is None or distance < best[0]:
                        best = (distance, t, i)
                    previous = node
                distance, t, i = best
                if distance >= self.options["radius"]:
                    continue
                force = (1.0-distance/self.options["radius"]) ** 2
                contact = nodes[i][7] - (1.0-t)*nodes[i][4]
                spread = max(self.options["radius"], self.options["cell"]*0.5)
                # A smooth kernel in rest-space keeps the response continuous
                # when contact crosses an edge boundary, at any subdivision.
                for node in nodes:
                    u = abs(node[7]-contact)/spread
                    if u < 1.0:
                        weight = (1.0-u*u)**2
                        self.impulse(node, vx, vy, force*weight)
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
