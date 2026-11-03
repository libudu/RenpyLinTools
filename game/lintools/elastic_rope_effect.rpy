# A draggable elastic text rope with fixed ends. No third-party dependencies.
init 1 python in lintools_text:
    from builtins import list as _rope_list

    ELASTIC_ROPE = {
        "size": (None, 48.0, 12.0, 120.0),
        "spacing": (None, 6.0, 0.0, 80.0),
        "stiffness": (None, 18.0, 1.0, 200.0),
        "coupling": (None, 380.0, 0.0, 1000.0),
        "damping": (None, 2.8, 0.2, 20.0),
        "distance": (None, 600.0, 0.0, 1200.0),
    }

    class ElasticRopeText(renpy.Displayable):
        """An unwrapped line whose first and last visible glyphs stay fixed."""
        STEP = 1.0 / 240.0

        def __init__(self, text, size=48, spacing=6, stiffness=18, coupling=380,
                damping=2.8, distance=600, style="default", color="#f7dfa0",
                **properties):
            super(ElasticRopeText, self).__init__(**properties)
            self.options = parse_parameters("ltrope", ";".join("%s=%s" % item
                for item in dict(size=size, spacing=spacing, stiffness=stiffness,
                    coupling=coupling, damping=damping, distance=distance).items()), ELASTIC_ROPE)
            if any(char in text for char in "\r\n\t"):
                raise ValueError("LinTools ltrope: use a single line without tabs.")
            self.characters = tuple(clusters(text))
            visible = [i for i, char in enumerate(self.characters) if not char.isspace()]
            if not visible:
                raise ValueError("LinTools ltrope: include at least one visible character.")
            self.fixed = frozenset((visible[0], visible[-1]))
            self.letters = tuple(Text(char.replace("{", "{{"), substitute=False,
                slow=False, style=style, size=int(self.options["size"]), color=color)
                for char in self.characters)
            self.geometry = ()
            self.line_size = (0, 0)
            # Mutable animation buffers intentionally bypass rollback tracking.
            self.nodes = _rope_list(_rope_list((0.0, 0.0, 0.0, 0.0))
                for char in self.characters)  # dx, dy, vx, vy
            self.dragged = None
            self.grab = (0.0, 0.0)
            self.target = (0.0, 0.0)
            self.active = False
            self.last_st = None
            self.accumulator = 0.0
            self.quiet_steps = 0

        def visit(self):
            return list(self.letters)

        def reset(self):
            for node in self.nodes:
                node[:] = (0.0, 0.0, 0.0, 0.0)
            self.dragged = None
            self.active = False
            self.last_st = None
            self.accumulator = 0.0
            self.quiet_steps = 0
            renpy.redraw(self, 0)

        def release(self):
            # The held glyph has zero velocity. Its spring tension launches the
            # rebound, avoiding event-rate-dependent release velocity spikes.
            self.dragged = None
            self.quiet_steps = 0

        def pin(self):
            for index in self.fixed:
                self.nodes[index][:] = (0.0, 0.0, 0.0, 0.0)
            if self.dragged is not None:
                self.nodes[self.dragged][:] = (*self.target, 0.0, 0.0)

        def simulate(self):
            self.pin()
            forces = _rope_list()
            stiffness, coupling = self.options["stiffness"], self.options["coupling"]
            decay = math.exp(-self.options["damping"] * self.STEP)
            for index, node in enumerate(self.nodes):
                ax, ay = -stiffness*node[0], -stiffness*node[1]
                for other in (index-1, index+1):
                    if 0 <= other < len(self.nodes):
                        neighbor = self.nodes[other]
                        ax += coupling*(neighbor[0]-node[0])
                        ay += coupling*(neighbor[1]-node[1])
                forces.append((ax, ay))
            limit = self.options["distance"]
            for index, (node, force) in enumerate(zip(self.nodes, forces)):
                if index in self.fixed or index == self.dragged:
                    continue
                node[2] = (node[2]+force[0]*self.STEP)*decay
                node[3] = (node[3]+force[1]*self.STEP)*decay
                node[0] += node[2]*self.STEP
                node[1] += node[3]*self.STEP
                length = math.hypot(node[0], node[1])
                if length > limit:
                    scale = limit / length
                    node[0] *= scale
                    node[1] *= scale
                    # Remove outward velocity at the displacement boundary.
                    outward = (node[2]*node[0]+node[3]*node[1]) / max(limit*limit, 1e-9)
                    if outward > 0:
                        node[2] -= outward*node[0]
                        node[3] -= outward*node[1]
            quiet = self.dragged is None and all(
                math.hypot(n[0], n[1]) < 0.03 and math.hypot(n[2], n[3]) < 0.15
                for n in self.nodes)
            self.quiet_steps = self.quiet_steps+1 if quiet else 0
            if self.quiet_steps >= 60:
                for node in self.nodes:
                    node[:] = (0.0, 0.0, 0.0, 0.0)
                self.active = False

        def advance(self, st):
            if self.last_st is None:
                self.last_st = st
            # Text layout/prediction may measure with st=0. Never rewind live
            # physics in response to such a measurement.
            if st < self.last_st:
                return
            elapsed = min(0.1, st-self.last_st)
            self.last_st = st
            if not self.active:
                self.accumulator = 0.0
                return
            self.accumulator += elapsed
            while self.accumulator + 1e-10 >= self.STEP and self.active:
                self.accumulator -= self.STEP
                self.simulate()

        def render(self, width, height, st, at):
            renders = [renpy.render(letter, width, height, st, at) for letter in self.letters]
            line_height = max(r.get_size()[1] for r in renders)
            x, geometry = 0.0, []
            for glyph in renders:
                w, h = glyph.get_size()
                geometry.append((x, (line_height-h)/2.0, w, h))
                x += w + self.options["spacing"]
            self.geometry = tuple(geometry)
            self.line_size = (int(math.ceil(x-self.options["spacing"])), line_height)
            self.advance(st)
            result = renpy.Render(*self.line_size)
            # Draw the grabbed glyph last, above any overlapping neighbors.
            order = [i for i in range(len(renders)) if i != self.dragged]
            if self.dragged is not None:
                order.append(self.dragged)
            for i in order:
                ox, oy, w, h = self.geometry[i]
                node = self.nodes[i]
                result.blit(renders[i], (ox+node[0], oy+node[1]))
            if self.active:
                renpy.redraw(self, 1.0/60.0)
            return result

        def move_target(self, x, y):
            ox, oy, w, h = self.geometry[self.dragged]
            dx, dy = x-ox-self.grab[0], y-oy-self.grab[1]
            length = math.hypot(dx, dy)
            scale = min(1.0, self.options["distance"]/max(length, 1e-9))
            self.target = (dx*scale, dy*scale)
            self.pin()
            renpy.redraw(self, 0)

        def event(self, ev, x, y, st):
            # Losing window focus or releasing outside the window must never
            # leave a glyph attached to the cursor on return.
            lost_focus = ((ev.type == getattr(pygame, "WINDOWFOCUSLOST", -1)) or
                (ev.type == getattr(pygame, "ACTIVEEVENT", -2)
                    and not getattr(ev, "gain", 1)))
            if lost_focus:
                self.release()
                return None
            if self.dragged is not None:
                if ev.type == pygame.MOUSEMOTION:
                    if getattr(ev, "buttons", (1,))[0]:
                        self.move_target(x, y)
                    else:
                        self.release()
                    raise renpy.IgnoreEvent()
                if ev.type == pygame.MOUSEBUTTONUP and ev.button == 1:
                    self.move_target(x, y)
                    self.release()
                    raise renpy.IgnoreEvent()
                if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                    raise renpy.IgnoreEvent()
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                # Reverse order matches rendering when moving glyphs overlap.
                for i in reversed(range(len(self.geometry))):
                    ox, oy, w, h = self.geometry[i]
                    node = self.nodes[i]
                    gx, gy = x-ox-node[0], y-oy-node[1]
                    if (i not in self.fixed and not self.characters[i].isspace()
                            and 0 <= gx < w and 0 <= gy < h):
                        if not self.active:
                            self.last_st = st
                            self.accumulator = 0.0
                        self.dragged = i
                        self.grab = (gx, gy)
                        self.target = (node[0], node[1])
                        self.active = True
                        self.quiet_steps = 0
                        self.pin()
                        renpy.redraw(self, 0)
                        raise renpy.IgnoreEvent()
            return None

    def rope_tag(tag, argument, contents):
        options, style_name = interactive_parameters(tag, argument, ELASTIC_ROPE)
        if any(kind != renpy.TEXT_TEXT for kind, value in contents):
            raise ValueError("LinTools ltrope: use plain single-line text without nested tags.")
        return [(renpy.TEXT_DISPLAYABLE, ElasticRopeText(
            "".join(value for kind, value in contents), style=style_name, **options))]

    if "ltrope" in config.custom_text_tags or "ltrope" in config.self_closing_custom_text_tags:
        raise Exception("LinTools: text tag 'ltrope' is already registered.")
    config.custom_text_tags["ltrope"] = rope_tag

# A separate layer also escapes viewport clipping and parent screen ordering.
# menu_clear keeps this foreground effect out of save/load and game menus.
init 100 python in lintools_text:
    renpy.add_layer("lintools_rope", above=config.layers[-1], menu_clear=True)

screen lintools_rope(rope, position=(0.5, 0.5)):
    layer "lintools_rope"
    zorder 1000
    add rope align position
    on "hide" action Function(rope.release)
