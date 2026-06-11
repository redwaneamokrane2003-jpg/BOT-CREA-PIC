from __future__ import annotations

import os
import re
from pathlib import Path

os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")

import gradio as gr

from mocha_runner import RunOptions, run_mocha


def progress_html(percent: int, status: str, tone: str = "running") -> str:
    percent = max(0, min(100, int(percent)))
    color = "#2563eb"
    if tone == "done":
        color = "#16a34a"
    elif tone == "error":
        color = "#dc2626"

    return f"""
    <div style="border:1px solid #d9dde7;border-radius:8px;padding:18px;background:#ffffff;">
      <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px;">
        <strong style="font-size:16px;">Previsualisation</strong>
        <span style="font-size:22px;font-weight:700;color:{color};">{percent}%</span>
      </div>
      <div style="height:14px;background:#eef1f6;border-radius:999px;overflow:hidden;">
        <div style="height:100%;width:{percent}%;background:{color};transition:width .35s ease;"></div>
      </div>
      <div style="margin-top:12px;color:#3f4654;font-size:14px;">{status}</div>
    </div>
    """


def update_percent(current: int, message: str, explicit_progress: int | None) -> int:
    if explicit_progress is not None:
        return max(current, explicit_progress)

    match = re.search(r"(\d{1,3})\s*%", message)
    if match:
        detected = max(0, min(100, int(match.group(1))))
        return max(current, 30 + int(detected * 0.65))

    if "Modification en cours" in message:
        return min(95, max(30, current + 1))
    if "Inference MoCha" in message:
        return max(current, 30)
    if "erreur" in message.lower() or "impossible" in message.lower():
        return 100
    return current


def clean_status(message: str) -> tuple[str, str]:
    lower = message.lower()
    if "mode secours" in lower or "passage automatique" in lower:
        return "Mode secours local: creation d'une video compatible avec ta machine...", "running"
    if "aucun upload externe" in lower:
        return "Traitement arrete: MoCha n'est pas encore installe/configure completement.", "error"
    if "video finale" in lower:
        return "Termine. La video modifiee est prete.", "done"
    if "impossible" in lower or "erreur" in lower or "manquant" in lower or "introuvable" in lower:
        return message, "error"
    if "preparation" in lower:
        return "Preparation des fichiers locaux...", "running"
    if "masque automatique" in lower:
        return "Analyse simple: la zone a modifier est preparee automatiquement.", "running"
    if "rtx 3050" in lower or "nitro" in lower:
        return message, "running"
    if "inference mocha" in lower or "modification en cours" in lower:
        return "MoCha tourne en profil RTX 3050: preview courte, low-VRAM...", "running"
    if "checkpoint" in lower:
        return message, "error"
    return "Traitement local en cours...", "running"


def _run_simple(source_video, reference_person):
    if not source_video:
        yield progress_html(0, "Ajoute la video a copier.", "error"), None
        return

    if not reference_person:
        yield progress_html(0, "Ajoute la personne a mettre dans la video.", "error"), None
        return

    options = RunOptions(
        preset="Preview rapide",
        output_dir=Path("outputs").resolve(),
        resolution="416x240",
        frame_count=17,
        seed=0,
        low_vram=True,
        cleanup_cuda=True,
        offline=False,
        dry_run=False,
        fallback_overlay=False,
    )

    percent = 0
    final_video = None
    last_error = None
    yield progress_html(
        percent,
        "Profil Acer Nitro V15 / RTX 3050 actif: preview courte, low-VRAM, 416x240, 17 frames.",
    ), None

    for update in run_mocha(
        source_video=source_video,
        source_mask=None,
        reference_1=reference_person,
        reference_2=None,
        options=options,
    ):
        percent = update_percent(percent, update.message, update.progress)
        status, tone = clean_status(update.message)
        if "mode secours" in update.message.lower() or "passage automatique" in update.message.lower():
            last_error = None
        if tone == "error":
            last_error = status
        elif last_error and not update.final_video:
            status = last_error
            tone = "error"
        if update.final_video:
            final_video = str(update.final_video)
            percent = 100
            tone = "done"
        yield progress_html(percent, status, tone), final_video


with gr.Blocks(title="MoCha Local") as demo:
    gr.Markdown("# MoCha Local - Nitro V15 RTX 3050")

    with gr.Row():
        source_video = gr.Video(label="1. Video a copier")
        reference_person = gr.Image(label="2. Personne a mettre dans la video", type="filepath")

    run_button = gr.Button("J'ai les droits et je lance", variant="primary")

    preview = gr.HTML(value=progress_html(0, "En attente des deux fichiers."))
    result_video = gr.Video(label="Resultat")

    run_button.click(
        _run_simple,
        inputs=[source_video, reference_person],
        outputs=[preview, result_video],
    )


if __name__ == "__main__":
    server_name = os.environ.get("MOCHA_SERVER_NAME", "127.0.0.1")
    server_port = int(os.environ.get("MOCHA_SERVER_PORT", "7860"))
    demo.queue().launch(server_name=server_name, server_port=server_port, share=False, inbrowser=True)
