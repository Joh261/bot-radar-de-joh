import os
import json
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

NOM_MODULE = "deals_multisources"

PARAMETRES_PATH = "data/config/parametres_globaux.json"
CONFIG_PATH = "data/config/deals_motscles.json"
ETAT_PATH = "data/etat/deals_deja_envoyes.json"

URL_APIFY = "https://api.apify.com/v2/acts/automation-lab~dealabs-deals-scraper/run-sync-get-dataset-items"


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


def chercher_deals(mots_cles, token):
    body = {
        "searchQueries": mots_cles,
        "maxItems": 100,
        "maxPagesPerSource": 1,
        "includeExpired": False,
    }
    reponse = requests.post(
        URL_APIFY,
        params={"token": token},
        json=body,
        timeout=60,
    )
    reponse.raise_for_status()
    return reponse.json()


def envoyer_telegram(message):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.post(url, data={"chat_id": chat_id, "text": message})


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

    token_apify = os.environ["APIFY_TOKEN"]
    config = charger_json(CONFIG_PATH)
    etat = charger_json(ETAT_PATH) if os.path.exists(ETAT_PATH) else {"deals_envoyes": []}
    deals_envoyes = etat.get("deals_envoyes", [])

    seuil = config["seuil_reduction_pourcent"]
    mots_cles = config["mots_cles"]

    deals = chercher_deals(mots_cles, token_apify)
    print(f"{len(deals)} deals récupérés au total")

    for deal in deals:
        deal_id = deal.get("dealId")
        discount = deal.get("discountPercentage")
        titre = deal.get("title", "Deal sans titre")
        prix = deal.get("price")
        merchant = deal.get("merchant", "")
        lien = deal.get("dealUrl", "")

        if deal_id is None or discount is None:
            continue

        print(f"{titre}, {discount}% de réduction")

        if discount < seuil:
            continue

        if deal_id in deals_envoyes:
            continue

        message = (
            f"Deal repéré, {discount}% de réduction\n"
            f"{titre}\n"
            f"{prix} euros" + (f", chez {merchant}" if merchant else "") + "\n"
            f"{lien}"
        )
        envoyer_telegram(message)
        deals_envoyes.append(deal_id)

    etat["deals_envoyes"] = deals_envoyes[-200:]
    sauvegarder_json(ETAT_PATH, etat)


if __name__ == "__main__":
    main()
