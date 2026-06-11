from __future__ import annotations

import argparse
import csv
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Generator, Iterable


ROOT = Path(__file__).resolve().parent
CSV_COLUMNS = ["source_video", "source_mask", "reference_1", "reference_2"]
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
OUTPUT_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv"}
HEARTBEAT_LINE = "__MOCHA_PROGRESS_HEARTBEAT__"


WAN_REQUIRED_FILES = [
    "diffusion_pytorch_model-00001-of-00006.safetensors",
    "diffusion_pytorch_model-00002-of-00006.safetensors",
    "diffusion_pytorch_model-00003-of-00006.safetensors",
    "diffusion_pytorch_model-00004-of-00006.safetensors",
    "diffusion_pytorch_model-00005-of-00006.safetensors",
    "diffusion_pytorch_model-00006-of-00006.safetensors",
    "models_t5_umt5-xxl-enc-bf16.pth",
    "Wan2.1_VAE.pth",
]


PRESETS = {
    "Preview rapide": {"cfg_scale": 4.0, "steps": 20, "quality": 4},
    "Qualite normale": {"cfg_scale": 5.0, "steps": 50, "quality": 5},
    "Haute qualite": {"cfg_scale": 6.0, "steps": 60, "quality": 6},
}

PRESET_ALIASES = {
    "Qualité normale": "Qualite normale",
    "Haute qualité": "Haute qualite",
}


@dataclass(frozen=True)
class LocalConfig:
    mocha_repo_dir: Path
    wan_dir: Path
    mocha_ckpt_path: Path
    mocha_ckpt_fallback: Path
    uploads_dir: Path
    outputs_dir: Path
    temp_dir: Path


@dataclass(frozen=True)
class RunOptions:
    preset: str = "Qualite normale"
    output_dir: Path | None = None
    resolution: str = "832x480"
    frame_count: int = 81
    seed: int = 0
    low_vram: bool = False
    cpu_offload: bool = False
    precision: str = "bf16"
    cleanup_cuda: bool = True
    offline: bool = False
    dry_run: bool = False
    dataloader_num_workers: int = 0
    fallback_overlay: bool = True


@dataclass(frozen=True)
class RunUpdate:
    message: str
    final_video: Path | None = None
    progress: int | None = None


@dataclass(frozen=True)
class PreparedJob:
    source_video: Path
    source_mask: Path
    reference_1: Path
    reference_2: Path | None
    csv_path: Path
    run_output_dir: Path
    final_output_dir: Path
    auto_mask: bool = False


def load_config(config_path: Path | None = None) -> LocalConfig:
    config_path = config_path or ROOT / "config_local.yaml"
    raw: dict[str, str] = {}
    if config_path.exists():
        try:
            import yaml

            loaded = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            if isinstance(loaded, dict):
                raw = {str(key): str(value) for key, value in loaded.items() if value is not None}
        except Exception:
            raw = _read_simple_yaml(config_path)

    def local_path(key: str, default: str) -> Path:
        value = raw.get(key, default)
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = ROOT / path
        return path.resolve()

    return LocalConfig(
        mocha_repo_dir=local_path("mocha_repo_dir", "./MoCha"),
        wan_dir=local_path("wan_dir", "./checkpoints/Wan2.1-T2V-14B"),
        mocha_ckpt_path=local_path("mocha_ckpt_path", "./checkpoints/MoCha/preview/step18500.ckpt"),
        mocha_ckpt_fallback=local_path("mocha_ckpt_fallback", "./checkpoints/step18500.ckpt"),
        uploads_dir=local_path("uploads_dir", "./uploads"),
        outputs_dir=local_path("outputs_dir", "./outputs"),
        temp_dir=local_path("temp_dir", "./temp"),
    )


