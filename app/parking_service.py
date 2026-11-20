"""Orchestration entrée / sortie sur les 3 bases [A7-A8] (sections 6.1 et 6.2).
Dépend de : redis_repo [B], cassandra_repo [C], tarification [C]."""
import logging
import time
from datetime import datetime, timezone

from app import cassandra_repo, config, mongo_repo, redis_repo, tarification
from app.errors import EchecCassandra, ParkingInconnu, VehiculeAbsent, VehiculeDejaPresent

log = logging.getLogger("parking")


def _utc(ts):
    return datetime.fromtimestamp(float(ts), tz=timezone.utc)


def _ecrire_cassandra(**kw):
    """Retry puis lève EchecCassandra (la compensation est faite par l'appelant)."""
    derniere = None
    for essai in range(1, config.CASSANDRA_RETRIES + 1):
        try:
            cassandra_repo.ajouter_mouvement(**kw)
            return
        except Exception as e:  # noqa: BLE001
            derniere = e
            log.warning("Cassandra échec %d/%d : %s", essai, config.CASSANDRA_RETRIES, e)
            time.sleep(0.5 * essai)
    raise EchecCassandra(str(derniere))


def entree(plaque, parking_id):
    # 1. MongoDB : parking
    parking = mongo_repo.get_parking(parking_id)
    if parking is None:
        raise ParkingInconnu(parking_id)
    # 2. Redis : déjà présent ? (revérifié atomiquement dans le script Lua)
    if redis_repo.get_place_de(plaque):
        raise VehiculeDejaPresent(plaque)
    # 3. MongoDB : abonné (information)
    now = datetime.now(timezone.utc)
    abonne = mongo_repo.get_abonne(plaque, parking_id, now)
    # 4. Redis atomique (lève ParkingComplet / VehiculeDejaPresent)
    place = redis_repo.occuper_place(parking_id, plaque, now.timestamp())
    # 5. Alerte parking complet (bonus), si B ne la publie pas déjà dans occuper_place
    libres = redis_repo.get_libres(parking_id)
    if libres == 0 and hasattr(redis_repo, "publier_alerte_complet"):
        redis_repo.publier_alerte_complet(parking_id)
    # 6. Cassandra, avec compensation Redis en cas d'échec définitif
    try:
        _ecrire_cassandra(parking_id=parking_id, plaque=plaque, type="ENTREE",
                          place=place, ts=now)
    except EchecCassandra:
        log.error("Compensation Redis pour %s (entrée annulée)", plaque)
        redis_repo.liberer_place(plaque)
        raise
    return {"plaque": plaque, "parking": parking["nom"], "parking_id": parking_id,
            "place": place, "heure_entree": now,
            "abonne": abonne["type_abonnement"] if abonne else None, "libres": libres}


def sortie(plaque):
    sortie_dt = datetime.now(timezone.utc)
    # 1-2. Redis : libération atomique -> parking, place, heure d'entrée (VehiculeAbsent si inconnu)
    info = redis_repo.liberer_place(plaque)
    parking_id, place = info["parking_id"], int(info["place"])
    heure_entree = info.get("heure_entree")
    if heure_entree:
        entree_dt = _utc(heure_entree)
    else:  # secours Cassandra
        entree_dt = cassandra_repo.derniere_entree(plaque)
        if entree_dt is None:
            raise VehiculeAbsent(plaque)
        if entree_dt.tzinfo is None:
            entree_dt = entree_dt.replace(tzinfo=timezone.utc)
    # 3. Durée (lève IncoherenceDuree si <= 0)
    duree = tarification.calculer_duree(entree_dt, sortie_dt)
    # 4. MongoDB : tarifs + abonné valide
    parking = mongo_repo.get_parking(parking_id)
    abonne = mongo_repo.get_abonne(plaque, parking_id, sortie_dt)
    montant = tarification.calculer_montant(duree, parking["tarifs"], abonne)
    # 6. Cassandra (SORTIE + montant), compensation en cas d'échec
    try:
        _ecrire_cassandra(parking_id=parking_id, plaque=plaque, type="SORTIE",
                          place=place, ts=sortie_dt, montant=montant)
    except EchecCassandra:
        log.error("Compensation Redis : ré-occupation de la place pour %s", plaque)
        redis_repo.occuper_place(parking_id, plaque, entree_dt.timestamp())
        raise
    # 7. Reçu
    return {"plaque": plaque, "parking": parking["nom"], "parking_id": parking_id,
            "place": place, "entree": entree_dt, "sortie": sortie_dt,
            "duree_minutes": duree, "montant": montant,
            "abonne": abonne["type_abonnement"] if abonne else None}
