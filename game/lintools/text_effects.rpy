# Copy this directory into another project's game/. Requires Ren'Py 8.5+.
init -10 python in lintools_text:
    import math
    import renpy.exports as renpy
    import renpy.config as config
    _constant = True

    # Parameter: (uniform, default, minimum, maximum).
    EFFECTS = {
        "shake": ("lintools.shake", {
            "amplitude": ("u__amplitude", 3.0, 0.0, 100.0),
            "speed": ("u__speed", 20.0, 0.0, 120.0),
        }),
        "wave": ("wave", {
            "amplitude": ("u__amplitude", 6.0, 0.0, 100.0),
            "speed": ("u__frequency", 1.5, 0.0, 20.0),
            "wavelength": ("u__wavelength", 12.0, 1.0, 200.0),
        }),
        "tornado": ("lintools.tornado", {
            "radius": ("u__radius", 6.0, 0.0, 100.0),
            "speed": ("u__speed", 1.5, 0.0, 20.0),
            "spread": ("u__spread", 0.12, 0.0, 1.0),
        }),
        "rainbow": ("lintools.rainbow", {
            "speed": ("u__speed", 0.25, 0.0, 20.0),
            "spread": ("u__spread", 0.08, 0.0, 1.0),
            "saturation": ("u__saturation", 0.85, 0.0, 1.0),
        }),
    }
    TAGS = {"ltshake": "shake", "ltwave": "wave",
        "lttornado": "tornado", "ltrainbow": "rainbow"}

    def parse_parameters(name, argument, schema):
        """Validate plain numeric arguments; never evaluate expressions."""
        values = {key: info[1] for key, info in schema.items()}
        argument = argument.strip()
        if argument:
            if "=" not in argument:
                pairs = [(next(iter(schema)), argument)]
            else:
                pairs = []
                for item in argument.split(";"):
                    key, separator, value = item.strip().partition("=")
                    if not separator:
                        raise ValueError("LinTools %s: expected key=value;key=value." % name)
                    pairs.append((key.strip(), value.strip()))
            seen = set()
            for key, raw in pairs:
                if key not in schema:
                    raise ValueError("LinTools %s: unknown parameter %r. Choose: %s." % (
                        name, key, ", ".join(schema)))
                if key in seen:
                    raise ValueError("LinTools %s: duplicate parameter %r." % (name, key))
                seen.add(key)
                try:
                    value = float(raw)
                except (TypeError, ValueError):
                    raise ValueError("LinTools %s: %s must be a number." % (name, key))
                _, _, low, high = schema[key]
                if not math.isfinite(value) or not low <= value <= high:
                    raise ValueError("LinTools %s: %s must be between %g and %g." % (
                        name, key, low, high))
                values[key] = value
        return values

    def effect_spec(name, argument=""):
        if name not in EFFECTS:
            raise ValueError("LinTools: unknown effect %r. Choose: %s." % (
                name, ", ".join(EFFECTS)))
        shader, schema = EFFECTS[name]
        values = parse_parameters(name, argument, schema)
        return shader + "".join(":%s=%s" % (info[0], repr(values[key]))
            for key, info in schema.items())

    def combined_spec(argument):
        parts = []
        seen = set()
        for item in argument.split("|"):
            name, _, parameters = item.strip().partition(":")
            name = name.strip()
            if name in seen:
                raise ValueError("LinTools: effect %r occurs twice in one combination." % name)
            seen.add(name)
            parts.append(effect_spec(name, parameters))
        return "|".join(parts)

    def text_tag(tag, argument, contents):
        shader = combined_spec(argument) if tag == "ltfx" else effect_spec(TAGS[tag], argument)
        for kind, value in contents:
            if kind == renpy.TEXT_TAG:
                nested = value.partition("=")[0]
                if nested in TAGS or nested in ("ltfx", "shader", "ltshatter", "ltrepel", "ltcurtain"):
                    raise ValueError("LinTools: use {ltfx=wave|rainbow} for combined effects, "
                        "rather than nesting effect/shader tags.")
        return [(renpy.TEXT_TAG, "shader=" + shader)] + list(contents) + [
            (renpy.TEXT_TAG, "/shader")]

    # Independent per-glyph shake; never touches game RNG or rollback state.
    renpy.register_textshader(
        "lintools.shake",
        variables="""
            uniform float u__amplitude;
            uniform float u__speed;
            uniform float u_time;
            uniform float u_text_to_drawable;
            attribute float a_text_index;
        """,
        vertex_30="""
            float l__tick = floor(u_time * u__speed);
            vec2 l__seed = vec2(a_text_index * 17.13 + l__tick * 3.71,
                               a_text_index * 41.73 + l__tick * 7.19);
            vec2 l__noise = fract(sin(l__seed) * 43758.5453) * 2.0 - 1.0;
            gl_Position.xy += l__noise * u__amplitude * u_text_to_drawable;
        """,
        u__amplitude=3.0, u__speed=20.0, redraw=0.0,
    )
    # Orbit around the laid-out position; the glyph itself remains upright.
    renpy.register_textshader(
        "lintools.tornado",
        variables="""
            uniform float u__radius;
            uniform float u__speed;
            uniform float u__spread;
            uniform float u_time;
            uniform float u_text_to_drawable;
            attribute float a_text_index;
        """,
        vertex_45="""
            float l__angle = 6.28318530718 *
                (u_time * u__speed + a_text_index * u__spread);
            gl_Position.xy += vec2(cos(l__angle), sin(l__angle)) *
                u__radius * u_text_to_drawable;
        """,
        u__radius=6.0, u__speed=1.5, u__spread=0.12, redraw=0.0,
    )
    # Preserve premultiplied alpha and the host's outline/shadow colors.
    renpy.register_textshader(
        "lintools.rainbow",
        variables="""
            uniform float u__speed;
            uniform float u__spread;
            uniform float u__saturation;
            uniform float u_time;
            uniform float u_text_main;
            attribute float a_text_index;
            varying float v__hue;
        """,
        vertex_60="""
            v__hue = a_text_index * u__spread + u_time * u__speed;
        """,
        fragment_300="""
            if (u_text_main > 0.5) {
                vec3 l__rgb = clamp(abs(fract(v__hue +
                    vec3(0.0, 0.666666667, 0.333333333)) * 6.0 - 3.0) - 1.0,
                    0.0, 1.0);
                gl_FragColor.rgb = mix(vec3(1.0), l__rgb, u__saturation)
                    * gl_FragColor.a;
            }
        """,
        u__speed=0.25, u__spread=0.08, u__saturation=0.85, redraw=0.0,
    )
    for _tag in tuple(TAGS) + ("ltfx",):
        if _tag in config.custom_text_tags or _tag in config.self_closing_custom_text_tags:
            raise Exception("LinTools: text tag %r is already registered." % _tag)
        config.custom_text_tags[_tag] = text_tag

# Retain the host's explicit default; opt in otherwise for mixed plain/effect text.
init 100 python:
    if config.default_textshader is None:
        config.default_textshader = "typewriter"
