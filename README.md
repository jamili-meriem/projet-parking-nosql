# Projet NoSQL - Sujet 15 : Gestion d'un parking
Persistance polyglotte : **MongoDB + Redis + Cassandra** - déploiement Docker Compose.
Équipe : Meryem (A : MongoDB + Docker + intégration), Marwa (B : Redis), Douaa (C : Cassandra + calculs).

## 1. Lancement rapide (moins de 10 minutes)
Prérequis : Docker Desktop démarré, Python 3.10+.
```bash
python -m venv .venv && source .venv/Scripts/activate      # Linux/Mac : source .venv/bin/activate
pip install -r requirements.txt
docker compose up -d && docker compose ps                   # attendre 3 x healthy (Cassandra ~1-2 min)
python scripts/seed_mongo.py                                # parkings + abonnés (idempotent)
python scripts/generate_mouvements.py                       # historique Cassandra + init Redis
python -m app.cli etat                                      # places libres
python -m app.cli entree 97197-H-32 P1
python -m app.cli sortie 97197-H-32                         # reçu : durée + montant
python -m pytest -q tests                                   # tests unitaires + intégration
docker compose down -v                                      # reset complet
```
Commandes CLI : `parkings`, `entree <plaque> <parking>`, `sortie <plaque>`, `etat`, `abonnes <parking>`.
Tableau de bord temps réel : `python scripts/dashboard.py`.

## 2. Architecture
```
            CLI (app/cli.py)  ->  parking_service.entree() / sortie()
                 |                  |                     |
     tarifs, abonnés          état des places        historique
                 v                  v                     v
            MongoDB              Redis                Cassandra
         parkings, abonnes   place:* libres:*       mouvements
         (documents)         vehicule:* Pub/Sub     mouvements_par_vehicule
```
| Source | Destination | Donnée | Moment |
|---|---|---|---|
| MongoDB | Application | capacité, tarifs, statut d'abonné | entrée et sortie |
| MongoDB | Redis | nb_places (init des places et du compteur) | initialisation |
| Redis | Application | place, heure d'entrée, places libres | entrée, sortie, affichage |
| Application | Cassandra | événement ENTREE / SORTIE (+ montant) | entrée et sortie |
| Cassandra | Redis | dernier mouvement de chaque plaque | reprise après panne |
| Cassandra | Application | heure d'entrée (secours) | sortie |

**Entrée** : Mongo (parking, abonné) -> Redis (script Lua atomique : place attribuée, compteur décrémenté) -> alerte Pub/Sub si complet -> Cassandra (ENTREE).
**Sortie** : Redis (libération atomique, heure d'entrée) -> calcul durée -> Mongo (tarifs, abonné) -> montant -> Cassandra (SORTIE + montant) -> reçu.
Redis est mis à jour avant Cassandra (état temps réel faisant foi). Il n'existe pas de transaction distribuée : si Cassandra échoue après 3 essais, l'application **compense** côté Redis (entrée annulée / place ré-occupée) et journalise l'incident.

## 3. MongoDB : justification et CAP (partie A)
**Pourquoi MongoDB** : parkings et abonnés sont des données structurées mais flexibles, peu volumineuses, qui changent rarement. Le document imbriqué `tarifs` évite toute jointure, les index secondaires (`nom`, `plaque`, `(parking_id, plaque)`) permettent des recherches rapides, et la validation `$jsonSchema` garantit des capacités et tarifs cohérents.
**Positionnement CAP : CP.** En replica set, un seul primaire accepte les écritures. En cas de partition réseau, le secondaire minoritaire ne peut pas élire de primaire : les écritures sont refusées mais les données restent cohérentes. C'est acceptable ici car ces données sont lues bien plus qu'écrites et une lecture légèrement retardée n'est pas gênante. (Dans notre projet, MongoDB tourne en instance unique ; le positionnement décrit la configuration classique en replica set.)

## 4. Modèle MongoDB (base `parking_db`)
- `parkings` : `_id` métier court (`P1`...), `nom` (unique), `adresse{}`, `nb_places`, `tarifs{tarif_heure, tarif_journalier, gratuit_minutes}`. Validation `$jsonSchema`.
- `abonnes` : `nom`, `plaque` (unique), `parking_id`, `type_abonnement` (mensuel = gratuit, reduit = 50 %), `date_fin`. Index composé `(parking_id, plaque)`.
- Jeu de données : 6 parkings (50 à 300 places), 300 abonnés dont 15 expirés (seed déterministe, relançable sans doublon).

## 5. Requêtes MongoDB (mongosh : `docker compose exec mongo mongosh parking_db`)
| # | Requête | Rôle dans l'application | Capture |
|---|---|---|---|
| 1 | `db.parkings.find({ nom: "Parking Centre-Ville" }, { tarifs: 1, nb_places: 1, _id: 0 })` | source des tarifs et de la capacité | `captures/mongo_1.png` |
| 2 | `db.abonnes.find({ parking_id: "P1" }).sort({ nom: 1 })` | liste des abonnés d'un parking | `captures/mongo_2.png` |
| 3 | `db.abonnes.findOne({ plaque: "97197-H-32", parking_id: "P1", date_fin: { $gte: new Date() } })` | vérification d'abonnement valide à l'entrée/sortie | `captures/mongo_3.png` |
| 4 | `db.abonnes.aggregate([{ $group: { _id: "$type_abonnement", total: { $sum: 1 } } }])` | statistiques (196 mensuels, 104 réduits) | `captures/mongo_4.png` |

## 6. Gestion des cas limites (côté orchestration)
Parking inconnu, véhicule déjà présent, parking complet, sortie d'un véhicule absent (aucun compteur modifié), heure d'entrée absente de Redis (secours Cassandra), abonnement expiré (tarif normal), échec Cassandra (retry + compensation). Tous sont couverts par `tests/test_integration.py`.

## 7. Docker
`docker-compose.yml` : 3 services, volumes nommés, réseau commun, healthchecks, Redis en AOF, Cassandra limitée (`MAX_HEAP_SIZE=512M`, `HEAP_NEWSIZE=128M`, un nœud). La CLI attend les 3 bases (`config.wait_for_all`) au lieu de planter.

## 8. Difficultés et limites
Pas de transaction distribuée (compensation applicative) ; Cassandra lente au démarrage (healthcheck + retry) ; instance unique pour chaque base. Améliorations : cluster Cassandra à 3 nœuds, Redis Sentinel, replica set / sharding MongoDB.

## 9. Parties de Marwa (Redis) et Douaa (Cassandra)
*À compléter par chacune : justification + CAP, modèle, requêtes avec captures.*
