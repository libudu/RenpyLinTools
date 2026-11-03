# Loaded only by benchmark_curtain.py in an isolated temporary project.
define config.name = "LinTools curtain benchmark"
define config.screen_width = 1200
define config.screen_height = 900
define config.sound = False
define config.save_directory = None
define config.autosave_on_quit = False
define config.default_text_cps = 0

style default:
    font "SourceHanSansLite.ttf"

init 2 python:
    import hashlib
    import json
    from pathlib import Path
    import statistics
    import time

    class CurtainBenchmark(lintools_text.CurtainText):
        def __init__(self, source, frames, subdivisions):
            super(CurtainBenchmark, self).__init__(source, subdivisions=subdivisions)
            self.samples = []
            self.times = []
            self.limit = frames
            self.physics_ms = self.ropes_ms = 0.0
            self.gpu_draws = 0
            motion = lintools_text.pygame.event.Event(lintools_text.pygame.MOUSEMOTION)
            self.event(motion, 10, 300, 0.0)
            self.event(motion, 790, 300, 0.1)

        def simulate(self):
            begin = time.perf_counter()
            super(CurtainBenchmark, self).simulate()
            self.physics_ms += (time.perf_counter()-begin)*1000

        def draw_gpu_ropes(self, result, st, at):
            self.gpu_draws += 1
            begin = time.perf_counter()
            super(CurtainBenchmark, self).draw_gpu_ropes(result, st, at)
            self.ropes_ms += (time.perf_counter()-begin)*1000

        def render(self, width, height, st, at):
            measuring = len(self.samples) < self.limit
            # Exactly two unchanged physics steps per sample, independent of
            # vsync/frame drops. Both runs follow the same trajectory.
            self.last_st = st
            self.accumulator = 2*self.STEP if measuring else 0.0
            self.physics_ms = self.ropes_ms = 0.0
            begin = time.perf_counter()
            result = super(CurtainBenchmark, self).render(width, height, st, at)
            total = (time.perf_counter()-begin)*1000
            if measuring:
                self.samples.append((total, self.physics_ms, self.ropes_ms))
                self.times.append(st)
                renpy.redraw(self, 0)
            return result

        def report(self):
            samples = self.samples[10:]
            def stats(values):
                return dict(median=statistics.median(values),
                    mean=statistics.mean(values), p95=sorted(values)[int(len(values)*0.95)])
            state = tuple(tuple(tuple(node[:4]) for node in chain[1]) for chain in self.chains)
            intervals = [(b-a)*1000 for a, b in zip(self.times[10:], self.times[11:]) if b > a]
            return dict(gpu_draws=self.gpu_draws, frames=len(samples),
                cpu_render_ms=stats([s[0] for s in samples]),
                physics_ms=stats([s[1] for s in samples]),
                ropes_ms=stats([s[2] for s in samples]),
                frame_interval_ms=stats(intervals),
                state_sha256=hashlib.sha256(repr(state).encode("utf-8")).hexdigest())

        def finish_if_ready(self):
            if len(self.samples) >= self.limit:
                renpy.end_interaction(True)

screen curtain_benchmark_view(curtain):
    add Solid("#101823")
    add curtain align (0.5, 0.5)
    timer 0.02 repeat True action Function(curtain.finish_if_ready, _update_screens=False)

label start:
    python:
        settings = json.loads(Path(config.basedir, "settings.json").read_text(encoding="utf-8"))
        results = []
    $ run_index = 0
    while run_index < 2:
        $ curtain = CurtainBenchmark(settings["source"], settings["frames"], settings["subdivisions"])
        call screen curtain_benchmark_view(curtain)
        $ results.append(curtain.report())
        if run_index == 0:
            $ renpy.screenshot(str(Path(config.basedir, "gpu.png")))
        $ run_index += 1
    python:
        output = dict(renderer=dict(renpy.get_renderer_info()),
            subdivisions=settings["subdivisions"],
            particles=sum(len(c[1]) for c in curtain.chains),
            identical_physics=len(set(r["state_sha256"] for r in results)) == 1,
            runs=results)
        Path(config.basedir, "metrics.json").write_text(json.dumps(output, indent=2), encoding="utf-8")
    $ renpy.quit(status=0)
