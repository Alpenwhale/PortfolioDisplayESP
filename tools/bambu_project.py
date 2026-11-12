"""Print-ready Bambu Studio projects for both cases, one plate each.

Needs Bambu Studio installed and build/case/*.stl from tools/case.py.
Writes 3d/bambu/<variant>_case.3mf (settings included, not sliced).
Run: uv run tools/bambu_project.py [--slice] [--machine NAME] [--process NAME] [--filament NAME]
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

STUDIO = Path(r"C:\Program Files\Bambu Studio")
PROFILES = STUDIO / "resources" / "profiles" / "BBL"
ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build" / "case"
OUT = ROOT / "3d" / "bambu"
VARIANTS = ("tft", "oled")

# defaults, any Bambu system preset name works
MACHINE = "Bambu Lab P2S 0.4 nozzle"
PROCESS = "0.20mm Standard @BBL P2S"
FILAMENT = "Bambu PETG HF @BBL P2S 0.4 nozzle"

# our changes on top of the system process
PROCESS_SET = {
    "curr_bed_type": "Textured PEI Plate",  # PETG is not allowed on the default plate
    "wall_loops": "3",
    "sparse_infill_density": "15%",
    "enable_support": "1",
    "support_type": "tree(auto)",
    "skirt_loops": "3",           # longer purge before the parts
    "skirt_distance": "4",
    "skirt_height": "1",
    "brim_type": "auto_brim",     # tall thin parts get a brim
    "reduce_crossing_wall": "1",  # no travel moves across the open window
    "seam_position": "back",
    "thick_bridges": "1",         # window top is a long bridge
}
FILAMENT_SET = {"default_filament_colour": "#000000", "filament_colour": "#000000"}


def find(kind: str, name: str) -> Path:
    """Preset file by name, filament presets sit in subfolders."""
    hits = list((PROFILES / kind).rglob(f"{name}.json"))
    if not hits:
        sys.exit(f"preset not found: {kind}/{name}")
    return hits[0]


def resolve(kind: str, name: str) -> dict:
    """Preset with its inherits chain merged in."""
    data = json.loads(find(kind, name).read_text(encoding="utf-8"))
    parent = data.pop("inherits", "")
    if parent:
        base = resolve(kind, parent)
        base.update(data)
        data = base
    return data


def write(kind: str, name: str, extra: dict) -> Path:
    """Resolved preset as json in build/case/."""
    data = resolve(kind, name)
    for key, val in extra.items():
        old = data.get(key)
        data[key] = [val] * len(old) if isinstance(old, list) else val
    data["name"] = name
    path = BUILD / f"{kind}.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def export(variant: str, settings: str, filament: Path, sliced: bool) -> Path:
    """Let Bambu Studio arrange one plate and export it."""
    # warmup first, so it is printed first on each layer
    parts = [BUILD / "warmup.stl", BUILD / f"{variant}_shell.stl"]
    parts += [p for p in (BUILD / f"{variant}_{n}.stl" for n in ("cover", "panel", "roof")) if p.exists()]
    out = BUILD / f"{variant}_case.gcode.3mf" if sliced else OUT / f"{variant}_case.3mf"
    cmd = [str(STUDIO / "bambu-studio.exe"), "--arrange", "1",
           "--load-settings", settings, "--load-filaments", str(filament),
           *(["--slice", "0"] if sliced else []),
           "--export-3mf", str(out), *map(str, parts)]
    subprocess.run(cmd, check=True, cwd=BUILD)  # cli drops result.json in cwd
    return out


def main() -> None:
    """Resolve presets once, export every variant."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--machine", default=MACHINE)
    ap.add_argument("--process", default=PROCESS)
    ap.add_argument("--filament", default=FILAMENT)
    ap.add_argument("--slice", action="store_true", help="also slice into build/case/ to check")
    a = ap.parse_args()

    # presets
    OUT.mkdir(parents=True, exist_ok=True)
    m = write("machine", a.machine, {})
    p = write("process", a.process, PROCESS_SET)
    f = write("filament", a.filament, FILAMENT_SET)

    for v in VARIANTS:
        print(export(v, f"{m};{p}", f, a.slice))


if __name__ == "__main__":
    main()
