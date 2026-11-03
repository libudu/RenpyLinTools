"""Profile GPU curtain ropes in a temporary Ren'Py project (Windows SDK)."""
import argparse
import ast
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", type=Path, required=True)
    parser.add_argument("--frames", type=int, default=120)
    parser.add_argument("--subdivisions", type=int, default=8, choices=range(2, 17))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.frames < 30:
        parser.error("--frames must be at least 30 (the first 10 are warm-up).")
    launcher = args.sdk / "renpy.exe"
    if not launcher.is_file():
        parser.error("--sdk must contain renpy.exe.")
    root = Path(__file__).resolve().parents[1]
    project = Path(tempfile.mkdtemp(prefix="lintools_curtain_gpu_"))
    game = project / "game"
    (game / "lintools").mkdir(parents=True)
    for source in (root / "game/lintools").glob("*.rpy"):
        shutil.copy2(source, game / "lintools" / source.name)
    shutil.copy2(root / "game/SourceHanSansLite.ttf", game / "SourceHanSansLite.ttf")
    shutil.copy2(root / "tools/curtain_benchmark.rpy", game / "script.rpy")
    script = (root / "game/script.rpy").read_text(encoding="utf-8")
    source = ast.literal_eval(next(line.split(" = ", 1)[1] for line in script.splitlines()
        if line.startswith("define lintools_demo_curtain_source =")))
    (project / "settings.json").write_text(json.dumps(dict(source=source,
        frames=args.frames, subdivisions=args.subdivisions)), encoding="utf-8")
    print(f"Temporary project: {project}", flush=True)
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = subprocess.SW_HIDE
    child = subprocess.Popen([str(launcher), str(project)], startupinfo=startup)
    deadline = time.monotonic() + max(90, args.frames / 60 * 12)
    try:
        while child.poll() is None:
            error = project / "traceback.txt"
            if error.is_file():
                raise RuntimeError(error.read_text(encoding="utf-8-sig"))
            if time.monotonic() > deadline:
                raise TimeoutError(f"Benchmark timed out. Inspect {project}")
            time.sleep(0.25)
    finally:
        if child.poll() is None:
            child.terminate()
            child.wait(timeout=10)
    metrics = project / "metrics.json"
    if not metrics.is_file():
        raise RuntimeError(f"No metrics produced (exit {child.returncode}). Inspect {project}")
    report = json.loads(metrics.read_text(encoding="utf-8"))
    if not report["renderer"].get("models") or any(
            not r["gpu_draws"] for r in report["runs"]):
        raise RuntimeError("GPU model rendering unavailable.")
    if not report["identical_physics"]:
        raise RuntimeError("Repeated runs ended at different physics states.")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(metrics, args.output)
    runs = report["runs"]
    print("GPU", json.dumps({key:
        sum(run[key]["median"] for run in runs) / len(runs)
        for key in ("cpu_render_ms", "physics_ms", "ropes_ms", "frame_interval_ms")}))
    print(f"Identical physics: {report['identical_physics']}")
    print(f"Metrics: {metrics}\nScreenshot: {project / 'gpu.png'}")


if __name__ == "__main__":
    main()
