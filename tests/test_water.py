"""Water propagation/input regressions runnable without the Ren'Py SDK."""
import ast
import math
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[1]


class Displayable:
    def __init__(self, *args, **kwargs):
        pass


def load_water():
    renpy = SimpleNamespace(Displayable=Displayable, redraw=Mock(),
        TEXT_TAG=1, TEXT_TEXT=2, TEXT_DISPLAYABLE=3)
    ns = dict(math=math, renpy=renpy, pygame=SimpleNamespace(MOUSEMOTION=1),
        _water_list=list)
    for filename, names in (
        ("text_effects.rpy", {"parse_parameters"}),
        ("interactive_effects.rpy", {"InteractiveGlyph"}),
        ("water_effect.rpy", {"WATER", "WaterSurface", "WaterGlyph", "water_tag"}),
    ):
        source = (ROOT / "game/lintools" / filename).read_text(encoding="utf-8")
        source = source.split("python in lintools_text:", 1)[1].split("\ninit ", 1)[0]
        source = "\n".join(line[4:] if line.startswith("    ") else line
            for line in source.splitlines())
        nodes = [node for node in ast.parse(source).body
            if getattr(node, "name", "") in names or isinstance(node, ast.Assign)
            and any(getattr(target, "id", "") in names for target in node.targets)]
        exec(compile(ast.Module(body=nodes, type_ignores=[]), filename, "exec"), ns)
    return ns


