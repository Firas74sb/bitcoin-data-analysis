import os
import sys
from flask import Flask, render_template, request, jsonify
from core.section3.route_section3 import register_context
# from core.section2.parquet_manager import ParquetManager

app = Flask(__name__)

# Vérification des dossiers et fichiers requis
required_dirs = {
    "data/SNAPSHOT/EDGES/hour": "hour"
}

for path, name in required_dirs.items():
    if not os.path.isdir(path) or not any(f.endswith('.parquet') for f in os.listdir(path)):
        sys.exit(
            f"\n[ERREUR] Le dossier '{path}' est manquant ou vide.\n"
        )

# Pour section3 Ahmed
register_context(app)

@app.route('/')
def home():
    """Affiche la page d'accueil."""
    return render_template("home.html")

@app.route('/section2')
def home2():
    """Affiche la section2"""
    return render_template("section2/section2.html")


if __name__ == '__main__':
    app.run()
