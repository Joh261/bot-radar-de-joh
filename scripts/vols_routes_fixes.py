import os
import json
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

# Heures cibles à Paris, avec une tolérance de quinze minutes
HEURES_CIBLES = ["08:45", "12:00", "18:00", "23:00"]
TOLERANCE_MINUTES = 15

CONFIG_PATH = "data/config/routes_fixes_vols.json"
ETAT_PATH = "data/etat/vols_derniers_prix.json"


def dans_la_fenetre_horaire():
    maintenant = datetime.now(ZoneInfo("Europe/Paris"))
    for heure in HEURES_CIBLES:
        h, m = map(int, heure.split(":"))
        cible = maintenant.replace(hour=h, minute=m, second=0, microsecond=0)
        ecart = abs((maintenant - cible).total_seconds()) / 60
        if ecart <= TOLERANCE_MINUTES:
            return True
    return False


def charger_json(chemin):
    with open(chemin, "r", encoding="utf-8") as f:
        return json.load(f)


def sauvegarder_json(chemin, contenu):
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(contenu, f, ensure_ascii=False, indent=2)


def chercher_prix(depart, destination, token):
    url = "https://api.travelpayouts.com/v2/prices/latest"
    params = {
        "origin": depart,
        "destination": destination,
        "currency": "eur",
        "sorting": "price",
        "limit": 5,
        "token": token,
    }
    reponse = requests.get(url, params=params, timeout=20)
    reponse.raise_for_status()
    resultat = reponse.json()
    if not resultat.get("success") or not resultat.get("data"):
        return None
    return min(resultat["data"], key=lambda x: x["price"])


def envoyer_telegram(message):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.post(url, data={"chat_id": chat_id, "text": message})


def main():
    if not dans_la_fenetre_horaire():
        print("Hors fenêtre horaire, aucune vérification.")
        return

    token_travelpayouts = os.environ["TRAVELPAYOUTS_TOKEN"]
    config = charger_json(CONFIG_PATH)
    etat = charger_json(ETAT_PATH)
    historique = etat.get("historique", [])

    for depart in config["depart"]:
        for route in config["routes"]:
            destination = route["code"]
            plafond = route["plafond_euros"]

            meilleur = chercher_prix(depart, destination, token_travelpayouts)
            if meilleur is None:
                continue

            prix = meilleur["price"]
            if prix > plafond:
                continue

            cle = f"{depart}-{destination}-{prix}"
            if cle in [h.get("cle") for h in historique[-20:]]:
                continue

            message = (
                f"Vol repéré, {depart} vers {route['destination']}\n"
                f"{prix} euros, sous ton plafond de {plafond} euros\n"
                f"Départ {meilleur.get('departure_at', 'date non précisée')}"
            )
            envoyer_telegram(message)

            historique.append({
                "cle": cle,
                "route": f"{depart}-{destination}",
                "prix": prix,
                "date_alerte": datetime.now(ZoneInfo("Europe/Paris")).isoformat(),
            })

    etat["historique"] = historique[-50:]
    sauvegarder_json(ETAT_PATH, etat)


if __name__ == "__main__":
    main()
