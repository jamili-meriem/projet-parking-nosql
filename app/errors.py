"""Exceptions métier PARTAGÉES. Marwa (Redis) et Douaa (Cassandra) doivent
les importer d'ici : from app.errors import ParkingComplet, ..."""


class ParkingError(Exception):
    code = "ERREUR"


class ParkingInconnu(ParkingError):
    code = "PARKING_INCONNU"


class ParkingComplet(ParkingError):
    code = "PARKING_COMPLET"


class VehiculeDejaPresent(ParkingError):
    code = "VEHICULE_DEJA_PRESENT"


class VehiculeAbsent(ParkingError):
    code = "VEHICULE_ABSENT"


class IncoherenceDuree(ParkingError):
    code = "DUREE_INCOHERENTE"


class EchecCassandra(ParkingError):
    code = "ECHEC_CASSANDRA"
