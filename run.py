from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
VENV_DIR = ROOT / ".venv"


def venv_python() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def is_running_from_venv() -> bool:
    executable = Path(sys.executable).resolve()
    expected = venv_python().resolve()
    return executable == expected or sys.prefix != getattr(sys, "base_prefix", sys.prefix)


def run_command(command: list[str], check: bool = True) -> int:
    print("$ " + subprocess.list2cmdline(command), flush=True)
    result = subprocess.run(command, cwd=str(ROOT))
    if check and result.returncode != 0:
        raise SystemExit(result.returncode)
    return result.returncode


def python310_launcher() -> list[str] | None:
    if sys.version_info[:2] == (3, 10):
        return None

    if os.environ.get("MOCHA_TRIED_PY310") == "1":
        return None

    candidates = []
    if os.name == "nt" and shutil.which("py"):
        candidates.append(["py", "-3.10"])
    if shutil.which("python3.10"):
        candidates.append(["python3.10"])

    for candidate in candidates:
        probe = subprocess.run(
            [*candidate, "-c", "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 10) else 1)"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if probe.returncode == 0:
            return candidate
    return None


def ensure_venv(args: list[str]) -> None:
    if is_running_from_venv():
        return

    launcher = python310_launcher()
    if launcher:
        env = os.environ.copy()
        env["MOCHA_TRIED_PY310"] = "1"
        command = [*launcher, str(Path(__file__).resolve()), *args]
        raise SystemExit(subprocess.call(command, cwd=str(ROOT), env=env))

    python_path = venv_python()
    if not python_path.exists():
        print("Creation de l'environnement local .venv...", flush=True)
        run_command([sys.executable, "-m", "venv", str(VENV_DIR)])

    command = [str(python_path), str(Path(__file__).resolve()), *args]
    raise SystemExit(run_command(command, check=False))


def ensure_ui_dependencies(force: bool = False) -> None:
    missing = []
    imports = {
        "gradio": "gradio",
        "yaml": "PyYAML",
        "PIL": "pillow",
        "pandas": "pandas",
        "imageio": "imageio",
    }
    for module_name, package_name in imports.items():
        try:
            __import__(module_name)
        except Exception:
            missing.append(package_name)

    if force or missing:
        requirements = ROOT / "requirements_ui.txt"
        run_command([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
        run_command([sys.executable, "-m", "pip", "install", "-r", str(requirements)])


def run_setup(download_models: bool, skip_install: bool) -> None:
    command = [sys.executable, str(ROOT / "setup_mocha_local.py"), "--clone-mocha"]
    if download_models:
        command.append("--download-models")
    if skip_install:
        command.append("--skip-install")
    run_command(command, check=False)


def print_runtime_note() -> None:
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info[:2] != (3, 10):
        print(
            f"Attention: Python {version} detecte. MoCha recommande Python 3.10. "
            "Pour un repo GitHub plug-and-play, lance avec py -3.10 run.py --setup --download-models.",
            flush=True,
        )


def launch_app(host: str, port: int) -> int:
    env = os.environ.copy()
    env["MOCHA_SERVER_NAME"] = host
    env["MOCHA_SERVER_PORT"] = str(port)
    print(f"Lancement local: http://{host}:{port}", flush=True)
    return subprocess.call([sys.executable, str(ROOT / "app.py")], cwd=str(ROOT), env=env)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MoCha Local plug-and-play launcher")
    parser.add_argument("--setup", action="store_true", help="Prepare .venv, dependances, repo MoCha et dossiers")
    parser.add_argument("--download-models", action="store_true", help="Telecharge les checkpoints Hugging Face localement")
    parser.add_argument("--skip-install", action="store_true", help="N'installe pas les dependances MoCha pendant le setup")
    parser.add_argument("--no-launch", action="store_true", help="Prepare seulement, ne lance pas Gradio")
    parser.add_argument("--host", default="127.0.0.1", help="Adresse locale Gradio")
    parser.add_argument("--port", type=int, default=7860, help="Port local Gradio")
    args = parser.parse_args(argv)

    raw_args = list(argv if argv is not None else sys.argv[1:])
    ensure_venv(raw_args)
    print_runtime_note()

    ensure_ui_dependencies(force=args.setup and not args.skip_install)
    if args.setup:
        run_setup(download_models=args.download_models, skip_install=args.skip_install)

    if args.no_launch:
        print("Preparation terminee.", flush=True)
        return 0

    return launch_app(args.host, args.port)


if __name__ == "__main__":
    raise SystemExit(main())
