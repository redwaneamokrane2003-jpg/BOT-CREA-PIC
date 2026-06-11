from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from mocha_runner import WAN_REQUIRED_FILES, ensure_directories, load_config, resolve_mocha_ckpt


ROOT = Path(__file__).resolve().parent
MOCHA_REPO = "https://github.com/Orange-3DV-Team/MoCha.git"
WAN_REPO_ID = "Wan-AI/Wan2.1-T2V-14B"
MOCHA_REPO_ID = "Orange-3DV-Team/MoCha"


def print_section(title: str) -> None:
    print(f"\n== {title} ==")


def run(command: list[str], cwd: Path | None = None) -> int:
    print("$ " + subprocess.list2cmdline(command))
    process = subprocess.run(command, cwd=str(cwd) if cwd else None)
    return process.returncode


def torch_cuda_ready() -> bool:
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def install_torch_cuda() -> None:
    if torch_cuda_ready():
        print("PyTorch CUDA deja disponible.")
        return
    print("Installation de PyTorch CUDA 12.1 pour GPU NVIDIA...")
    run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "torch==2.5.1",
            "torchvision==0.20.1",
            "torchaudio==2.5.1",
            "--index-url",
            "https://download.pytorch.org/whl/cu121",
        ]
    )


def check_python() -> bool:
    ok = sys.version_info[:2] == (3, 10)
    print(f"Python detecte: {sys.version.split()[0]}")
    if not ok:
        print("Attention: MoCha demande Python 3.10.")
    return ok


