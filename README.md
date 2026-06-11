# MoCha Local Character Replacement Tool

Interface locale Gradio pour lancer MoCha en mode gratuit, sans API payante, sans cloud, sans credits et sans upload externe.

Le profil par defaut est calibre pour un PC portable type **Acer Nitro V15 / RTX 3050**:

- preview rapide
- resolution `416x240`
- `17` frames
- mode low-VRAM
- lancement local sur `http://127.0.0.1:7860`

> Important: MoCha/Wan2.1 14B reste tres lourd. Une RTX 3050 laptop peut echouer en VRAM meme avec ce profil. L'outil est pret a lancer MoCha, mais il ne transforme pas une petite carte en GPU 24 GB.

## Installation en 2 commandes

```bash
git clone https://github.com/redwaneamokrane2003-jpg/BOT-CREA-PIC.git
cd BOT-CREA-PIC
```

Windows:

```bat
py -3.10 run.py --setup --download-models
```

Linux:

```bash
python3.10 run.py --setup --download-models
```

Ensuite, pour relancer plus tard:

```bash
python run.py
```

Ou avec les scripts:

```bat
run.bat
```

```bash
./run.sh
```

## Ce que fait `run.py --setup --download-models`

Le lanceur:

- cree un environnement local `.venv`
- installe les dependances de l'interface
- clone le repo public `https://github.com/Orange-3DV-Team/MoCha` dans `./MoCha`
- installe les dependances MoCha
- cree les dossiers locaux
- telecharge les checkpoints Hugging Face dans `./checkpoints`
- lance l'interface Gradio locale

## Si tu ne veux pas telecharger les modeles automatiquement

```bash
python run.py --setup --no-launch
```

Puis telecharge manuellement:

```bash
huggingface-cli download Wan-AI/Wan2.1-T2V-14B --local-dir ./checkpoints/Wan2.1-T2V-14B
huggingface-cli download Orange-3DV-Team/MoCha --include "preview/step18500.ckpt" --local-dir ./checkpoints/MoCha
```

Puis lance:

```bash
python run.py
```

## Utilisation

L'interface affiche seulement:

1. `Video a copier`
2. `Personne a mettre dans la video`
3. une barre de progression
4. la case `Resultat`

Tous les fichiers restent locaux:

- uploads: `uploads/`
- CSV temporaire: `temp/input_data.csv`
- resultats: `outputs/`
- checkpoints: `checkpoints/`

## Prerequis

- Python 3.10
- Git
- GPU NVIDIA + pilotes CUDA
- assez de VRAM pour MoCha/Wan2.1
- espace disque important pour les checkpoints

## Commandes utiles

Preparation sans lancer l'interface:

```bash
python run.py --setup --download-models --no-launch
```

Lancement sur un autre port:

```bash
python run.py --port 7870
```

Diagnostic local:

```bash
python setup_mocha_local.py --offline --skip-install
```

Mode CLI:

```bash
python mocha_runner.py --source-video video.mp4 --reference-1 personne.png
```

## Limites

Le vrai remplacement coherent d'une personne dans une video demande le moteur MoCha et ses checkpoints. Le projet ne fait aucun appel a fal.ai, Replicate, RunPod, Hugging Face Inference API ou autre service cloud.

Si les checkpoints, Python 3.10, CUDA ou la VRAM ne sont pas disponibles, l'outil affiche l'erreur au lieu de produire un faux collage.

## Licences

- MoCha: verifier la licence du repo et du checkpoint `Orange-3DV-Team/MoCha`.
- Wan2.1: verifier la licence du modele `Wan-AI/Wan2.1-T2V-14B`.
- Utilise l'outil seulement avec les droits/consentements necessaires.
