# Feedly-OPML-markdown

Convertir un OPML exporté depuis un newsreader comme Feedly en un fichier markdown.
Classe les feed selon les catégories Feedly, elles-mêmes classées par ordre alphabétique.
Évalue pour chacun des feeds sa fréquence de mise à jour.
Filtre les feeds morts.

## Télécharger OPML Feddly dans ./data

https://feedly.com/i/opml

remplacer le ./data/feedly.opml existant

## Local install du script python on a Mac

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

### 2. Exécution

```bash
python ./app.py
```

Le résultat se retrouve dans ./output/output.md