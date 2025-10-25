# Feedly-OPML-markdown

Convertir un OPML exporté depuis un newsreader comme Feedly en un fichier markdown.
Classe les feeds selon les catégories Feedly, elles-mêmes classées par ordre alphabétique.
Évalue pour chacun des feeds sa fréquence de mise à jour.
Filtre les feeds morts.

## Local install on a Mac/linux

### 1. Fork project

```bash
cd /MyPythonDir
git clone https://github.com/tcrouzet/Feedly-OPML-markdown
code Feedly-OPML-markdown
```

Sous VSC ouvrir terminal et créer venv

```bash
python -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt --upgrade
```

### 2. Télécharger OPML Feddly dans ./data

https://feedly.com/i/opml

remplacer le ./data/feedly.opml existant

### 3. Exécution

```bash
python ./app.py
```

Le résultat se retrouve dans ./output/output.md

### 4. Paramètre

Par défaut BLOCK_NON_ACTIVE = True, les sites qui fonctionnent mais qui n'ont pas mis leur feed à jour ne son pas exportés dans le markdown.