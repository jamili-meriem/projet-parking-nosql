"""A6 : initialise Redis depuis les parkings Mongo."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app import mongo_repo, redis_repo

for p in mongo_repo.list_parkings():
    redis_repo.init_parking(p["id"], p["nb_places"])
    print(f"{p['id']}: libres = {redis_repo.get_libres(p['id'])} / {p['nb_places']}")
