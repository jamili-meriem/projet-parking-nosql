"""Configuration centralisée [A] - aucune valeur en dur ailleurs dans le code."""
import os
import socket
import time

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

MONGO_HOST = os.getenv("MONGO_HOST", "localhost")
MONGO_PORT = int(os.getenv("MONGO_PORT", "27017"))
MONGO_DB = os.getenv("MONGO_DB", "parking_db")
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
CASSANDRA_HOST = os.getenv("CASSANDRA_HOST", "localhost")
CASSANDRA_PORT = int(os.getenv("CASSANDRA_PORT", "9042"))
CASSANDRA_KEYSPACE = os.getenv("CASSANDRA_KEYSPACE", "parking_ks")

CHANNEL_ALERTES = "alertes:parking_complet"
CASSANDRA_RETRIES = 3


def wait_for(host, port, nom, timeout=120):
    """Attend qu'un service accepte les connexions TCP (Cassandra: 30-90 s)."""
    debut = time.time()
    while time.time() - debut < timeout:
        try:
            with socket.create_connection((host, port), timeout=3):
                return True
        except OSError:
            print(f"[wait-for] {nom} pas prêt, nouvelle tentative...")
            time.sleep(3)
    raise TimeoutError(f"{nom} injoignable après {timeout}s")


def wait_for_all():
    wait_for(MONGO_HOST, MONGO_PORT, "MongoDB")
    wait_for(REDIS_HOST, REDIS_PORT, "Redis")
    wait_for(CASSANDRA_HOST, CASSANDRA_PORT, "Cassandra")
