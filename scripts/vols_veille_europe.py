import os
import json
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

NOM_MODULE = "vols_veille_europe"

PARAMETRES_PATH = "data/config/parametres_globaux.json"
CONFIG_PATH = "data/config/veille_europe.json"
ETAT_PATH = "data/etat/vols_europe_derniers_prix.json"


def charger_json(chemin):
    with open(chemin, "r", encoding="utf-8") as f:
        return json.load(f)


def sauvegarder_json(chemin, contenu):
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(contenu, f, ensure_ascii=False, indent=2)


def module_actif(parametres):
    return parametres.get("modules_actifs", {}).get(NOM_MODULE, True)


def dans_la_fenetre_horaire(parametres):
    heures_cibles = parametres.get("heures_cibles", [])
    tolerance = parametres.get("tolerance_minutes", 15)
    maintenant = datetime.now(ZoneInfo("Europe/Paris"))
    for heure in heures_cibles:
        h, m = map(int, heure.split(":"))
        cible = maintenant.replace(hour=h, minute=m, second=0, microsecond=0)
        ecart = abs((maintenant - cible).total_seconds()) / 60
        if ecart <= tolerance:
            return True
    return False


def chercher_meilleurs_prix(depart, token):
    url = "https://api.travelpayouts.com/v2/prices/latest"
    params = {
        "origin": depart,
        "currency": "eur",
        "sorting": "price",
        "limit": 30,
        "token": token,
    }
    reponse = requests.get(url, params=params, timeout=20)
    reponse.raise_for_status()
    resultat = reponse.json()
    if not resultat.get("success"):
        return []
    return resultat.get("data", [])


def envoyer_telegram(message):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.post(url, data={"chat_id": chat_id, "text": message}, params={"parse_mode": "Markdown"})


def main():
    forcer = os.environ.get("FORCER_TEST", "false").lower() == "true"
    parametres = charger_json(PARAMETRES_PATH)

    if not module_actif(parametres):
        print("Module désactivé dans les paramètres globaux.")
        return

    if not forcer and not dans_la_fenetre_horaire(parametres):
        print("Hors fenêtre horaire, aucune vérification.")
        return

    if forcer:
        print("Mode forcé activé, vérification immédiate.")

    token_travelpayouts = os.environ["TRAVELPAYOUTS_TOKEN"]
    config = charger_json(CONFIG_PATH)
    etat = charger_json(ETAT_PATH) if os.path.exists(ETAT_PATH) else {"historique": []}
    historique = etat.get("historique", [])

    budget_max = config["budget_max_euros"]

    for depart in config["depart"]:
        resultats = chercher_meilleurs_prix(depart, token_travelpayouts)

        for offre in resultats:
            destination = offre.get("destination")
            prix = offre["value"]
            print(f"{depart}-{destination}, prix trouvé {prix} euros")

            if prix > budget_max:
                continue

            cle = f"{depart}-{destination}-{prix}"
            if cle in [h.get("cle") for h in historique[-30:]]:
                continue

            message = (
                f"🇪🇺 *Petit prix Europe, {depart} vers {destination}*\n"
                f"{prix} euros, sous ton plafond de {budget_max} euros\n"
                f"Départ {offre.get('depart_date', 'date non précisée')}"
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
