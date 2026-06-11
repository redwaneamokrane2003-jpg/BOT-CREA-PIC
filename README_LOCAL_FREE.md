# MoCha Local Character Replacement Tool

Outil local pour remplacer une personne dans une video par un autre personnage avec MoCha, sans API payante, sans cloud, sans credits, sans abonnement et sans upload externe. L'outil est gratuit si vous avez deja le materiel compatible, en pratique un GPU NVIDIA/CUDA assez puissant.

## Points importants

- Tout s'execute sur votre machine.
- Hugging Face sert seulement a telecharger les checkpoints localement.
- Une fois les checkpoints presents, le mode `--offline` peut fonctionner sans requete reseau.
- Les fichiers uploades restent dans `uploads/`, les CSV temporaires dans `temp/`, les resultats dans `outputs/`.
- L'interface bloque l'inference tant que la case de consentement n'est pas cochee.

## Ce que le repo MoCha supporte actuellement

Analyse du repo `Orange-3DV-Team/MoCha`:

- Script principal: `inference_mocha.py`.
- Arguments officiels: `--data_path`, `--ckpt_path`, `--output_dir`, `--dataloader_num_workers`, `--cfg_scale`.
- CSV attendu: `source_video,source_mask,reference_1,reference_2`.
- `reference_2` peut valoir `None`.
- Sortie officielle: fichier `*_replaced.mp4` dans `--output_dir`.
- Dependances officielles: voir `MoCha/requirements.txt`.
- Python recommande par le README: `python==3.10`.
- Le script officiel contient encore des chemins Wan2.1 en dur (`/path/to/...`). Le wrapper cree donc une copie temporaire adaptee dans `temp/` avec vos chemins locaux, sans modifier le coeur du repo.

## Prerequis

- Windows ou Linux.
- Python 3.10.
- Git.
- GPU NVIDIA recommande.
- CUDA et PyTorch CUDA.
- VRAM recommandee: 24 GB ou plus pour Wan2.1 14B/MoCha. Moins peut echouer avec une erreur out of memory.

## Installation

Depuis ce dossier:

```shell
python setup_mocha_local.py --clone-mocha
```

Si vous avez deja clone MoCha dans `./MoCha`, vous pouvez lancer:

```shell
python setup_mocha_local.py
```

Le setup cree:

```text
checkpoints/
uploads/
uploads/videos/
uploads/masks/
uploads/references/
outputs/
temp/
```

## Telechargement des checkpoints

Wan2.1 14B:

```shell
huggingface-cli download Wan-AI/Wan2.1-T2V-14B --local-dir ./checkpoints/Wan2.1-T2V-14B
```

MoCha:

```shell
huggingface-cli download Orange-3DV-Team/MoCha --include "preview/step18500.ckpt" --local-dir ./checkpoints/MoCha
```

Chemins attendus par ce wrapper:

```text
checkpoints/Wan2.1-T2V-14B/diffusion_pytorch_model-00001-of-00006.safetensors
checkpoints/Wan2.1-T2V-14B/diffusion_pytorch_model-00002-of-00006.safetensors
checkpoints/Wan2.1-T2V-14B/diffusion_pytorch_model-00003-of-00006.safetensors
checkpoints/Wan2.1-T2V-14B/diffusion_pytorch_model-00004-of-00006.safetensors
checkpoints/Wan2.1-T2V-14B/diffusion_pytorch_model-00005-of-00006.safetensors
checkpoints/Wan2.1-T2V-14B/diffusion_pytorch_model-00006-of-00006.safetensors
checkpoints/Wan2.1-T2V-14B/models_t5_umt5-xxl-enc-bf16.pth
checkpoints/Wan2.1-T2V-14B/Wan2.1_VAE.pth
checkpoints/MoCha/preview/step18500.ckpt
```

## Lancement

```shell
python app.py
```

Ouvrez ensuite l'URL Gradio affichee dans le terminal.

## Utilisation

1. Ajoutez la video source.
2. Ajoutez le masque de la personne a remplacer sur la premiere frame.
3. Ajoutez l'image principale du nouveau personnage.
4. Ajoutez une deuxieme reference si possible, sinon laissez vide.
5. Choisissez un preset.
6. Cochez la case de consentement.
7. Lancez l'inference locale.

Le wrapper cree automatiquement `temp/input_data.csv` avec les colonnes exactes:

```csv
source_video,source_mask,reference_1,reference_2
```

## Mode hors ligne

Apres telechargement des checkpoints:

```shell
python mocha_runner.py --source-video video.mp4 --source-mask mask.png --reference-1 ref.png --offline
```

Dans l'interface, cochez `Mode hors ligne`.

## Mode test

```shell
python mocha_runner.py --source-video video.mp4 --source-mask mask.png --reference-1 ref.png --dry-run
```

Le dry-run verifie les chemins, cree le CSV, genere le script temporaire et affiche la commande sans lancer le modele.

## Options

- L'interface simple est reglee pour un profil `Acer Nitro V15 / RTX 3050`: `Preview rapide`, `416x240`, `17 frames`, `low VRAM`.
- Ce profil essaie de donner la meilleure chance possible a un GPU laptop type RTX 3050, mais MoCha/Wan2.1 14B reste un modele tres lourd.
- `Preview rapide`, `Qualite normale`, `Haute qualite`: ajustent `cfg_scale`, le nombre d'etapes internes et la qualite de sauvegarde dans la copie temporaire.
- Resolution: `832x480` par defaut MoCha, `1280x720` experimental et plus gourmand.
- Nombre de frames: le wrapper force un format compatible `4n+1`.
- Seed: appliquee dans la copie temporaire.
- Offload CPU: non supporte par `inference_mocha.py` dans la version analysee.
- Precision: `bf16`, comme le script officiel.

## Erreurs frequentes

- `CUDA indisponible`: installez PyTorch avec CUDA et verifiez le pilote NVIDIA.
- `CUDA out of memory`: reduisez le nombre de frames, utilisez `832x480`, fermez les autres applications GPU.
- `checkpoint Wan2.1 manquant`: relancez la commande `huggingface-cli download Wan-AI/Wan2.1-T2V-14B`.
- `step18500.ckpt manquant`: relancez la commande MoCha avec `--include "preview/step18500.ckpt"`.
- `No module named ...`: relancez `python setup_mocha_local.py`.
- Masque illisible: utilisez une image PNG/JPG/WebP correspondant a la premiere frame.

## Licences

- Le checkpoint MoCha sur Hugging Face est indique en licence AGPL-3.0.
- Wan2.1 T2V 14B est indique en licence Apache-2.0.
- Respectez les licences des modeles, du code et de vos donnees d'entree.

## Usage responsable

Utilisez cet outil uniquement pour des usages creatifs, personnels, artistiques ou autorises. Ne l'utilisez pas pour usurper l'identite d'une personne reelle, tromper un public, harceler, diffamer, ou creer des deepfakes non consentis.
