# Projet d'Analyse et de Visualisation des Transactions Bitcoin

Ce projet est une application web interactive permettant d'explorer et d'analyser les réseaux de transactions Bitcoin à travers différentes résolutions temporelles. Il s'appuie sur des technologies modernes pour fournir des visualisations dynamiques et des analyses approfondies des données.

[📄 Télécharger le PDF de Présentation] (./Projet_Bitocin_Diapo.pdf)
[📄 Télécharger le PDF du Rapport] (./Rapportindividuellifprojet_SAIBI_MOHAMED.pdf)


## Fonctionnalités

- **Analyse à un Moment Donné** : Explorez la structure du réseau Bitcoin pour une date et une heure spécifiques.
- **Analyse Comparative** : Comparez les états du réseau entre deux points temporels pour identifier les changements.
- **Visualisation Interactive** : Graphiques interactifs permettant d'explorer les nœuds et les transactions.
- **Statistiques Détaillées** : Affichez des métriques telles que le nombre total de nœuds, de transactions, et les flux de valeur.
- **Détection de Communautés** : Analysez les clusters de transactions pour comprendre la structure du réseau.
- **Recherche Avancée** : Recherchez des nœuds ou des communautés spécifiques et examinez leurs interactions.


## Prérequis

- **Python 3.8+**
- **Node.js** (pour les dépendances front-end si nécessaire)
- **Dépendances Python** : Installées via `requirements.txt`
- **Les fichiers parquets** : Pour que le projet fonctionne, vous devez au minimum avoir extraie le dataframe snapshots hour dans le dossier data à la racine.

## Fichier d'analyse exploratoire et Identification des Acteurs (Firas.ipynb)
 Fichier qui contient les resultats de la section 2 (a savoir) 
 - **Analyse exploratoire** :
   - Etude sur les transaction d'une journée 
   - top senders/recivers 
   - Repartition des bitcoins
   - Net Balance pour chaque addresse

-  **Etude des Acteurs**    : 
   - Mise en place des profiles 
   - Donner une etiquette a chaque profile 
   - Etude approfondi des Acteur (Avec profile) :
      - Interactions 
      - Transaction moyenne pour chaque profile 
      - Transaction atypique.
### NB il faut telecharger un fichier SNAPSHOT de "jour" 


## Installation

1. Clonez le dépôt :

   ```bash
   git clone https://forge.univ-lyon1.fr/p2100030/projet_kafka.git
   cd projet_kafka

2. Créez et activez un environnement virtuel (recommandé) :

   ```bash
   python -m venv env
   source env/bin/activate  # Sur Windows : env\Scripts\activate

3. Installler les dépendances :
   
   ```bash
   pip install -r requirements.txt

4. Telecharger au minimum le dataset hour et l'extraire dans le dossier data, on obtient :
   
   ```kotlin
   data/
   ├── SNAPSHOT/
       └── EDGES/
            └── hour/ *.parquet

5. Lancer l'application et ouvrir la [page](http://127.0.0.1:5000) :
   
   ```bash
   python3 app.py