def _read_simple_yaml(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def ensure_directories(config: LocalConfig) -> None:
    for path in [
        config.uploads_dir,
        config.uploads_dir / "videos",
        config.uploads_dir / "masks",
        config.uploads_dir / "references",
        config.outputs_dir,
        config.temp_dir,
    ]:
        path.mkdir(parents=True, exist_ok=True)


def normalize_frame_count(value: int) -> int:
    value = max(1, min(int(value), 161))
    if (value - 1) % 4:
        value = value - ((value - 1) % 4)
    return max(value, 1)


def parse_resolution(value: str) -> tuple[int, int]:
    match = re.search(r"(\d+)\s*x\s*(\d+)", value)
    if not match:
        return 480, 832
    width = int(match.group(1))
    height = int(match.group(2))
    return height, width


def coerce_uploaded_path(source: object) -> Path:
    if isinstance(source, Path):
        return source.expanduser().resolve()
    if isinstance(source, str):
        return Path(source).expanduser().resolve()
    if isinstance(source, dict):
        for key in ("video", "path", "name"):
            value = source.get(key)
            if value:
                return coerce_uploaded_path(value)
    name = getattr(source, "name", None)
    if name:
        return Path(str(name)).expanduser().resolve()
    raise ValueError(f"Format de fichier Gradio non reconnu: {type(source)!r}")


def save_input_file(source: object, destination_dir: Path, prefix: str) -> Path:
    if not source:
        raise ValueError(f"Fichier manquant pour {prefix}.")
    source_path = coerce_uploaded_path(source)
    if not source_path.exists():
        raise FileNotFoundError(f"Fichier introuvable: {source_path}")

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    safe_stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", source_path.stem).strip("._")[:80] or prefix
    suffix = source_path.suffix.lower() or ".dat"
    destination_dir.mkdir(parents=True, exist_ok=True)
    candidate = destination_dir / f"{timestamp}_{prefix}_{safe_stem}{suffix}"
    counter = 1
    while candidate.exists():
        candidate = destination_dir / f"{timestamp}_{prefix}_{safe_stem}_{counter}{suffix}"
        counter += 1
    shutil.copy2(source_path, candidate)
    return candidate.resolve()


def create_auto_mask(source_video: Path, destination_dir: Path) -> Path:
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    destination_dir.mkdir(parents=True, exist_ok=True)
    mask_path = destination_dir / f"{timestamp}_auto_full_frame_mask.png"

    width, height = 832, 480
    try:
        import imageio
        from PIL import Image

        reader = imageio.get_reader(str(source_video))
        frame = reader.get_data(0)
        reader.close()
        height, width = int(frame.shape[0]), int(frame.shape[1])
        Image.new("RGB", (width, height), "white").save(mask_path)
    except Exception:
        from PIL import Image

        Image.new("RGB", (width, height), "white").save(mask_path)

    return mask_path.resolve()


def create_input_csv(
    csv_path: Path,
    source_video: Path,
    source_mask: Path,
    reference_1: Path,
    reference_2: Path | None,
) -> Path:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerow(
            {
                "source_video": str(source_video),
                "source_mask": str(source_mask),
                "reference_1": str(reference_1),
                "reference_2": str(reference_2) if reference_2 else "None",
            }
        )
    return csv_path.resolve()


def prepare_job(
    source_video: str | Path,
    source_mask: object | None,
    reference_1: str | Path,
    reference_2: str | Path | None,
    options: RunOptions,
    config: LocalConfig,
) -> PreparedJob:
    ensure_directories(config)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    final_output_dir = (options.output_dir or config.outputs_dir).expanduser().resolve()
    final_output_dir.mkdir(parents=True, exist_ok=True)

    saved_video = save_input_file(source_video, config.uploads_dir / "videos", "video")
    auto_mask = not bool(source_mask)
    saved_mask = (
        create_auto_mask(saved_video, config.uploads_dir / "masks")
        if auto_mask
        else save_input_file(source_mask, config.uploads_dir / "masks", "mask")
    )
    saved_reference_1 = save_input_file(reference_1, config.uploads_dir / "references", "reference1")
    saved_reference_2 = None
    if reference_2:
        saved_reference_2 = save_input_file(reference_2, config.uploads_dir / "references", "reference2")

    csv_path = config.temp_dir / "input_data.csv"
    create_input_csv(csv_path, saved_video, saved_mask, saved_reference_1, saved_reference_2)
    run_output_dir = config.temp_dir / f"mocha_results_{timestamp}"
    run_output_dir.mkdir(parents=True, exist_ok=True)

    return PreparedJob(
        source_video=saved_video,
        source_mask=saved_mask,
        reference_1=saved_reference_1,
        reference_2=saved_reference_2,
        csv_path=csv_path,
        run_output_dir=run_output_dir.resolve(),
        final_output_dir=final_output_dir,
        auto_mask=auto_mask,
    )


def validate_inputs(job: PreparedJob) -> list[str]:
    errors: list[str] = []
    if job.source_video.suffix.lower() not in VIDEO_EXTENSIONS:
        errors.append(f"Video source illisible ou extension non supportee: {job.source_video.suffix}")
    if job.source_mask.suffix.lower() not in IMAGE_EXTENSIONS:
        errors.append("Le masque doit etre une image de premiere frame (PNG/JPG/WebP recommande).")
    if job.reference_1.suffix.lower() not in IMAGE_EXTENSIONS and job.reference_1.suffix.lower() not in VIDEO_EXTENSIONS:
        errors.append("La reference 1 doit etre une image lisible, ou une courte video acceptee par MoCha.")
    if job.reference_2 and job.reference_2.suffix.lower() not in IMAGE_EXTENSIONS and job.reference_2.suffix.lower() not in VIDEO_EXTENSIONS:
        errors.append("La reference 2 doit etre une image lisible, ou etre laissee vide.")

    try:
        from PIL import Image

        with Image.open(job.source_mask) as mask:
            mask.verify()
        with Image.open(job.reference_1) as ref:
            ref.verify()
        if job.reference_2 and job.reference_2.suffix.lower() in IMAGE_EXTENSIONS:
            with Image.open(job.reference_2) as ref2:
                ref2.verify()
    except Exception as exc:
        errors.append(f"Image invalide ou corrompue: {exc}")
    return errors


def resolve_mocha_ckpt(config: LocalConfig) -> Path:
    for candidate in [config.mocha_ckpt_path, config.mocha_ckpt_fallback]:
        if candidate.exists():
            return candidate.resolve()
    return config.mocha_ckpt_path.resolve()


def checkpoint_errors(config: LocalConfig) -> list[str]:
    errors: list[str] = []
    if not config.wan_dir.exists():
        errors.append(f"Checkpoint Wan2.1 absent: {config.wan_dir}")
    else:
        missing = [name for name in WAN_REQUIRED_FILES if not (config.wan_dir / name).exists()]
        for name in missing:
            errors.append(f"Fichier Wan2.1 manquant: {config.wan_dir / name}")

    if not resolve_mocha_ckpt(config).exists():
        errors.append(
            "Checkpoint MoCha manquant: attendu dans "
            f"{config.mocha_ckpt_path} ou {config.mocha_ckpt_fallback}"
        )
    return errors


def environment_errors(options: RunOptions) -> list[str]:
    errors: list[str] = []
    if options.dry_run:
        return errors
    if sys.version_info[:2] != (3, 10):
        errors.append(
            f"Python {sys.version_info.major}.{sys.version_info.minor} detecte. "
            "MoCha demande Python 3.10."
        )
    try:
        import torch

        if not torch.cuda.is_available():
            errors.append("CUDA indisponible: PyTorch ne detecte pas de GPU NVIDIA/CUDA.")
    except ModuleNotFoundError:
        errors.append("Dependance manquante: torch n'est pas installe dans cet environnement.")
    except Exception as exc:
        errors.append(f"Verification CUDA impossible: {exc}")
    return errors


def render_adapter_script(config: LocalConfig, options: RunOptions) -> Path:
    source_path = config.mocha_repo_dir / "inference_mocha.py"
    if not source_path.exists():
        raise FileNotFoundError(
            f"Repo MoCha introuvable ou incomplet: {source_path}. "
            "Clonez https://github.com/Orange-3DV-Team/MoCha dans ./MoCha."
        )

    text = source_path.read_text(encoding="utf-8")
    height, width = parse_resolution(options.resolution)
    frame_count = normalize_frame_count(options.frame_count)
    preset = resolve_preset(options.preset)
    wan_files = [config.wan_dir / name for name in WAN_REQUIRED_FILES]
    diffusion_files = wan_files[:6]
    t5_path = config.wan_dir / "models_t5_umt5-xxl-enc-bf16.pth"
    vae_path = config.wan_dir / "Wan2.1_VAE.pth"

    diffusion_literal = "[" + ", ".join(json.dumps(str(path)) for path in diffusion_files) + "]"
    text = re.sub(
        r'\["/path/to/diffusion_pytorch_model-00001-of-00006\.safetensors".*?'
        r'"/path/to/diffusion_pytorch_model-00006-of-00006\.safetensors"\]',
        diffusion_literal,
        text,
        flags=re.DOTALL,
    )
    text = text.replace(
        '"/path/to/Wan2.1-T2V-14B/models_t5_umt5-xxl-enc-bf16.pth"',
        json.dumps(str(t5_path)),
    )
    text = text.replace('"/path/to/Wan2.1-T2V-14B/Wan2.1_VAE.pth"', json.dumps(str(vae_path)))
    if "/path/to/" in text:
        raise RuntimeError(
            "Le script MoCha a change: impossible de remplacer tous les chemins checkpoints hardcodes."
        )

    dataset_block = """dataset = VideoRefDataset(
        args.data_path,
        args,
    )"""
    patched_dataset_block = f"""dataset = VideoRefDataset(
        args.data_path,
        args,
        max_num_frames={frame_count},
        num_frames={frame_count},
        height={height},
        width={width},
    )"""
    if dataset_block in text:
        text = text.replace(dataset_block, patched_dataset_block)

    text = re.sub(r"num_inference_steps=50", f"num_inference_steps={int(preset['steps'])}", text)
    text = re.sub(r"num_frames=81", f"num_frames={frame_count}", text)
    text = re.sub(r"seed=0", f"seed={int(options.seed)}", text)
    text = re.sub(r"quality=5\)", f"quality={int(preset['quality'])})", text)

    adapter_path = config.temp_dir / f"inference_mocha_local_{int(time.time())}.py"
    adapter_path.parent.mkdir(parents=True, exist_ok=True)
    adapter_path.write_text(text, encoding="utf-8")
    return adapter_path.resolve()


def build_command(adapter_script: Path, job: PreparedJob, config: LocalConfig, options: RunOptions) -> list[str]:
    preset = resolve_preset(options.preset)
    return [
        sys.executable,
        str(adapter_script),
        "--data_path",
        str(job.csv_path),
        "--ckpt_path",
        str(resolve_mocha_ckpt(config)),
        "--output_dir",
        str(job.run_output_dir),
        "--dataloader_num_workers",
        str(options.dataloader_num_workers),
        "--cfg_scale",
        str(preset["cfg_scale"]),
    ]


def command_to_text(command: Iterable[str]) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline(list(command))
    import shlex

    return shlex.join(list(command))


def resolve_preset(name: str) -> dict[str, float | int]:
    canonical = PRESET_ALIASES.get(name, name)
    return PRESETS.get(canonical, PRESETS["Qualite normale"])


def run_subprocess(command: list[str], cwd: Path, config: LocalConfig, options: RunOptions) -> Generator[str, None, int]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(config.mocha_repo_dir) + os.pathsep + env.get("PYTHONPATH", "")
    env.setdefault("WANDB_DISABLED", "true")
    if options.offline:
        env["HF_HUB_OFFLINE"] = "1"
        env["TRANSFORMERS_OFFLINE"] = "1"
        env["DIFFUSERS_OFFLINE"] = "1"
        env["HF_DATASETS_OFFLINE"] = "1"
    if options.low_vram:
        env.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

    process = subprocess.Popen(
        command,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=env,
    )
    assert process.stdout is not None
    output_queue: queue.Queue[str] = queue.Queue()

    def read_output() -> None:
        assert process.stdout is not None
        for raw_line in process.stdout:
            output_queue.put(raw_line.rstrip())

    reader = threading.Thread(target=read_output, daemon=True)
    reader.start()

    while process.poll() is None or not output_queue.empty():
        try:
            clean_line = output_queue.get(timeout=1)
        except queue.Empty:
            yield HEARTBEAT_LINE
            continue
        yield clean_line
        hint = explain_common_error(clean_line)
        if hint:
            yield hint

    return process.returncode or 0


def explain_common_error(line: str) -> str | None:
    lower = line.lower()
    if "cuda out of memory" in lower or "outofmemoryerror" in lower:
        return "Erreur detectee: VRAM insuffisante. Essayez moins de frames ou fermez les autres apps GPU."
    if "torch not compiled with cuda enabled" in lower:
        return "Erreur detectee: PyTorch n'a pas ete installe avec CUDA."
    if "cuda is not available" in lower:
        return "Erreur detectee: CUDA indisponible pour PyTorch."
    if "no module named" in lower:
        return "Erreur detectee: dependance Python manquante. Relancez setup_mocha_local.py."
    if "filenotfounderror" in lower and "wan2.1" in lower:
        return "Erreur detectee: checkpoint Wan2.1 manquant ou chemin incorrect."
    if "filenotfounderror" in lower and "step18500" in lower:
        return "Erreur detectee: checkpoint MoCha step18500.ckpt manquant."
    if "cannot identify image file" in lower:
        return "Erreur detectee: masque ou reference image illisible."
    if "expected all tensors to be on the same device" in lower:
        return "Erreur detectee: incompatibilite CUDA/CPU pendant l'inference."
    return None


def newest_video(search_dir: Path, started_at: float) -> Path | None:
    candidates = [
        path
        for path in search_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in OUTPUT_EXTENSIONS and path.stat().st_mtime >= started_at
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def copy_final_video(video_path: Path, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    final_path = output_dir / f"final_result_{timestamp}.mp4"
    counter = 1
    while final_path.exists():
        final_path = output_dir / f"final_result_{timestamp}_{counter}.mp4"
        counter += 1
    shutil.copy2(video_path, final_path)
    return final_path.resolve()


def create_fallback_overlay_video(
    source_video: Path,
    reference_image: Path,
    output_dir: Path,
    progress_start: int = 35,
    progress_end: int = 98,
) -> Generator[RunUpdate, None, Path | None]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"final_result_{timestamp}_mode_secours.mp4"

    try:
        import cv2
        import imageio.v2 as imageio
        import numpy as np
        from PIL import Image
    except Exception as exc:
        yield RunUpdate(f"Mode secours impossible: dependance manquante ({exc}).", progress=100)
        return None

    try:
        reader = imageio.get_reader(str(source_video))
        meta = reader.get_meta_data()
        fps = float(meta.get("fps") or 24)
        frame_count = None
        try:
            frame_count = int(reader.count_frames())
        except Exception:
            frame_count = None

        first_frame = reader.get_data(0)
        frame_height, frame_width = int(first_frame.shape[0]), int(first_frame.shape[1])

        person = create_reference_cutout(reference_image)
        bbox, source_mask = detect_source_person_area(first_frame)
        bbox_x1, bbox_y1, bbox_x2, bbox_y2 = bbox
        bbox_width = max(1, bbox_x2 - bbox_x1 + 1)
        bbox_height = max(1, bbox_y2 - bbox_y1 + 1)

        target_height = max(1, int(bbox_height * 0.98))
        scale = target_height / max(1, person.height)
        target_width = max(1, int(person.width * scale))
        if target_width > int(bbox_width * 1.18):
            target_width = max(1, int(bbox_width * 1.18))
            scale = target_width / max(1, person.width)
            target_height = max(1, int(person.height * scale))

        person = person.resize((target_width, target_height), Image.Resampling.LANCZOS)
        x = int((bbox_x1 + bbox_x2 - target_width) / 2)
        y = int(bbox_y2 - target_height)
        x = max(-target_width // 4, min(frame_width - target_width // 4, x))
        y = max(0, min(frame_height - max(1, target_height // 5), y))

        writer = imageio.get_writer(str(output_path), fps=fps, codec="libx264", quality=8)
        yield RunUpdate(
            "Mode secours local: detourage et placement sur la zone principale de la video...",
            progress=progress_start,
        )

        frame_index = 0
        while True:
            try:
                frame = first_frame if frame_index == 0 else reader.get_data(frame_index)
            except IndexError:
                break

            cleaned = soften_source_person_area(frame, source_mask)
            base = Image.fromarray(cleaned).convert("RGBA")
            base.alpha_composite(person, (x, y))
            writer.append_data(np.asarray(base.convert("RGB")))

            frame_index += 1
            if frame_count and frame_index % max(1, frame_count // 100) == 0:
                ratio = min(1.0, frame_index / max(1, frame_count))
                progress = progress_start + int((progress_end - progress_start) * ratio)
                yield RunUpdate("Mode secours local: video en cours de generation...", progress=progress)
            elif not frame_count and frame_index % 25 == 0:
                progress = min(progress_end, progress_start + frame_index // 25)
                yield RunUpdate("Mode secours local: video en cours de generation...", progress=progress)

        writer.close()
        reader.close()
        yield RunUpdate(f"Video creee en mode secours: {output_path}", final_video=output_path.resolve(), progress=100)
        return output_path.resolve()
    except Exception as exc:
        yield RunUpdate(f"Mode secours local echoue: {exc}", progress=100)
        return None


def create_reference_cutout(reference_image: Path):
    import cv2
    import numpy as np
    from PIL import Image

    image_bgr = cv2.imread(str(reference_image), cv2.IMREAD_COLOR)
    if image_bgr is None:
        return Image.open(reference_image).convert("RGBA")

    height, width = image_bgr.shape[:2]
    rect = (
        int(width * 0.16),
        int(height * 0.08),
        int(width * 0.80),
        int(height * 0.90),
    )
    mask = np.zeros((height, width), np.uint8)
    bgd_model = np.zeros((1, 65), np.float64)
    fgd_model = np.zeros((1, 65), np.float64)
    cv2.grabCut(image_bgr, mask, rect, bgd_model, fgd_model, 5, cv2.GC_INIT_WITH_RECT)

    alpha = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype("uint8")
    kernel = np.ones((5, 5), np.uint8)
    alpha = cv2.morphologyEx(alpha, cv2.MORPH_OPEN, kernel, iterations=1)
    alpha = cv2.morphologyEx(alpha, cv2.MORPH_CLOSE, kernel, iterations=2)
    alpha = cv2.GaussianBlur(alpha, (7, 7), 0)

    ys, xs = np.where(alpha > 20)
    if len(xs) == 0:
        return Image.open(reference_image).convert("RGBA")

    pad = 12
    x1 = max(0, int(xs.min()) - pad)
    y1 = max(0, int(ys.min()) - pad)
    x2 = min(width, int(xs.max()) + pad)
    y2 = min(height, int(ys.max()) + pad)

    rgba = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGBA)
    rgba[:, :, 3] = alpha
    crop = rgba[y1:y2, x1:x2]
    return Image.fromarray(crop).convert("RGBA")


def detect_source_person_area(frame) -> tuple[tuple[int, int, int, int], object]:
    import cv2
    import numpy as np

    height, width = frame.shape[:2]
    image_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    rect = (
        int(width * 0.10),
        int(height * 0.10),
        int(width * 0.78),
        int(height * 0.88),
    )
    mask = np.zeros((height, width), np.uint8)
    bgd_model = np.zeros((1, 65), np.float64)
    fgd_model = np.zeros((1, 65), np.float64)
    try:
        cv2.grabCut(image_bgr, mask, rect, bgd_model, fgd_model, 4, cv2.GC_INIT_WITH_RECT)
        source_mask = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype("uint8")
        kernel = np.ones((13, 13), np.uint8)
        source_mask = cv2.morphologyEx(source_mask, cv2.MORPH_CLOSE, kernel, iterations=2)
        source_mask = cv2.dilate(source_mask, kernel, iterations=1)
        ys, xs = np.where(source_mask > 0)
        if len(xs):
            return (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())), source_mask
    except Exception:
        pass

    x1 = int(width * 0.18)
    y1 = int(height * 0.18)
    x2 = int(width * 0.82)
    y2 = int(height * 0.98)
    fallback_mask = np.zeros((height, width), np.uint8)
    fallback_mask[y1:y2, x1:x2] = 255
    return (x1, y1, x2, y2), fallback_mask


def soften_source_person_area(frame, source_mask):
    import cv2
    import numpy as np

    mask = source_mask
    if mask is None:
        return frame
    mask = cv2.GaussianBlur(mask, (25, 25), 0)
    mask_float = (mask.astype("float32") / 255.0)[..., None]
    blurred = cv2.GaussianBlur(frame, (35, 35), 0)
    return np.clip(frame * (1.0 - mask_float) + blurred * mask_float, 0, 255).astype("uint8")


def cleanup_cuda_cache() -> str | None:
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            return "Cache CUDA nettoye."
    except Exception as exc:
        return f"Nettoyage CUDA ignore: {exc}"
    return None


def run_mocha(
    source_video: str | Path,
    source_mask: object | None,
    reference_1: str | Path,
    reference_2: str | Path | None = None,
    options: RunOptions | None = None,
    config_path: Path | None = None,
) -> Generator[RunUpdate, None, None]:
    options = options or RunOptions()
    config = load_config(config_path)
    started_at = time.time()

    yield RunUpdate("Preparation locale des fichiers...", progress=3)
    job = prepare_job(source_video, source_mask, reference_1, reference_2, options, config)
    yield RunUpdate(f"Video sauvegardee: {job.source_video}", progress=8)
    if job.auto_mask:
        yield RunUpdate(
            "Masque automatique cree: plein cadre. "
            "C'est le mode simple a 2 fichiers; pour remplacer une seule personne precise, un masque manuel reste plus fiable.",
            progress=12,
        )
    else:
        yield RunUpdate(f"Masque sauvegarde: {job.source_mask}", progress=12)
    yield RunUpdate(f"CSV cree: {job.csv_path}", progress=16)

    input_errors = validate_inputs(job)
    env_errors = environment_errors(options)
    ckpt_errors = checkpoint_errors(config)
    setup_errors = env_errors + ckpt_errors
    if not (config.mocha_repo_dir / "inference_mocha.py").exists():
        setup_errors.append(
            f"Repo MoCha introuvable: {config.mocha_repo_dir}. "
            "Clonez https://github.com/Orange-3DV-Team/MoCha dans ce dossier."
        )
    all_errors = input_errors + setup_errors

    unsupported = []
    if options.cpu_offload:
        unsupported.append("Offload CPU: non supporte par inference_mocha.py dans cette version.")
    if options.precision.lower() not in {"bf16", "bfloat16"}:
        unsupported.append("Precision autre que bf16: non supportee par inference_mocha.py dans cette version.")
    if options.low_vram:
        unsupported.append("Mode low VRAM: pas d'offload officiel; seul PYTORCH_CUDA_ALLOC_CONF est applique.")
    for message in unsupported:
        yield RunUpdate(message)

    if all_errors:
        yield RunUpdate("Impossible de lancer l'inference MoCha complete:", progress=32)
        for error in all_errors:
            yield RunUpdate(f"- {error}", progress=34)
        if input_errors or not options.fallback_overlay:
            yield RunUpdate("Aucun upload externe n'a ete effectue.", progress=100)
            return
        yield RunUpdate(
            "Passage automatique en mode secours local: une video sera creee sans IA MoCha.",
            progress=35,
        )
        fallback_result: Path | None = None
        fallback_runner = create_fallback_overlay_video(job.source_video, job.reference_1, job.final_output_dir)
        while True:
            try:
                update = next(fallback_runner)
                if update.final_video:
                    fallback_result = update.final_video
                yield update
            except StopIteration:
                break
        if fallback_result:
            yield RunUpdate(
                "Resultat cree avec le mode secours. Pour le vrai remplacement IA, il faudra MoCha, les checkpoints et un GPU plus puissant.",
                final_video=fallback_result,
                progress=100,
            )
        return

    adapter_script = render_adapter_script(config, options)
    command = build_command(adapter_script, job, config, options)
    yield RunUpdate(f"Script temporaire: {adapter_script}", progress=22)
    yield RunUpdate(f"Commande locale: {command_to_text(command)}", progress=26)

    if options.offline:
        yield RunUpdate("Mode hors ligne actif: variables HF/Transformers/Diffusers offline appliquees.", progress=28)
    if options.dry_run:
        yield RunUpdate("Dry-run termine: le modele n'a pas ete lance.", progress=100)
        return

    yield RunUpdate("Inference MoCha lancee en local...", progress=30)
    return_code = 1
    try:
        runner = run_subprocess(command, config.mocha_repo_dir, config, options)
        while True:
            try:
                line = next(runner)
                if line == HEARTBEAT_LINE:
                    yield RunUpdate("Modification en cours...", progress=None)
                elif line:
                    yield RunUpdate(line)
            except StopIteration as stop:
                return_code = int(stop.value or 0)
                break
    except KeyboardInterrupt:
        yield RunUpdate("Inference interrompue par l'utilisateur.")
        return

    if return_code != 0:
        yield RunUpdate(f"Inference terminee avec erreur (code {return_code}).", progress=100)
        return

    generated = newest_video(job.run_output_dir, started_at)
    if not generated:
        yield RunUpdate(f"Inference terminee, mais aucune video n'a ete trouvee dans {job.run_output_dir}.", progress=100)
        return

    final_video = copy_final_video(generated, job.final_output_dir)
    yield RunUpdate(f"Video finale copiee: {final_video}", final_video=final_video, progress=100)

    if options.cleanup_cuda:
        cleanup_message = cleanup_cuda_cache()
        if cleanup_message:
            yield RunUpdate(cleanup_message, final_video=final_video)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MoCha Local Character Replacement Tool")
    parser.add_argument("--source-video", required=True)
    parser.add_argument("--source-mask")
    parser.add_argument("--reference-1", required=True)
    parser.add_argument("--reference-2")
    parser.add_argument("--preset", choices=list(PRESETS), default="Qualite normale")
    parser.add_argument("--output-dir", default=str(ROOT / "outputs"))
    parser.add_argument("--resolution", default="832x480")
    parser.add_argument("--frame-count", type=int, default=81)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--low-vram", action="store_true")
    parser.add_argument("--cpu-offload", action="store_true")
    parser.add_argument("--precision", default="bf16")
    parser.add_argument("--no-cleanup-cuda", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    options = RunOptions(
        preset=args.preset,
        output_dir=Path(args.output_dir),
        resolution=args.resolution,
        frame_count=args.frame_count,
        seed=args.seed,
        low_vram=args.low_vram,
        cpu_offload=args.cpu_offload,
        precision=args.precision,
        cleanup_cuda=not args.no_cleanup_cuda,
        offline=args.offline,
        dry_run=args.dry_run,
    )
    final_video: Path | None = None
    for update in run_mocha(
        args.source_video,
        args.source_mask,
        args.reference_1,
        args.reference_2,
        options=options,
    ):
        print(update.message, flush=True)
        if update.final_video:
            final_video = update.final_video
    return 0 if final_video or args.dry_run else 1


if __name__ == "__main__":
    raise SystemExit(main())
