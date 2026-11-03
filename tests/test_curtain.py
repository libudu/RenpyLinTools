"""Physics and scheduling regressions, runnable without the Ren'Py SDK.

Run with: python -m unittest discover -s tests -v
Engine rendering and Ren'Py's list rewriting still require an SDK smoke test.
"""
import ast
import math
from pathlib import Path
import random
from types import SimpleNamespace
import unicodedata
import unittest
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[1]


class Displayable:
    def __init__(self, *args, **kwargs):
        pass


class Transform(Displayable):
    rotate = None

    def update(self):
        pass


class Render:
    def __init__(self, *args):
        self.size = tuple(args) if args else (42, 42)
        self.children = []
        self.uniforms = {}

    def get_size(self):
        return self.size

    def blit(self, *args):
        self.children.append(args)

    def add_uniform(self, name, value):
        self.uniforms[name] = value


class Model(Displayable):
    def __init__(self, **kwargs):
        self.uniforms = {}

    def grid_mesh(self, *args):
        self.grid = args
        return self

    def shader(self, name):
        return self

    def uniform(self, name, value):
        self.uniforms[name] = value
        return self


def load_curtain():
    renpy = SimpleNamespace(Displayable=Displayable, Render=Render,
        redraw=Mock(), render=Mock(side_effect=lambda *args: Render()))
    ns = dict(math=math, unicodedata=unicodedata, Text=Displayable,
        Transform=Transform, renpy=renpy, pygame=SimpleNamespace(MOUSEMOTION=1),
        _curtain_list=list, _curtain_dict=dict, Model=Model,
        Color=lambda value: SimpleNamespace(premultiplied=(0.4, 0.5, 0.5, 1.0)))
    for filename, names in (
        ("text_effects.rpy", {"parse_parameters"}),
        ("interactive_effects.rpy", {"clusters"}),
        ("curtain_effect.rpy", {"CURTAIN", "CURTAIN_ROPE_POINTS", "point_segment",
            "swept_rope_distance", "CurtainText"}),
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


class CurtainTests(unittest.TestCase):
    def setUp(self):
        self.ns = load_curtain()
        self.cls = self.ns["CurtainText"]
        self.motion = SimpleNamespace(type=1)

    def stroke(self, curtain, a, b, st=0.0):
        curtain.event(self.motion, *a, st)
        curtain.event(self.motion, *b, st+0.02)

    def test_batch_solver_matches_original_weighted_constraints(self):
        rng = random.Random(217)
        for stiffness, tension_only in ((1.0, False), (1.0, True), (0.04, False)):
            for fixed in (True, False):
                original = [[rng.uniform(-50, 50), rng.uniform(-50, 50), 0, 0, 0, None,
                    0.0 if fixed and i == 0 else rng.uniform(0.5, 8)] for i in range(8)]
                batched = [node[:] for node in original]
                prepared = self.cls.prepare_constraints(
                    [(a, b, 8.0) for a, b in zip(batched, batched[1:])], stiffness)
                for _ in range(10):
                    for a, b in zip(original, original[1:]):
                        dx, dy = b[0]-a[0], b[1]-a[1]
                        length = math.hypot(dx, dy)
                        if length < 0.000001 or tension_only and length <= 8.0:
                            continue
                        correction = stiffness*(length-8.0)/(length*(a[6]+b[6]))
                        a[0] += dx*correction*a[6]
                        a[1] += dy*correction*a[6]
                        b[0] -= dx*correction*b[6]
                        b[1] -= dy*correction*b[6]
                    self.cls.solve_constraints(prepared, tension_only)
                for a, b in zip(original, batched):
                    self.assertAlmostEqual(a[0], b[0], places=9)
                    self.assertAlmostEqual(a[1], b[1], places=9)

    def test_idle_does_not_simulate_or_schedule_frames(self):
        curtain = self.cls("甲乙\n丙丁")
        curtain.simulate = Mock(wraps=curtain.simulate)
        curtain.render(800, 600, 0, 0)
        curtain.render(800, 600, 100, 100)
        curtain.simulate.assert_not_called()
        self.ns["renpy"].redraw.assert_not_called()

    def test_only_touched_chain_wakes_and_anchors_stay_fixed(self):
        curtain = self.cls("甲乙丙\n丁戊己")
        anchors = [(chain[0][0], chain[0][1]) for chain in curtain.chains]
        untouched = [node[:] for node in curtain.chains[1][1]]
        self.stroke(curtain, (80, 130), (145, 130))
        self.assertEqual(set(curtain.active_chains), {0})
        curtain.simulate()
        self.assertEqual(untouched, curtain.chains[1][1])
        self.assertEqual(anchors, [(c[0][0], c[0][1]) for c in curtain.chains])

    def test_fast_stroke_wakes_every_crossed_column(self):
        curtain = self.cls("甲乙丙\n丁戊己")
        self.stroke(curtain, (20, 130), (300, 130))
        self.assertEqual(set(curtain.active_chains), {0, 1, 2})

    def test_unrelated_mouse_motion_and_disabled_strength_stay_idle(self):
        for curtain, a, b in ((self.cls("甲乙"), (0, 0), (40, 0)),
                (self.cls("甲乙", strength=0), (20, 110), (300, 110))):
            self.stroke(curtain, a, b)
            self.assertFalse(curtain.active_chains)
        self.ns["renpy"].redraw.assert_not_called()

    def test_waking_after_long_idle_does_not_catch_up_idle_time(self):
        curtain = self.cls("甲乙\n丙丁")
        curtain.render(800, 600, 0, 0)
        self.stroke(curtain, (80, 130), (145, 130), st=100)
        curtain.simulate = Mock(wraps=curtain.simulate)
        curtain.render(800, 600, 100.02, 100.02)
        curtain.simulate.assert_not_called()
        curtain.render(800, 600, 100.02+1/60, 100.02+1/60)
        self.assertLessEqual(curtain.simulate.call_count, 2)

    def test_settling_sleeps_then_mouse_wakes_again(self):
        curtain = self.cls("甲\n乙\n丙")
        self.stroke(curtain, (70, 160), (150, 160))
        for _ in range(120*15):
            curtain.simulate()
            if not curtain.active_chains:
                break
        self.assertFalse(curtain.active_chains)
        self.ns["renpy"].redraw.reset_mock()
        curtain.render(800, 600, 20, 20)
        self.ns["renpy"].redraw.assert_not_called()
        self.stroke(curtain, (70, 160), (150, 160), st=20)
        self.assertTrue(curtain.active_chains)

    def test_transform_objects_survive_motion_and_reset(self):
        curtain = self.cls("甲乙\n丙丁")
        transforms = [c for c in curtain.visit() if isinstance(c, Transform)]
        self.stroke(curtain, (20, 130), (300, 130))
        curtain.render(800, 600, 0.05, 0.05)
        self.assertTrue(any(t.rotate != 0 for t in transforms))
        curtain.reset()
        curtain.render(800, 600, 0.1, 0.1)
        self.assertFalse(curtain.active_chains)
        self.assertEqual(transforms, [c for c in curtain.visit() if isinstance(c, Transform)])
        self.assertTrue(all(t.rotate == 0 for t in transforms))

    def test_full_demo_eventually_stops_requesting_frames(self):
        script = (ROOT / "game/script.rpy").read_text(encoding="utf-8")
        source = ast.literal_eval(next(line.split(" = ", 1)[1]
            for line in script.splitlines()
            if line.startswith("define lintools_demo_curtain_source =")))
        curtain = self.cls(source)
        self.stroke(curtain, (10, 300), (790, 300))
        self.assertEqual(len(curtain.active_chains), len(curtain.chains))
        for _ in range(120*15):
            curtain.simulate()
            if not curtain.active_chains:
                break
        self.assertFalse(curtain.active_chains)
        self.ns["renpy"].redraw.reset_mock()
        curtain.render(1920, 1080, 20, 20)
        self.ns["renpy"].redraw.assert_not_called()

    def test_gpu_drawing_preserves_simulation_and_glyph_state(self):
        curtain = self.cls("甲乙\n丙丁")
        self.stroke(curtain, (20, 130), (300, 130))
        curtain.simulate()
        before = [node[:4] for chain in curtain.chains for node in chain[1]]
        active = dict(curtain.active_chains)
        transforms = curtain.visit()
        curtain.render(800, 600, 0.02, 0.02)
        curtain.render(800, 600, 0.02, 0.02)
        self.assertEqual(before, [n[:4] for c in curtain.chains for n in c[1]])
        self.assertEqual(active, curtain.active_chains)
        self.assertEqual(transforms, curtain.visit())

    def test_long_gpu_rope_chunks_cover_all_segments_and_share_join_neighbors(self):
        curtain = self.cls("\n".join(["甲"]*20), subdivisions=16)
        result = curtain.render(800, 1600, 0, 0)
        models = [call.args[0] for call in self.ns["renpy"].render.call_args_list
            if isinstance(call.args[0], Model)]
        layers = [child for child, _ in result.children
            if "u_lintools_curtain_rope_points" in child.uniforms]
        self.assertGreater(len(models), 1)
        self.assertEqual(len(models), len(layers))
        joined = []
        previous = None
        for model, layer in zip(models, layers):
            data = layer.uniforms["u_lintools_curtain_rope_points"]
            first, count, last = map(int, layer.uniforms["u_lintools_curtain_rope_range"])
            visible = list(data[first:first+count])
            self.assertEqual(len(data), 64)
            self.assertEqual(model.grid, (2, count))
            self.assertLessEqual(first+count-1, last)
            if previous:
                self.assertEqual(previous[-1], visible[0])
                self.assertEqual(previous[-2], data[first-1])
                joined.extend(visible[1:])
            else:
                joined.extend(visible)
            previous = visible
        anchor, nodes, *_ = curtain.chains[0]
        self.assertEqual(joined, [(n[0], n[1]) for n in [anchor]+nodes])

    def test_gpu_drawing_is_used_by_default(self):
        curtain = self.cls("甲乙")
        curtain.draw_gpu_ropes = Mock()
        curtain.render(800, 600, 0, 0)
        curtain.draw_gpu_ropes.assert_called_once()

    def test_gpu_reuses_models_but_refreshes_uniforms_without_scheduling_idle_frames(self):
        curtain = self.cls("甲\n乙")
        models = tuple(item[2] for item in curtain.rope_models)
        first = curtain.render(800, 600, 0, 0)
        original_data = first.children[0][0].uniforms["u_lintools_curtain_rope_points"]
        curtain.chains[0][1][0][0] += 5.0
        second = curtain.render(800, 600, 1, 1)
        updated_data = second.children[0][0].uniforms["u_lintools_curtain_rope_points"]
        self.assertEqual(models, tuple(item[2] for item in curtain.rope_models))
        self.assertNotEqual(original_data, updated_data)
        self.assertEqual(updated_data[1][0], original_data[1][0]+5.0)
        self.assertTrue(all(not model.uniforms for model in models))
        self.ns["renpy"].redraw.assert_not_called()


if __name__ == "__main__":
    unittest.main()
