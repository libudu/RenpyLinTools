# A resting text surface, disturbed only by vertical mouse strokes.
init 1 python in lintools_text:
    from builtins import list as _water_list

    WATER = {
        "strength": (None, 0.8, 0.0, 3.0),
        "speed": (None, 260.0, 40.0, 1000.0),
        "damping": (None, 1.2, 0.2, 12.0),
        "radius": (None, 44.0, 4.0, 160.0),
        "distance": (None, 48.0, 0.0, 100.0),
    }

    class WaterSurface(object):
        """One damped spring chain per laid-out line, shared by a tag's glyphs."""
        STEP = 1.0 / 240.0

        def __init__(self, options):
            self.options = options
            # Animation buffers must not record rollback on every physics step.
            self.glyphs = _water_list()
            self.links = _water_list()
            self.geometry_dirty = True
            self.active = False
            self.last_st = None
            self.accumulator = 0.0
            self.motion_key = None
            self.anchor = (0.0, 0.0)

        def reset(self):
            for glyph in self.glyphs:
                glyph.offset = glyph.velocity = 0.0
                glyph.pointer = None
            self.active = False
            self.accumulator = 0.0
            self.motion_key = None

        def prepare_links(self):
            self.links = _water_list()
            for left, right in zip(self.glyphs, self.glyphs[1:]):
                if left.center is None or right.center is None:
                    continue
                dx = right.center[0] - left.center[0]
                dy = abs(right.center[1] - left.center[1])
                # Wrapping and explicit newlines create separate water surfaces.
                if dx > 0.0 and dy < max(left.h, right.h) * 0.5:
                    stiffness = (self.options["speed"] / max(12.0, dx)) ** 2
                    self.links.append((left, right, stiffness))
            self.geometry_dirty = False

        def simulate(self):
            if self.geometry_dirty:
                self.prepare_links()
            dt = self.STEP
            # A weak restoring force returns even a uniformly displaced line
            # to its original baseline; tension carries the local disturbance.
            for glyph in self.glyphs:
                glyph.velocity -= glyph.offset * 9.0 * dt
            for left, right, stiffness in self.links:
                impulse = (right.offset - left.offset) * stiffness * dt
                left.velocity += impulse
                right.velocity -= impulse
            decay = math.exp(-self.options["damping"] * dt)
            limit = self.options["distance"]
            for glyph in self.glyphs:
                glyph.velocity *= decay
                glyph.offset += glyph.velocity * dt
                if abs(glyph.offset) > limit:
                    glyph.offset = max(-limit, min(limit, glyph.offset))
                    if glyph.offset * glyph.velocity > 0.0:
                        glyph.velocity = 0.0

        def advance(self, st):
            # Text may remeasure embedded displayables at st=0 when its layout
            # cache changes. A sizing pass must not rewind a moving surface.
            if st == 0.0 and self.last_st is not None:
                return
            if self.last_st is None:
                self.last_st = st
            elif st == self.last_st:
                return
            if st < self.last_st:
                self.reset()
            elapsed = max(0.0, min(0.1, st - self.last_st))
            self.last_st = st
            if not self.active:
                return
            self.accumulator += elapsed
            while self.accumulator >= self.STEP:
                self.simulate()
                self.accumulator -= self.STEP
            if all(abs(g.offset) < 0.02 and abs(g.velocity) < 0.05
                    for g in self.glyphs):
                self.reset()
            # Invalidate cached sibling renders as well as the glyph that
            # advanced the shared clock. Every glyph samples the same state.
            for glyph in self.glyphs:
                renpy.redraw(glyph, 0)

        def mouse(self, glyph, ev, x, y, st):
            key = (st, tuple(getattr(ev, "pos", ())), tuple(getattr(ev, "rel", ())))
            if key != self.motion_key:
                self.motion_key = key
                self.anchor = (x, y)
            # All glyphs receive the same event in their own local coordinates.
            # Their differences recover real layout positions, including spaces
            # and wrapping, without depending on Ren'Py Text internals or DPI.
            center = (self.anchor[0] - x + glyph.w * 0.5,
                self.anchor[1] - y + glyph.h * 0.5)
            if center != glyph.center:
                glyph.center = center
                self.geometry_dirty = True
            previous = glyph.pointer
            glyph.pointer = (x, y, st)
            if previous is None:
                return
            px, py, when = previous
            dt = st - when
            dx, dy = x - px, y - py
            # Ignore stale samples after a pause/menu and stationary/horizontal
            # motion. Sampling alone never wakes an otherwise still surface.
            if not 0.0 < dt <= 0.15 or abs(dy) < 0.001:
                return
            cx, cy = glyph.w * 0.5, glyph.h * 0.5 + glyph.offset
            t = max(0.0, min(1.0, ((cx-px)*dx + (cy-py)*dy) / (dx*dx + dy*dy)))
            distance = math.hypot(px + t*dx - cx, py + t*dy - cy)
            radius = self.options["radius"]
            if distance >= radius or not self.options["distance"]:
                return
            velocity = max(-1800.0, min(1800.0, dy / dt))
            impulse = velocity * self.options["strength"] * (1.0-distance/radius) ** 2
            # Integrate frequent samples so input strength is not tied to the
            # mouse polling rate. Swept contact catches fast surface crossings.
            impulse *= min(1.0, dt * 60.0)
            if abs(impulse) < 0.001:
                return
            glyph.velocity = max(-1800.0, min(1800.0, glyph.velocity + impulse))
            if not self.active:
                self.active = True
                # Text subtracts a glyph's typewriter start time for render(),
                # but forwards its own st to event(). Never mix those clocks.
                self.last_st = None
                self.accumulator = 0.0
                for sibling in self.glyphs:
                    renpy.redraw(sibling, 0)

    class WaterGlyph(InteractiveGlyph):
        def __init__(self, child, surface):
            super(WaterGlyph, self).__init__(child)
            self.surface = surface
            self.w = self.h = 0
            self.center = None
            self.pointer = None
            self.offset = self.velocity = 0.0
            surface.glyphs.append(self)

        def render(self, width, height, st, at):
            self.surface.advance(st)
            child = renpy.render(self.child, width, height, st, at)
            self.w, self.h = child.get_size()
            result = renpy.Render(self.w, self.h)
            result.subpixel_blit(child, (0.0, self.offset))
            if self.surface.active:
                renpy.redraw(self, 0)
            else:
                # Keep Text's layout cached while resting, so Text.event()
                # still forwards the mouse strokes that wake the water.
                # Physics remains asleep until a stroke applies an impulse.
                renpy.redraw(self, 1.0 / 60.0)
            return result

        def event(self, ev, x, y, st):
            if ev.type == pygame.MOUSEMOTION:
                self.surface.mouse(self, ev, x, y, st)
            return None

    def water_tag(tag, argument, contents):
        options, style_name = interactive_parameters(tag, argument, WATER)
        surface = WaterSurface(options)
        result = [(renpy.TEXT_TAG, "cps=0")]
        for kind, value in styled_characters(contents, style_name):
            if kind == renpy.TEXT_DISPLAYABLE:
                value = WaterGlyph(value, surface)
            result.append((kind, value))
        if not surface.glyphs:
            raise ValueError("LinTools ltwater: include at least one visible character.")
        result.append((renpy.TEXT_TAG, "/cps"))
        return result

    if "ltwater" in config.custom_text_tags or "ltwater" in config.self_closing_custom_text_tags:
        raise Exception("LinTools: text tag 'ltwater' is already registered.")
    config.custom_text_tags["ltwater"] = water_tag