class WaterTests(unittest.TestCase):
    def setUp(self):
        self.ns = load_water()
        self.options = self.ns["parse_parameters"]("ltwater", "", self.ns["WATER"])

    def surface(self, count=15, **options):
        surface = self.ns["WaterSurface"](dict(self.options, **options))
        for i in range(count):
            glyph = self.ns["WaterGlyph"](Displayable(), surface)
            glyph.w = glyph.h = 40
            glyph.center = (20 + i*40, 20)
        return surface

    def motion(self, surface, x, y, st):
        ev = SimpleNamespace(type=1, pos=(x, y), rel=(0, 1))
        for i, glyph in enumerate(surface.glyphs):
            self.assertIsNone(glyph.event(ev, x-i*40, y, st))

    def test_initial_and_horizontal_stationary_motion_remain_at_rest(self):
        surface = self.surface()
        for frame in range(60):
            surface.advance(frame/60)
        self.motion(surface, 100, 20, 1.0)
        self.motion(surface, 400, 20, 1.02)
        self.motion(surface, 400, 20, 1.04)
        self.assertFalse(surface.active)
        self.assertTrue(all(g.offset == g.velocity == 0 for g in surface.glyphs))
        self.ns["renpy"].redraw.assert_not_called()

    def test_fast_crossing_between_events_is_detected_and_uses_vertical_sign(self):
        for start, end, sign in ((-100, 140, 1), (140, -100, -1)):
            surface = self.surface()
            self.motion(surface, 300, start, 0.0)
            self.motion(surface, 300, end, 0.02)
            self.assertTrue(surface.active)
            self.assertGreater(surface.glyphs[7].velocity * sign, 0)
            self.assertEqual(surface.glyphs[0].velocity, 0)

    def test_faster_stroke_has_stronger_impulse(self):
        def kick(speed):
            surface = self.surface()
            self.motion(surface, 300, 20-speed*0.02, 0)
            self.motion(surface, 300, 20, 0.02)
            return surface.glyphs[7].velocity
        self.assertGreater(kick(800), kick(200)*3.9)

    def test_disturbance_propagates_to_both_sides(self):
        surface = self.surface()
        surface.glyphs[7].velocity = 300
        surface.active = True
        surface.advance(0)
        surface.advance(0.1)
        self.assertGreater(abs(surface.glyphs[6].offset), 0.1)
        self.assertAlmostEqual(surface.glyphs[6].offset, surface.glyphs[8].offset)
        self.assertLess(abs(surface.glyphs[0].offset), 0.001)
        for frame in range(21):
            surface.advance(0.1 + (frame+1)/60)
        self.assertGreater(abs(surface.glyphs[4].offset), 0.1)

    def test_separate_lines_do_not_exchange_waves(self):
        surface = self.surface(8)
        for i, glyph in enumerate(surface.glyphs[4:]):
            glyph.center = (20+i*40, 100)
        surface.glyphs[3].velocity = 300
        surface.active = True
        for frame in range(121):
            surface.advance(frame/60)
        self.assertTrue(all(g.offset == g.velocity == 0 for g in surface.glyphs[4:]))

    def test_decay_returns_exactly_to_rest_and_stops_scheduling(self):
        surface = self.surface()
        surface.glyphs[7].velocity = 600
        surface.active = True
        surface.advance(0)
        for frame in range(1, 2401):
            surface.advance(frame/60)
        self.assertFalse(surface.active)
        self.assertTrue(all(g.offset == g.velocity == 0 for g in surface.glyphs))
        self.ns["renpy"].redraw.reset_mock()
        surface.advance(41)
        self.ns["renpy"].redraw.assert_not_called()

    def test_fixed_step_and_shared_clock_are_independent_of_render_order(self):
        results = []
        for fps in (30, 60, 120):
            surface = self.surface()
            surface.glyphs[7].velocity = 300
            surface.active = True
            for frame in range(fps+1):
                surface.advance(frame/fps)
                # Additional glyph renders at the same timestamp do not step.
                surface.advance(frame/fps)
            results.append([g.offset for g in surface.glyphs])
        for result in results[1:]:
            for a, b in zip(results[0], result):
                self.assertAlmostEqual(a, b, places=6)

    def test_extreme_settings_remain_bounded_and_finite(self):
        surface = self.surface(speed=1000, damping=0.2, distance=100)
        for i, glyph in enumerate(surface.glyphs):
            glyph.center = (i*2, 20)
            glyph.velocity = 1800 if i % 2 else -1800
        surface.active = True
        for frame in range(601):
            surface.advance(frame/60)
            self.assertTrue(all(math.isfinite(g.velocity) and abs(g.offset) <= 100
                for g in surface.glyphs))

    def test_stale_sample_and_zero_strength_do_not_wake_surface(self):
        surface = self.surface(strength=0)
        self.motion(surface, 300, 0, 0)
        self.motion(surface, 300, 20, 0.02)
        self.assertFalse(surface.active)
        surface = self.surface()
        self.motion(surface, 300, 0, 0)
        self.motion(surface, 300, 20, 10)
        self.assertFalse(surface.active)

    def test_input_clock_does_not_reset_glyphs_after_a_typewritten_prefix(self):
        surface = self.surface()
        surface.advance(0.5)
        self.motion(surface, 300, 0, 10.0)
        self.motion(surface, 300, 20, 10.02)
        surface.advance(0.52)
        surface.advance(0.54)
        self.assertTrue(surface.active)
        self.assertGreater(surface.glyphs[7].offset, 0.1)

    def test_text_layout_measurement_does_not_rewind_animation(self):
        surface = self.surface()
        surface.glyphs[7].velocity = 300
        surface.active = True
        surface.advance(1.0)
        surface.advance(1.02)
        before = surface.glyphs[7].offset
        surface.advance(0.0)
        self.assertEqual(surface.glyphs[7].offset, before)
        self.assertTrue(surface.active)
        surface.advance(1.04)
        self.assertNotEqual(surface.glyphs[7].offset, before)

    def test_geometry_respects_spaces_and_wrapped_event_coordinates(self):
        surface = self.surface(4)
        positions = ((0, 0), (40, 0), (160, 0), (0, 80))
        for (gx, gy), glyph in zip(positions, surface.glyphs):
            ev = SimpleNamespace(type=1, pos=(100, 100))
            glyph.event(ev, 100-gx, 100-gy, 0)
        surface.prepare_links()
        self.assertEqual(len(surface.links), 2)
        self.assertAlmostEqual(surface.links[1][2], (self.options["speed"]/120)**2)

    def test_clicks_and_keyboard_are_not_consumed(self):
        surface = self.surface(1)
        for event_type in (2, 3, 4):
            self.assertIsNone(surface.glyphs[0].event(SimpleNamespace(type=event_type), 0, 0, 0))
        self.assertFalse(surface.active)

    def test_invalid_options_are_rejected(self):
        for argument in ("speed=nan", "speed=1001", "damping=0", "radius=-1",
                "strength=4", "distance=101", "speed=200;speed=300", "unknown=1"):
            with self.subTest(argument=argument), self.assertRaises(ValueError):
                self.ns["parse_parameters"]("ltwater", argument, self.ns["WATER"])


if __name__ == "__main__":
    unittest.main()
