"""Seed MongoDB idempotent [A2-A4] : python scripts/seed_mongo.py"""
import os
import random
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pymongo import ASCENDING, MongoClient, UpdateOne

from app import config

PARKINGS = [
    ("P1", "Parking Centre-Ville", "12 Avenue Hassan II", "Casablanca", "20000", 120, 8.0, 60.0, 15),
    ("P2", "Parking Gare Casa-Voyageurs", "Boulevard Mohammed VI", "Casablanca", "20250", 200, 10.0, 80.0, 10),
    ("P3", "Parking Marina", "Bd des Almohades", "Casablanca", "20030", 300, 12.0, 90.0, 15),
    ("P4", "Parking Agdal", "Avenue Fal Ould Oumeir", "Rabat", "10090", 80, 6.0, 45.0, 20),
    ("P5", "Parking Medina", "Rue des Consuls", "Rabat", "10030", 50, 5.0, 40.0, 30),
    ("P6", "Parking Technopolis", "Rocade Rabat-Salé", "Salé", "11100", 150, 7.0, 55.0, 15),
]
PRENOMS = ["Amine", "Sara", "Youssef", "Salma", "Omar", "Imane", "Hamza", "Nadia", "Karim", "Lina", "Mehdi", "Zineb"]
NOMS = ["El Idrissi", "Benali", "Alaoui", "Tazi", "Berrada", "Fassi", "Chraibi", "Lahlou", "Amrani", "Jamili"]
NB_ABONNES, NB_EXPIRES = 300, 15


def plaque(rng):
    return f"{rng.randint(1, 99999)}-{rng.choice('ABDEHJKLMTW')}-{rng.randint(1, 99)}"


def main():
    rng = random.Random(42)  # déterministe => idempotent
    db = MongoClient(config.MONGO_HOST, config.MONGO_PORT, tz_aware=True)[config.MONGO_DB]

    # Validation de schéma (A2)
    if "parkings" not in db.list_collection_names():
        db.create_collection("parkings", validator={"$jsonSchema": {
            "bsonType": "object", "required": ["nom", "nb_places", "tarifs"],
            "properties": {
                "nb_places": {"bsonType": "int", "minimum": 1},
                "tarifs": {"bsonType": "object", "properties": {
                    "tarif_heure": {"bsonType": ["double", "int"], "minimum": 0},
                    "tarif_journalier": {"bsonType": ["double", "int"], "minimum": 0},
                    "gratuit_minutes": {"bsonType": ["double", "int"], "minimum": 0}}}}}})
    db.parkings.create_index([("nom", ASCENDING)], unique=True)
    db.abonnes.create_index([("plaque", ASCENDING)], unique=True)
    db.abonnes.create_index([("parking_id", ASCENDING), ("plaque", ASCENDING)])

    ops = [UpdateOne({"_id": p[0]}, {"$set": {
        "nom": p[1], "adresse": {"rue": p[2], "ville": p[3], "code_postal": p[4]},
        "nb_places": p[5],
        "tarifs": {"tarif_heure": p[6], "tarif_journalier": p[7], "gratuit_minutes": p[8]}}},
        upsert=True) for p in PARKINGS]
    db.parkings.bulk_write(ops)

    now = datetime.now(timezone.utc)
    plaques, ab_ops = set(), []
    while len(plaques) < NB_ABONNES:
        plaques.add(plaque(rng))
    for i, pl in enumerate(sorted(plaques)):
        expire = i < NB_EXPIRES
        date_fin = now - timedelta(days=rng.randint(10, 200)) if expire \
            else now + timedelta(days=rng.randint(30, 400))
        ab_ops.append(UpdateOne({"plaque": pl}, {"$set": {
            "nom": f"{rng.choice(PRENOMS)} {rng.choice(NOMS)}",
            "parking_id": rng.choice(PARKINGS)[0],
            "type_abonnement": rng.choice(["mensuel", "mensuel", "reduit"]),
            "date_fin": date_fin}}, upsert=True))
    db.abonnes.bulk_write(ab_ops)

    print(f"parkings: {db.parkings.count_documents({})} | abonnés: {db.abonnes.count_documents({})} "
          f"| expirés: {db.abonnes.count_documents({'date_fin': {'$lt': now}})}")


if __name__ == "__main__":
    main()
