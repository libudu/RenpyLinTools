"""Repel animation/input regressions runnable without the Ren'Py SDK."""
import ast
import math
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


class RepelTests(unittest.TestCase):
    def setUp(self):
        class Displayable:
            def __init__(self, **kwargs):
                pass

        class Render:
            def __init__(self, w, h):
                self.size = (w, h)

            def get_size(self):
                return self.size

            def subpixel_blit(self, child, offset):
                self.offset = offset

        self.renpy = SimpleNamespace(Displayable=Displayable, Render=Render,
            render=Mock(return_value=Render(42, 52)), redraw=Mock())
        source = (Path(__file__).resolve().parents[1] /
            "game/lintools/interactive_effects.rpy").read_text(encoding="utf-8")
        source = source.split("python in lintools_text:", 1)[1]
        source = "\n".join(line[4:] if line.startswith("    ") else line
            for line in source.splitlines())
        nodes = [node for node in ast.parse(source).body
            if getattr(node, "name", "") in {"InteractiveGlyph", "RepelGlyph"}]
        ns = dict(renpy=self.renpy, math=math, pygame=SimpleNamespace(MOUSEMOTION=1))
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "repel", "exec"), ns)
        self.glyph = ns["RepelGlyph"](Displayable(),
            dict(radius=110, distance=18, response=12))

    def render(self, st):
        return self.glyph.render(800, 600, st, st)

    def motion(self, x, y):
        self.assertIsNone(self.glyph.event(SimpleNamespace(type=1), x, y, 10))

    def test_idle_render_keeps_layout_alive_to_receive_first_mouse_event(self):
        self.render(0)
        self.renpy.redraw.assert_called_with(self.glyph, 1 / 60)
        self.assertEqual(self.glyph.offset, (0, 0))
        self.motion(15, 25)
        self.render(0.05)
        self.assertGreater(self.glyph.offset[0], 1)
        self.assertGreater(self.glyph.offset[1], 0)

    def test_nearer_pointer_repels_more_and_offset_stays_bounded(self):
        self.render(0)
        self.motion(0, 26)
        for i in range(1, 61):
            self.render(i / 60)
        near = math.hypot(*self.glyph.offset)
        self.assertLessEqual(near, 18)
        self.motion(-60, 26)
        for i in range(61, 121):
            self.render(i / 60)
        self.assertLess(math.hypot(*self.glyph.offset), near)

    def test_leaving_radius_returns_to_rest_and_keeps_listening(self):
        self.render(0)
        self.motion(15, 25)
        for i in range(1, 31):
            self.render(i / 60)
        self.motion(1000, 1000)
        for i in range(31, 151):
            self.render(i / 60)
        self.assertLess(math.hypot(*self.glyph.offset), 0.001)
        self.renpy.redraw.assert_called_with(self.glyph, 1 / 60)
        self.motion(15, 25)
        self.render(151 / 60)
        self.assertGreater(math.hypot(*self.glyph.offset), 1)

    def test_click_wheel_and_keyboard_events_pass_through(self):
        self.motion(15, 25)
        self.renpy.redraw.reset_mock()
        for event_type in (2, 3, 4):
            self.assertIsNone(self.glyph.event(SimpleNamespace(type=event_type), 0, 0, 10))
        self.assertEqual(self.glyph.mouse, (15, 25))
        self.renpy.redraw.assert_not_called()


if __name__ == "__main__":
    unittest.main()
