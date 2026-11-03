"""Elastic rope physics and drag lifecycle regressions without the Ren'Py SDK."""
import ast
import math
from pathlib import Path
from types import SimpleNamespace
import unicodedata
import unittest
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[1]


class Displayable:
    def __init__(self, *args, **kwargs):
        pass


class IgnoreEvent(Exception):
    pass


class Render:
    def __init__(self, w=40, h=48):
        self.size = (w, h)
        self.blits = []

    def get_size(self):
        return self.size

    def blit(self, child, position):
        self.blits.append((child, position))


def load_rope():
    renpy = SimpleNamespace(Displayable=Displayable, redraw=Mock(), Render=Render,
        render=Mock(side_effect=lambda *args: Render()), IgnoreEvent=IgnoreEvent,
        TEXT_TEXT=1, TEXT_DISPLAYABLE=2)
    pygame = SimpleNamespace(MOUSEMOTION=1, MOUSEBUTTONDOWN=2, MOUSEBUTTONUP=3,
        WINDOWFOCUSLOST=4, ACTIVEEVENT=5)
    ns = dict(math=math, unicodedata=unicodedata, renpy=renpy, pygame=pygame,
        Text=Displayable, _rope_list=list)
    for filename, names in (
        ("text_effects.rpy", {"parse_parameters"}),
        ("interactive_effects.rpy", {"clusters"}),
        ("elastic_rope_effect.rpy", {"ELASTIC_ROPE", "ElasticRopeText", "rope_tag"}),
    ):
        source = (ROOT / "game/lintools" / filename).read_text(encoding="utf-8")
        source = source.split("python in lintools_text:", 1)[1].split("\ninit ", 1)[0]
        source = "\n".join(line[4:] if line.startswith("    ") else line
            for line in source.splitlines())
        nodes = [node for node in ast.parse(source).body
            if getattr(node, "name", "") in names or isinstance(node, ast.Assign)
            and any(getattr(t, "id", "") in names for t in node.targets)]
        exec(compile(ast.Module(body=nodes, type_ignores=[]), filename, "exec"), ns)
    return ns


