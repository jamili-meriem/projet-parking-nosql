"""Accès MongoDB [A] : parkings et abonnés (contrats section 8.1)."""
from datetime import datetime, timezone

from pymongo import MongoClient

from app import config

_client = None


def _db():
    global _client
    if _client is None:
        _client = MongoClient(config.MONGO_HOST, config.MONGO_PORT,
                              serverSelectionTimeoutMS=5000, tz_aware=True)
    return _client[config.MONGO_DB]


def _fmt_parking(doc):
    if doc is None:
        return None
    return {"id": doc["_id"], "nom": doc["nom"], "adresse": doc.get("adresse", {}),
            "nb_places": doc["nb_places"], "tarifs": doc["tarifs"]}


def get_parking(parking_id):
    return _fmt_parking(_db().parkings.find_one({"_id": parking_id}))


def get_parking_by_nom(nom):
    return _fmt_parking(_db().parkings.find_one({"nom": nom}))


def get_abonne(plaque, parking_id, date=None):
    """Abonné VALIDE uniquement (date_fin >= date), sinon None."""
    date = date or datetime.now(timezone.utc)
    if date.tzinfo is None:
        date = date.replace(tzinfo=timezone.utc)
    doc = _db().abonnes.find_one({"plaque": plaque, "parking_id": parking_id,
                                  "date_fin": {"$gte": date}})
    if doc is None:
        return None
    return {"type_abonnement": doc["type_abonnement"], "date_fin": doc["date_fin"]}


def list_parkings():
    return [_fmt_parking(d) for d in _db().parkings.find().sort("_id", 1)]


def list_abonnes(parking_id):
    return list(_db().abonnes.find({"parking_id": parking_id}, {"_id": 0}).sort("nom", 1))


def compter_abonnes_par_type():
    return list(_db().abonnes.aggregate(
        [{"$group": {"_id": "$type_abonnement", "total": {"$sum": 1}}}]))
