import os
import socket

from pyspark.sql import SparkSession


class ParquetManager:
    """
    Cette classe permet de gérer la lecture des fichiers Parquet.
    """

    def __init__(self):
        """
        Initialisation de la classe.
        """
        self.path_nodetable = "data/NODE_TABLE/orbitaal-nodetable.snappy.parquet"
        self.path_addresses = "data/NODE_TABLE/orbitaal-listaddresses.snappy.parquet"

        self.path_snap_hour = "data/SNAPSHOT/EDGES/hour/"
        self.path_snap_day = "data/SNAPSHOT/EDGES/day/"
        self.path_snap_month = "data/SNAPSHOT/EDGES/month/"
        self.path_snap_year = "data/SNAPSHOT/EDGES/year/"
        self.path_snap_all = "data/SNAPSHOT/EDGES/ALL/"

        self.path_streamgraph = "data/STREAM_GRAPH/EDGES/"

        
        self.__set_spark_local_ip()
        self.spark = SparkSession.builder.appName("ParquetManager").getOrCreate()

        self.df_nodetable = self.spark.read.parquet(self.path_nodetable)
        self.df_addresses = self.spark.read.parquet(self.path_addresses)
        
        self.df_hour = self.spark.read.parquet(self.path_snap_hour)
        self.df_day = self.spark.read.parquet(self.path_snap_day)
        self.df_month = self.spark.read.parquet(self.path_snap_month)
        self.df_year = self.spark.read.parquet(self.path_snap_year)
        self.df_all = self.spark.read.parquet(self.path_snap_all)

        self.df_stream = self.spark.read.parquet(self.path_streamgraph)


    def __set_spark_local_ip(self):
        """
        Définit l'adresse IP locale pour Spark.
        """
        hostname = socket.gethostname()
        ip_address = socket.gethostbyname(hostname)
        os.environ["SPARK_LOCAL_IP"] = ip_address
    
    def get_df_page(self, page: int = 1, page_size: int = 20):
        """
        Retourne les données spécifique d'un DataFrame Spark

        Args:
            df (DataFrame): Le DataFrame Spark à paginer.
            page (int): Le numéro de la page souhaitée (1-indexed).
            page_size (int): Le nombre d'éléments par page.

        Returns:
            dict: {
                "page": numéro de la page actuelle,
                "total_pages": nombre total de pages,
                "total_items": nombre total de lignes,
                "data": liste des lignes sous forme de dictionnaires
            }
        """
        df = self.df_nodetable

        total_items = df.count()
        total_pages = max((total_items + page_size - 1) // page_size, 1)
        
        # S'assurer que la page est dans les limites
        page = max(1, min(page, total_pages))
        
        start = (page - 1) * page_size
        
        # Récupération des données
        page_data = (
            df
            .limit(start + page_size)  # Limite haute
            .tail(page_size)           # Tail pour ne garder que les derniers résultats
        )
        
        # Conversion en dictionnaire pour Flask
        data = [row.asDict() for row in page_data]
        
        return data, total_pages
    
    
    def get_dataframe_columns(self, df):
        """
        Retourne la liste des noms de colonnes du DataFrame Spark donné.

        Args:
            df (DataFrame): Le DataFrame Spark dont on veut les colonnes.

        Returns:
            list: Liste des noms de colonnes.
        """
        return df.columns