class ElasticRopeTests(unittest.TestCase):
    def setUp(self):
        self.ns = load_rope()
        self.rope = self.make()

    def make(self, text="拖住文字拉成弹力绳", **kwargs):
        rope = self.ns["ElasticRopeText"](text, **kwargs)
        rope.render(1920, 1080, 0, 0)
        return rope

    def send(self, kind, x, y, st=0, consumed=True, **kwargs):
        ev = SimpleNamespace(type=kind, button=1, **kwargs)
        if consumed:
            with self.assertRaises(IgnoreEvent):
                self.rope.event(ev, x, y, st)
        else:
            self.assertIsNone(self.rope.event(ev, x, y, st))

    def drag(self, dx=200, dy=130):
        self.send(2, 158, 24)
        self.send(1, 158+dx, 24+dy, 0.02, buttons=(1, 0, 0))

    def test_idle_does_not_schedule_and_unrelated_input_passes_through(self):
        self.ns["renpy"].redraw.assert_not_called()
        for kind in (1, 2, 3, 7):
            self.send(kind, -500, -500, consumed=False)
        self.assertFalse(self.rope.active)

    def test_drag_preserves_grab_offset_and_releases_outside_line(self):
        self.drag()
        self.assertEqual(self.rope.nodes[3][:2], [200, 130])
        self.assertEqual(self.rope.dragged, 3)
        self.send(3, 478, 424, 0.03)
        self.assertIsNone(self.rope.dragged)
        self.assertEqual(self.rope.nodes[3][:2], [320, 400])
        self.assertTrue(self.rope.active)

    def test_tension_propagates_then_overshoots_and_sleeps(self):
        self.drag()
        for frame in range(1, 61):
            self.rope.advance(frame/60)
        self.assertGreater(self.rope.nodes[2][0], 10)
        self.assertGreater(self.rope.nodes[2][1], 5)
        self.send(3, 358, 154, 1)
        overshot = False
        for frame in range(1, 2401):
            self.rope.advance(1+frame/60)
            overshot |= self.rope.nodes[3][0] < -1
        self.assertTrue(overshot)
        self.assertFalse(self.rope.active)
        self.assertTrue(all(n == [0, 0, 0, 0] for n in self.rope.nodes))
        self.ns["renpy"].redraw.reset_mock()
        self.rope.render(1920, 1080, 42, 42)
        self.ns["renpy"].redraw.assert_not_called()

    def test_interior_glyph_can_be_grabbed_in_both_directions(self):
        self.send(2, 3*46+10, 12)
        self.send(1, 3*46-90, -138, buttons=(1, 0, 0))
        self.assertEqual(self.rope.dragged, 3)
        self.assertEqual(self.rope.nodes[3][:2], [-100, -150])

    def test_focus_loss_and_missing_button_release_cancel_drag(self):
        for kind, kwargs in ((4, {}), (5, {"gain": 0}), (1, {"buttons": (0, 0, 0)})):
            self.rope = self.make()
            self.drag()
            self.send(kind, 358, 154, consumed=kind == 1, **kwargs)
            self.assertIsNone(self.rope.dragged)

    def test_moving_glyph_can_be_regrabbed_at_rendered_position(self):
        self.drag()
        self.send(3, 358, 154)
        self.send(2, 358, 154)
        self.assertEqual(self.rope.dragged, 3)
        self.assertEqual(self.rope.grab, (20, 24))

    def test_fixed_step_is_independent_of_frame_rate(self):
        results = []
        for fps in (30, 60, 120):
            self.rope = self.make()
            self.drag()
            self.send(3, 358, 154)
            for frame in range(fps+1):
                self.rope.advance(frame/fps)
                self.rope.advance(frame/fps)
            results.append([tuple(n) for n in self.rope.nodes])
        for result in results[1:]:
            for a, b in zip(results[0], result):
                for av, bv in zip(a, b):
                    self.assertAlmostEqual(av, bv, places=6)

    def test_extreme_parameters_are_bounded_and_finite(self):
        self.rope = self.make(stiffness=200, coupling=1000, damping=0.2, distance=1200)
        self.drag(10000, -10000)
        self.send(3, 10158, -9976)
        for frame in range(601):
            self.rope.advance(frame/60)
            for node in self.rope.nodes:
                self.assertLessEqual(math.hypot(*node[:2]), 1200.00001)
                self.assertTrue(all(math.isfinite(v) for v in node))

    def test_spaces_are_not_draggable_and_reset_clears_live_drag(self):
        self.rope = self.make("固 中字 定")
        self.send(2, 66, 24, consumed=False)
        self.drag()
        self.rope.reset()
        self.assertIsNone(self.rope.dragged)
        self.assertFalse(self.rope.active)
        self.assertTrue(all(n == [0, 0, 0, 0] for n in self.rope.nodes))

    def test_zero_distance_is_supported(self):
        self.rope = self.make(distance=0)
        self.drag()
        self.assertEqual(self.rope.nodes[3], [0, 0, 0, 0])
        self.send(3, 358, 154)
        for frame in range(61):
            self.rope.advance(frame/60)
        self.assertFalse(self.rope.active)

    def test_invalid_content_and_parameters_are_rejected(self):
        for text in ("", "　 ", "两\n行", "制\t表"):
            with self.assertRaises(ValueError):
                self.make(text)
        for options in (dict(damping=float("nan")), dict(coupling=1001), dict(distance=-1)):
            with self.assertRaises(ValueError):
                self.make(**options)

    def test_pause_is_capped_and_layout_probe_does_not_rewind(self):
        self.drag()
        self.send(3, 358, 154)
        self.rope.advance(1)
        before = [tuple(n) for n in self.rope.nodes]
        self.rope.advance(0)
        self.assertEqual([tuple(n) for n in self.rope.nodes], before)
        self.rope.advance(1000)
        self.assertTrue(all(math.isfinite(v) for n in self.rope.nodes for v in n))

    def test_both_endpoints_stay_exactly_fixed_during_drag_and_rebound(self):
        self.drag(400, -300)
        for frame in range(1, 61):
            self.rope.advance(frame/60)
            for index in self.rope.fixed:
                self.assertEqual(self.rope.nodes[index], [0, 0, 0, 0])
        self.assertGreater(abs(self.rope.nodes[2][1]), 1)
        self.assertGreater(abs(self.rope.nodes[4][1]), 1)
        self.send(3, 558, -276, 1)
        for frame in range(1, 301):
            self.rope.advance(1+frame/60)
            for index in self.rope.fixed:
                self.assertEqual(self.rope.nodes[index], [0, 0, 0, 0])

    def test_endpoints_cannot_be_grabbed(self):
        for index in self.rope.fixed:
            self.send(2, index*46+20, 24, consumed=False)
        self.assertIsNone(self.rope.dragged)
        self.assertFalse(self.rope.active)

    def test_leading_and_trailing_spaces_do_not_change_visible_anchors(self):
        self.rope = self.make("  固中定　")
        self.assertEqual(self.rope.fixed, {2, 4})
        for index in (0, 1, 2, 4, 5):
            self.send(2, index*46+20, 24, consumed=False)
        self.drag()
        self.assertEqual(self.rope.dragged, 3)
        for index in self.rope.fixed:
            self.assertEqual(self.rope.nodes[index], [0, 0, 0, 0])

    def test_one_or_two_visible_glyphs_are_all_fixed(self):
        for text in ("字", "两字", " 首 尾 "):
            self.rope = self.make(text)
            for index in range(len(text)):
                self.send(2, index*46+20, 24, consumed=False)
            self.assertIsNone(self.rope.dragged)
            self.assertFalse(self.rope.active)


if __name__ == "__main__":
    unittest.main()
