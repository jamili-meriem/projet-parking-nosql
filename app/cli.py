"""CLI [A9] : python -m app.cli {parkings,entree,sortie,etat,abonnes}"""
import argparse
import sys

from app import config, mongo_repo
from app.errors import ParkingError


def main():
    ap = argparse.ArgumentParser(prog="parking")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("parkings")
    e = sub.add_parser("entree"); e.add_argument("plaque"); e.add_argument("parking_id")
    s = sub.add_parser("sortie"); s.add_argument("plaque")
    sub.add_parser("etat")
    a = sub.add_parser("abonnes"); a.add_argument("parking_id")
    args = ap.parse_args()

    try:
        config.wait_for_all()
        from app import parking_service, redis_repo
        if args.cmd == "parkings":
            for p in mongo_repo.list_parkings():
                t = p["tarifs"]
                print(f"{p['id']} {p['nom']:<30} {p['nb_places']:>4} places | "
                      f"{t['tarif_heure']} MAD/h, plafond {t['tarif_journalier']}, franchise {t['gratuit_minutes']} min")
        elif args.cmd == "entree":
            r = parking_service.entree(args.plaque, args.parking_id)
            print(f"ENTREE OK : {r['plaque']} -> {r['parking']} place n°{r['place']} "
                  f"(abonné: {r['abonne'] or 'non'}) | libres: {r['libres']}")
        elif args.cmd == "sortie":
            r = parking_service.sortie(args.plaque)
            print("=" * 40, "\nRECU DE SORTIE")
            for k in ("plaque", "parking", "place", "entree", "sortie", "duree_minutes", "montant", "abonne"):
                print(f"{k:>14} : {r[k]}")
            print("=" * 40)
        elif args.cmd == "etat":
            libres = redis_repo.get_tous_libres()
            for p in mongo_repo.list_parkings():
                l, n = libres.get(p["id"], 0), p["nb_places"]
                taux = (n - l) / n
                print(f"{p['id']} {p['nom']:<30} {l:>4}/{n:<4} libres [{'#' * int(taux * 20):<20}] {taux:.0%}")
        elif args.cmd == "abonnes":
            for ab in mongo_repo.list_abonnes(args.parking_id):
                print(f"{ab['plaque']:<12} {ab['nom']:<22} {ab['type_abonnement']:<8} jusqu'au {ab['date_fin']:%Y-%m-%d}")
    except ParkingError as err:
        print(f"ERREUR {err.code} : {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
