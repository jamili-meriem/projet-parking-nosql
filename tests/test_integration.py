"""Tests d'intégration bout en bout [A10] - section 17.
Prérequis : docker compose up -d, seed_mongo.py, modules redis/cassandra/tarification en place.
Lancer : python -m pytest -q tests/test_integration.py"""
import socket
from collections import Counter
from decimal import Decimal

import pytest

from app import config

def _up(host, port):
    try:
        socket.create_connection((host, port), timeout=2).close()
        return True
    except OSError:
        return False

pytestmark = pytest.mark.skipif(
    not (_up(config.MONGO_HOST, config.MONGO_PORT) and _up(config.REDIS_HOST, config.REDIS_PORT)
         and _up(config.CASSANDRA_HOST, config.CASSANDRA_PORT)),
    reason="les 3 bases doivent être démarrées")

from app import cassandra_repo, mongo_repo, parking_service, redis_repo  # noqa: E402
from app.errors import (ParkingComplet, ParkingInconnu, VehiculeAbsent,  # noqa: E402
                        VehiculeDejaPresent)

PLAQUE_STD = "99999-T-1"


@pytest.fixture(autouse=True, scope="module")
def etat_propre():
    for p in mongo_repo.list_parkings():
        redis_repo.init_parking(p["id"], p["nb_places"])
    yield


def _abonne_valide(type_ab):
    from datetime import datetime, timezone
    d = mongo_repo._db().abonnes.find_one(
        {"type_abonnement": type_ab, "date_fin": {"$gte": datetime.now(timezone.utc)}})
    return d["plaque"], d["parking_id"]


def test_init_redis_depuis_mongo():
    for p in mongo_repo.list_parkings():
        assert redis_repo.get_libres(p["id"]) == p["nb_places"]
        assert redis_repo.verifier_coherence(p["id"])


def test_entree_sortie_non_abonne():
    avant = redis_repo.get_libres("P1")
    r = parking_service.entree(PLAQUE_STD, "P1")
    assert redis_repo.get_libres("P1") == avant - 1
    assert redis_repo.get_place_de(PLAQUE_STD) == f"P1:{r['place']}"
    assert cassandra_repo.dernier_mouvement(PLAQUE_STD).type == "ENTREE"
    recu = parking_service.sortie(PLAQUE_STD)
    assert recu["duree_minutes"] >= 1
    assert recu["montant"] == Decimal("0.00")          # sous la franchise
    assert redis_repo.get_libres("P1") == avant
    assert cassandra_repo.dernier_mouvement(PLAQUE_STD).type == "SORTIE"


def test_vehicule_deja_present():
    parking_service.entree(PLAQUE_STD, "P1")
    with pytest.raises(VehiculeDejaPresent):
        parking_service.entree(PLAQUE_STD, "P1")
    parking_service.sortie(PLAQUE_STD)


def test_sortie_vehicule_absent_ne_change_rien():
    avant = redis_repo.get_tous_libres()
    with pytest.raises(VehiculeAbsent):
        parking_service.sortie("00000-X-0")
    assert redis_repo.get_tous_libres() == avant


def test_parking_inconnu():
    with pytest.raises(ParkingInconnu):
        parking_service.entree("11111-A-1", "PXX")


def test_abonne_mensuel_gratuit():
    plaque, pid = _abonne_valide("mensuel")
    r = parking_service.entree(plaque, pid)
    assert r["abonne"] == "mensuel"
    assert parking_service.sortie(plaque)["montant"] == Decimal("0.00")


def test_parking_complet_et_alerte():
    pid, nb = "P5", mongo_repo.get_parking("P5")["nb_places"]
    pubsub = redis_repo.r().pubsub()
    pubsub.subscribe(config.CHANNEL_ALERTES)
    pubsub.get_message(timeout=1)                       # confirmation d'abonnement
    for i in range(nb):
        redis_repo.occuper_place(pid, f"FULL-{i}", 1.0)
    assert redis_repo.get_libres(pid) == 0
    with pytest.raises(ParkingComplet):
        parking_service.entree("22222-B-2", pid)
    assert redis_repo.get_libres(pid) == 0              # jamais négatif
    msg = pubsub.get_message(timeout=2)
    assert msg and pid in msg["data"]                   # alerte reçue
    redis_repo.init_parking(pid, nb)


def test_panne_redis_reconstruction():
    parking_service.entree("33333-C-3", "P2")           # au moins un présent
    presents = cassandra_repo.dernieres_entrees()
    redis_repo.r().flushall()
    redis_repo.rebuild_depuis(presents)
    attendu = Counter(e["parking_id"] for e in presents)
    for p in mongo_repo.list_parkings():
        assert redis_repo.get_libres(p["id"]) == p["nb_places"] - attendu.get(p["id"], 0)
        assert redis_repo.verifier_coherence(p["id"])
    assert redis_repo.get_place_de("33333-C-3") is not None
    parking_service.sortie("33333-C-3")
