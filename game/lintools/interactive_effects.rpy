# Interactive/timed effects use embedded displayables rather than text shaders.
# Parsing only builds displayables. Dialogue advancement happens in event(),
# only when the displayable actually belongs to the current say screen's what.
init python in lintools_text:
    import unicodedata
    import re
    import renpy.pygame as pygame
    from renpy.text.text import Text

    SHATTER = {
        "hold": (None, 0.0, 0.0, 30.0),
        "stagger": (None, 0.18, 0.01, 3.0),
        "tremble": (None, 0.3, 0.0, 1.0),
        "tremble_distance": (None, 4.0, 0.0, 10.0),
        "duration": (None, 0.9, 0.05, 10.0),
        "distance": (None, 28.0, 0.0, 200.0),
        "gravity": (None, 180.0, 0.0, 2000.0),
        "impulse": (None, 48.0, 0.0, 100.0),
        "pieces": (None, 4.0, 2.0, 8.0),
        "variation": (None, 1.0, 0.0, 3.0),
        "rotation": (None, 3.0, 0.0, 45.0),
        "gap": (None, 0.6, 0.0, 8.0),
        "auto": (None, 1.0, 0.0, 1.0),
    }
    REPEL = {
        "radius": (None, 110.0, 1.0, 600.0),
        "distance": (None, 18.0, 0.0, 100.0),
        "response": (None, 12.0, 0.1, 60.0),
    }
    # Explicit formatting inside these tags is copied to every child Text.
    INLINE_STYLES = {"b", "i", "u", "s", "plain", "size", "font",
        "color", "alpha", "outlinecolor", "k", "kerning"}

    # Each shard samples the complete glyph, masked by the same Voronoi sites.
    # Local pixel coordinates keep the cells independent of texture atlas UVs
    # and make their edges correct for both narrow and wide glyphs.
    renpy.register_shader("lintools.voronoi_shard", variables="""
        uniform vec2 u_model_size;
        uniform vec2 u_lintools_shatter_sites[8];
        uniform float u_lintools_shatter_count;
        uniform float u_lintools_shatter_cell;
        uniform vec2 u_lintools_shatter_pivot;
        uniform float u_lintools_shatter_angle;
        uniform float u_lintools_shatter_gap;
        uniform float u_lintools_shatter_alpha;
        attribute vec4 a_position;
        varying vec2 v_lintools_shatter_position;
    """, vertex_50="""
        v_lintools_shatter_position = a_position.xy;
        vec2 l__pivot = u_lintools_shatter_pivot * u_model_size;
        vec2 l__offset = a_position.xy - l__pivot;
        float l__cos = cos(u_lintools_shatter_angle);
        float l__sin = sin(u_lintools_shatter_angle);
        gl_Position.xy = l__pivot + vec2(
            l__cos * l__offset.x - l__sin * l__offset.y,
            l__sin * l__offset.x + l__cos * l__offset.y);
    """, fragment_300="""
        vec2 l__point = v_lintools_shatter_position;
        vec2 l__site = u_lintools_shatter_pivot * u_model_size;
        vec2 l__delta = l__point - l__site;
        float l__distance = dot(l__delta, l__delta);
        float l__edge = 10000.0;
        for (int i = 0; i < 8; i++) {
            if (float(i) < u_lintools_shatter_count &&
                    abs(float(i) - u_lintools_shatter_cell) > 0.5) {
                vec2 l__other = u_lintools_shatter_sites[i] * u_model_size;
                vec2 l__difference = l__point - l__other;
                float l__rival = dot(l__difference, l__difference);
                // Deterministic ownership at an exactly shared boundary.
                if (l__rival < l__distance || (l__rival == l__distance &&
                        float(i) < u_lintools_shatter_cell)) {
                    discard;
                }
                l__edge = min(l__edge, (l__rival - l__distance) /
                    (2.0 * max(length(l__other - l__site), 0.001)));
            }
        }
        // Open only the internal fracture lines; preserve the glyph's outline.
        float l__coverage = smoothstep(-0.65, 0.0,
            l__edge - u_lintools_shatter_gap * 0.5);
        gl_FragColor *= l__coverage * u_lintools_shatter_alpha;
    """)

    def shatter_noise(seed):
        """Stable local variation without consuming the game's random state."""
        value = math.sin(seed * 12.9898 + 78.233) * 43758.5453
        return value - math.floor(value)

    def shatter_sites(index, count):
        """Spread a few sites across the glyph, with irregular, repeatable cuts."""
        turn = shatter_noise(index * 97 + 3) * math.tau
        sites = []
        for cell in range(count):
            seed = index * 97 + cell * 43
            angle = turn + cell * 2.399963229728653
            radius = 0.4 * math.sqrt((cell + 0.5) / count)
            sites.append((
                0.5 + math.cos(angle) * radius + (shatter_noise(seed + 11) - 0.5) * 0.07,
                0.5 + math.sin(angle) * radius + (shatter_noise(seed + 29) - 0.5) * 0.07))
        return tuple(sites)

    def clusters(text):
        """Keep combining marks, variation selectors and ZWJ sequences together."""
        current = ""
        for char in text:
            code = ord(char)
            attached = (unicodedata.combining(char) or char == "\u200d"
                or 0xfe00 <= code <= 0xfe0f or 0x1f3fb <= code <= 0x1f3ff
                or 0xe0100 <= code <= 0xe01ef or current.endswith("\u200d"))
            if current and not attached:
                yield current
                current = ""
            current += char
        if current:
            yield current

    def interactive_parameters(tag, argument, schema):
        style_name = "default"
        numeric = []
        found_style = False
        for part in argument.split(";") if argument else []:
            key, sep, value = part.strip().partition("=")
            if key.strip() == "style" and sep:
                if found_style or not re.fullmatch(r"[A-Za-z_]\w*", value.strip()):
                    raise ValueError("LinTools %s: invalid or duplicate style name." % tag)
                found_style = True
                style_name = value.strip()
            else:
                numeric.append(part)
        values = parse_parameters(tag, ";".join(numeric), schema)
        for key in ("pieces", "variation", "auto"):
            if key in values and values[key] != int(values[key]):
                raise ValueError("LinTools %s: %s must be an integer." % (tag, key))
        return values, style_name

    def styled_characters(contents, style_name):
        """Preserve local formatting and let the outer Text lay out the children."""
        active = []
        result = []
        for kind, value in contents:
            if kind == renpy.TEXT_TEXT:
                for char in clusters(value):
                    if char.isspace():
                        result.append((renpy.TEXT_TEXT, char))
                    else:
                        tokens = [(renpy.TEXT_TAG, t) for t in active]
                        tokens.append((renpy.TEXT_TEXT, char))
                        tokens.extend((renpy.TEXT_TAG, "/" + t.partition("=")[0])
                            for t in reversed(active))
                        result.append((renpy.TEXT_DISPLAYABLE, Text(tokens,
                            tokenized=True, substitute=False, slow=False, style=style_name)))
            elif kind == renpy.TEXT_PARAGRAPH:
                result.append((kind, value))
            elif kind == renpy.TEXT_TAG:
                name = value.partition("=")[0]
                if name.startswith("/"):
                    if not active or active[-1].partition("=")[0] != name[1:]:
                        raise ValueError("LinTools: interactive text has mismatched style tags.")
                    active.pop()
                elif name in INLINE_STYLES:
                    active.append(value)
                else:
                    raise ValueError("LinTools: tag %r is not supported inside ltshatter/ltrepel. "
                        "Use font/size/color/b/i tags inside, or style=your_style." % name)
            else:
                raise ValueError("LinTools: images/displayables cannot be nested in interactive text.")
        if active:
            raise ValueError("LinTools: close formatting tags inside the interactive effect.")
        return result

    class InteractiveGlyph(renpy.Displayable):
        def __init__(self, child, **kwargs):
            super(InteractiveGlyph, self).__init__(**kwargs)
            self.child = child

        def visit(self):
            return [self.child]

    class ShatterGlyph(InteractiveGlyph):
        def __init__(self, child, index, count, options):
            super(ShatterGlyph, self).__init__(child)
            self.index = index
            self.options = options
            # Vary the total cell count per glyph within a small bounded range.
            # Stable local randomness also keeps replay and rendering consistent.
            low = max(2, int(options["pieces"] - options["variation"]))
            high = min(8, int(options["pieces"] + options["variation"]))
            piece_count = low + int(shatter_noise(index * 97 + 131) * (high - low + 1))
            self.sites = shatter_sites(index, piece_count)
            self.begin = options["hold"] + (count - 1 - index) * options["stagger"]
            self.break_begin = self.begin + options["tremble"]
            self.finish = self.break_begin + options["duration"]
            self.origin = None
            self.played = 0.0

        def per_interact(self):
            renpy.redraw(self, 0)
            if self.options["auto"]:
                renpy.timeout(0.05)

        def elapsed(self, st):
            return max(0.0, st - (self.origin if self.origin is not None else st))

        def render(self, width, height, st, at):
            if self.origin is None or st < self.origin:
                self.origin = st
            child = renpy.render(self.child, width, height, st, at)
            w, h = child.get_size()
            result = renpy.Render(w, h)
            elapsed = self.elapsed(st)
            self.played = elapsed
            if elapsed <= self.begin:
                # Draw the intact glyph on its first frame, including hold=0.
                result.blit(child, (0, 0))
                renpy.redraw(self, self.begin - elapsed)
            elif elapsed < self.break_begin:
                # Build from half to full amplitude, then burst without easing out.
                tremble_time = elapsed - self.begin
                tremble_progress = tremble_time / self.options["tremble"]
                strength = self.options["tremble_distance"] * (0.5 + 0.5 * tremble_progress)
                phase = shatter_noise(self.index * 97 + 211) * math.tau
                dx = math.sin(tremble_time * math.tau * 4.75 + phase) * strength
                dy = math.sin(tremble_time * math.tau * 6.625 + phase) * strength * 0.6
                result.subpixel_blit(child, (dx, dy))
                renpy.redraw(self, 0)
            elif elapsed < self.finish:
                flight_time = elapsed - self.break_begin
                progress = flight_time / self.options["duration"]
                # Open the large cells first, while their ballistic motion builds.
                opening = min(1.0, progress / 0.35)
                opening = opening * opening * (3.0 - 2.0 * opening)
                fade = max(0.0, min(1.0, (progress - 0.75) / 0.25))
                alpha = 1.0 - fade * fade * (3.0 - 2.0 * fade)
                distance = self.options["distance"]
                fall = 0.5 * self.options["gravity"] * flight_time ** 2
                # Share one glyph texture between all cells; never shrink shards.
                source = renpy.Render(w, h)
                source.blit(child, (0, 0))
                source.mesh = True
                source.add_shader("renpy.texture")
                sites = self.sites + ((0.5, 0.5),) * (8 - len(self.sites))
                for cell, pivot in enumerate(self.sites):
                    seed = self.index * 97 + cell * 43
                    vx = (pivot[0] - 0.5) * 2.0 + (shatter_noise(seed + 67) - 0.5) * 0.25
                    vy = (pivot[1] - 0.5) * 2.0 + (shatter_noise(seed + 79) - 0.5) * 0.25
                    direction_length = max(0.001, math.hypot(vx, vy))
                    scatter = distance * (0.75 + shatter_noise(seed + 89) * 0.5) * progress
                    dx = vx / direction_length * scatter
                    dy = (vy / direction_length - 0.25) * scatter + fall
                    # A small one-off kick in any direction adds initial velocity,
                    # independent of radial scattering and gravity. It stays fixed
                    # for this shard, rather than applying new noise every frame.
                    kick_angle = shatter_noise(seed + 101) * math.tau
                    kick_speed = self.options["impulse"] * (0.5 + 0.5 * shatter_noise(seed + 113))
                    dx += math.cos(kick_angle) * kick_speed * flight_time
                    dy += math.sin(kick_angle) * kick_speed * flight_time
                    angle = (shatter_noise(seed + 53) * 2.0 - 1.0)
                    angle *= math.radians(self.options["rotation"]) * progress
                    shard = renpy.Render(w, h)
                    shard.blit(source, (0, 0))
                    shard.mesh = True
                    shard.add_shader("renpy.texture")
                    shard.add_shader("lintools.voronoi_shard")
                    for name, value in (
                            ("sites", sites), ("count", float(len(self.sites))),
                            ("cell", float(cell)), ("pivot", pivot),
                            ("angle", angle), ("gap", self.options["gap"] * opening),
                            ("alpha", alpha)):
                        shard.add_uniform("u_lintools_shatter_" + name, value)
                    result.blit(shard, (dx, dy))
                renpy.redraw(self, 0)
            return result

        def event(self, ev, x, y, st):
            if not self.options["auto"]:
                return None
            # Returning False completes the current dialogue interaction like nw.
            # Never advance a gallery, button, history screen or unrelated dialogue.
            what = renpy.get_displayable("say", "what")
            children = getattr(what, "displayables", None) or ()
            if self not in children:
                return None
            timed = [d for d in children if isinstance(d, ShatterGlyph) and d.options["auto"]]
            if timed and all(d.origin is not None and d.played >= d.finish for d in timed):
                return False
            renpy.timeout(0.03)
            return None

    class ReplayableShatterText(renpy.Displayable):
        """Own the rendered Text and rebuild its entire animation on replay."""
        def __init__(self, source, **text_properties):
            super(ReplayableShatterText, self).__init__()
            self.source = source
            self.text_properties = text_properties
            self.child = None
            self.started = None
            self.replay()

        def replay(self):
            # A Text may be copied when placed on a screen, and its parsed tokens
            # and layouts are cached. Resetting glyphs on the original Text can
            # therefore miss the instance that is actually being drawn.
            self.child = Text(self.source, slow=False, **self.text_properties)
            self.started = None
            renpy.redraw(self, 0)

        def visit(self):
            return [self.child]

        def render(self, width, height, st, at):
            if self.started is None or st < self.started:
                self.started = st
            local_st = max(0.0, st-self.started)
            child = renpy.render(self.child, width, height, local_st, local_st)
            w, h = child.get_size()
            result = renpy.Render(w, h)
            result.blit(child, (0, 0))
            return result

        def event(self, ev, x, y, st):
            local_st = max(0.0, st-self.started) if self.started is not None else 0.0
            return self.child.event(ev, x, y, local_st)

    class RepelGlyph(InteractiveGlyph):
        def __init__(self, child, options):
            super(RepelGlyph, self).__init__(child)
            self.options = options
            self.mouse = None
            self.offset = (0.0, 0.0)
            self.last_st = None

        def render(self, width, height, st, at):
            child = renpy.render(self.child, width, height, st, at)
            w, h = child.get_size()
            tx, ty = 0.0, 0.0
            if self.mouse is not None:
                dx, dy = w / 2.0 - self.mouse[0], h / 2.0 - self.mouse[1]
                distance = math.hypot(dx, dy)
                if distance < self.options["radius"]:
                    if distance < 0.001:
                        dx, dy, distance = 0.0, -1.0, 1.0
                    force = (1.0 - distance / self.options["radius"]) ** 2
                    tx = dx / distance * self.options["distance"] * force
                    ty = dy / distance * self.options["distance"] * force
            dt = 0.0 if self.last_st is None else max(0.0, min(0.1, st - self.last_st))
            self.last_st = st
            blend = 1.0 - math.exp(-self.options["response"] * dt)
            ox, oy = self.offset
            self.offset = (ox + (tx-ox)*blend, oy + (ty-oy)*blend)
            result = renpy.Render(w, h)
            result.blit(child, self.offset)
            if abs(tx-self.offset[0]) + abs(ty-self.offset[1]) > 0.02:
                renpy.redraw(self, 0)
            return result

        def event(self, ev, x, y, st):
            if ev.type == pygame.MOUSEMOTION:
                self.mouse = (x, y)
                renpy.redraw(self, 0)
            # Do not consume clicks, wheel events, rollback or dialogue keys.
            return None

    def interactive_tag(tag, argument, contents):
        options, style_name = interactive_parameters(tag, argument,
            SHATTER if tag == "ltshatter" else REPEL)
        characters = styled_characters(contents, style_name)
        count = sum(kind == renpy.TEXT_DISPLAYABLE for kind, value in characters)
        if not count:
            raise ValueError("LinTools %s: include at least one visible character." % tag)
        result = [(renpy.TEXT_TAG, "cps=0")]
        index = 0
        for kind, value in characters:
            if kind == renpy.TEXT_DISPLAYABLE:
                value = (ShatterGlyph(value, index, count, options) if tag == "ltshatter"
                    else RepelGlyph(value, options))
                index += 1
            result.append((kind, value))
        result.append((renpy.TEXT_TAG, "/cps"))
        return result

    for _tag in ("ltshatter", "ltrepel"):
        if _tag in config.custom_text_tags or _tag in config.self_closing_custom_text_tags:
            raise Exception("LinTools: text tag %r is already registered." % _tag)
        config.custom_text_tags[_tag] = interactive_tag