def find_nvidia_smi() -> str | None:
    found = shutil.which("nvidia-smi")
    if found:
        return found
    windows_path = Path(r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe")
    if windows_path.exists():
        return str(windows_path)
    return None


def check_git() -> bool:
    git = shutil.which("git")
    if git:
        print(f"Git detecte: {git}")
        return True
    print("Git introuvable dans le PATH.")
    return False


def check_cuda() -> None:
    nvidia_smi = find_nvidia_smi()
    if nvidia_smi:
        try:
            result = subprocess.run(
                [
                    nvidia_smi,
                    "--query-gpu=name,memory.total,driver_version",
                    "--format=csv,noheader,nounits",
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            if result.stdout.strip():
                print("GPU NVIDIA:")
                print(result.stdout.strip())
        except Exception as exc:
            print(f"nvidia-smi detecte mais non exploitable: {exc}")
    else:
        print("nvidia-smi introuvable. Verifiez le pilote NVIDIA/CUDA.")

    try:
        import torch

        print(f"PyTorch: {torch.__version__}")
        print(f"CUDA PyTorch disponible: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            device = torch.cuda.current_device()
            props = torch.cuda.get_device_properties(device)
            total_gb = props.total_memory / (1024**3)
            print(f"GPU PyTorch: {props.name} - VRAM {total_gb:.1f} GB")
            if total_gb < 8:
                print("Profil RTX 3050/Nitro: utilisez Preview rapide, 416x240 et 17 frames.")
                print("Attention: Wan2.1 14B/MoCha peut encore echouer en VRAM meme avec ce profil.")
            elif total_gb < 24:
                print("Profil low-VRAM recommande. 24 GB+ reste preferable pour MoCha/Wan2.1 14B.")
    except ModuleNotFoundError:
        print("PyTorch n'est pas encore installe.")
    except Exception as exc:
        print(f"Verification PyTorch/CUDA impossible: {exc}")


def install_dependencies(mocha_repo_dir: Path) -> None:
    ui_requirements = ROOT / "requirements_ui.txt"
    if ui_requirements.exists():
        run([sys.executable, "-m", "pip", "install", "-r", str(ui_requirements)])
    run([sys.executable, "-m", "pip", "install", "huggingface_hub[cli]"])
    install_torch_cuda()

    mocha_requirements = mocha_repo_dir / "requirements.txt"
    if mocha_requirements.exists():
        run([sys.executable, "-m", "pip", "install", "-r", str(mocha_requirements)])
    else:
        print(f"requirements.txt MoCha introuvable: {mocha_requirements}")


def clone_mocha(mocha_repo_dir: Path) -> None:
    if mocha_repo_dir.exists():
        print(f"Repo MoCha deja present: {mocha_repo_dir}")
        return
    if not shutil.which("git"):
        print("Impossible de cloner: Git est introuvable.")
        return
    run(["git", "clone", MOCHA_REPO, str(mocha_repo_dir)])


def print_download_commands(config) -> None:
    print_section("Commandes de telechargement local")
    print(
        "huggingface-cli download "
        f"{WAN_REPO_ID} --local-dir {config.wan_dir}"
    )
    print(
        "huggingface-cli download "
        f'{MOCHA_REPO_ID} --include "preview/step18500.ckpt" --local-dir {config.mocha_ckpt_path.parent.parent}'
    )
    print("\nCes commandes telechargent les checkpoints localement. Elles ne lancent aucune API d'inference.")


def download_models(config) -> None:
    try:
        from huggingface_hub import snapshot_download
    except ModuleNotFoundError:
        print("huggingface_hub absent. Installez requirements_ui.txt puis relancez.")
        return

    snapshot_download(repo_id=WAN_REPO_ID, local_dir=str(config.wan_dir))
    snapshot_download(
        repo_id=MOCHA_REPO_ID,
        local_dir=str(config.mocha_ckpt_path.parent.parent),
        allow_patterns=["preview/step18500.ckpt"],
    )


def check_checkpoints(config) -> bool:
    print_section("Checkpoints")
    ok = True
    if not config.wan_dir.exists():
        print(f"Wan2.1 absent: {config.wan_dir}")
        ok = False
    else:
        for name in WAN_REQUIRED_FILES:
            path = config.wan_dir / name
            if path.exists():
                print(f"OK {path}")
            else:
                print(f"Manquant {path}")
                ok = False

    mocha_ckpt = resolve_mocha_ckpt(config)
    if mocha_ckpt.exists():
        print(f"OK {mocha_ckpt}")
    else:
        print(f"MoCha manquant: {config.mocha_ckpt_path} ou {config.mocha_ckpt_fallback}")
        ok = False
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description="Setup local gratuit pour MoCha")
    parser.add_argument("--clone-mocha", action="store_true", help="Clone le repo MoCha dans ./MoCha")
    parser.add_argument("--skip-install", action="store_true", help="N'installe pas les dependances pip")
    parser.add_argument("--download-models", action="store_true", help="Telecharge les checkpoints Hugging Face localement")
    parser.add_argument("--offline", action="store_true", help="Interdit les actions reseau du setup")
    args = parser.parse_args()

    config = load_config()
    print_section("Dossiers locaux")
    ensure_directories(config)
    for path in [
        config.wan_dir.parent,
        config.uploads_dir,
        config.uploads_dir / "videos",
        config.uploads_dir / "masks",
        config.uploads_dir / "references",
        config.outputs_dir,
        config.temp_dir,
    ]:
        path.mkdir(parents=True, exist_ok=True)
        print(path)

    print_section("Prerequis")
    python_ok = check_python()
    git_ok = check_git()
    check_cuda()

    if args.offline:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        print("Mode offline setup: clone, pip install et download sont ignores.")
    else:
        if args.clone_mocha:
            clone_mocha(config.mocha_repo_dir)
        elif not config.mocha_repo_dir.exists():
            print(f"Repo MoCha absent. Commande: git clone {MOCHA_REPO} {config.mocha_repo_dir}")

        if not args.skip_install:
            install_dependencies(config.mocha_repo_dir)

        if args.download_models:
            download_models(config)

    print_download_commands(config)
    checkpoints_ok = check_checkpoints(config)

    print_section("Resume")
    print(f"Python 3.10: {'OK' if python_ok else 'A corriger'}")
    print(f"Git: {'OK' if git_ok else 'A corriger'}")
    print(f"Checkpoints: {'OK' if checkpoints_ok else 'A telecharger'}")
    print("Lancement apres installation: python app.py")
    return 0 if python_ok and checkpoints_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
