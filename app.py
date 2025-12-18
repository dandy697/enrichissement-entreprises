import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from googlesearch import search
import io
import concurrent.futures
import time
import urllib3
import random

# Désactivation totale des alertes de sécurité
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

st.set_page_config(page_title="Enrichissement V8 (Mode Direct)", page_icon="⚡", layout="wide")

# --- CONFIGURATION SECTORIELLE (Réduite pour la lisibilité, mais fonctionnelle) ---
SECTOR_CONFIG = {
    "Agriculture": {"kw": ["agriculture", "élevage", "vin", "bio"]},
    "BTP": {"kw": ["btp", "construction", "travaux", "architecte"]},
    "Tech/IT": {"kw": ["conseil", "logiciel", "saas", "data", "web", "digital"]},
    "Commerce": {"kw": ["boutique", "vente", "magasin", "e-commerce"]},
    "Finance": {"kw": ["banque", "assurance", "crédit", "invest"]},
    "Immobilier": {"kw": ["agence", "location", "gestion", "immo"]},
    "Industrie": {"kw": ["usine", "fabrication", "industrie", "mécanique"]},
    "Santé": {"kw": ["santé", "médical", "clinique", "pharmacie"]},
    "Restauration": {"kw": ["hôtel", "restaurant", "bar", "cuisine"]},
    "Transport": {"kw": ["transport", "logistique", "livraison", "camion"]}
}

# --- FONCTION MAGIQUE DE CONNEXION ---
def get_direct_session():
    """Crée une session qui IGNORE les proxys système"""
    s = requests.Session()
    # C'est cette ligne qui corrige l'erreur 0 dans 90% des cas :
    s.trust_env = False 
    s.verify = False
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })
    return s

def process_company(raw_input):
    company_name = str(raw_input).strip()
    res = {"Entrée": company_name, "Statut": "❌", "Info": "-", "Secteur": "-"}
    
    session = get_direct_session()
    
    # 1. TEST API GOUV
    try:
        url_api = "https://recherche-entreprises.api.gouv.fr/search"
        resp = session.get(url_api, params={"q": company_name, "per_page": 1}, timeout=10)
        
        if resp.status_code == 200 and resp.json():
            data = resp.json()[0]
            res["Statut"] = "✅"
            res["Info"] = data.get('nom_complet', 'OK')
            
            # Analyse simple
            naf = data.get('activite_principale', '')
            res["Secteur"] = f"NAF: {naf}"
            
            # 2. MINI SCRAPING (Si API OK)
            try:
                # Pause pour être gentil avec Google
                time.sleep(1)
                query = f"{data.get('nom_complet')} site officiel"
                # On utilise la lib search directement
                urls = list(search(query, num_results=1, lang="fr", advanced=True))
                if urls:
                    target_url = urls[0].url
                    # Visite du site
                    web_resp = session.get(target_url, timeout=10)
                    if web_resp.status_code == 200:
                        txt = web_resp.text.lower()
                        # Recherche mot clé rapide
                        for sec, cfg in SECTOR_CONFIG.items():
                            if any(k in txt for k in cfg['kw']):
                                res["Secteur"] = f"WEB: {sec}"
                                break
            except Exception as e:
                pass # On ignore les erreurs web pour ne pas bloquer
                
        else:
             res["Statut"] = "⚠️"
             res["Info"] = f"API: {resp.status_code}"

    except Exception as e:
        res["Statut"] = "❌"
        # On affiche l'erreur technique précise
        res["Info"] = str(e)

    return res

# --- INTERFACE ---
st.title("Test de Connexion V8 ⚡")
st.info("Cette version force la connexion directe (Bypass Proxy).")

txt = st.text_area("Entrez un nom (ex: LVMH)")

if st.button("Lancer le test"):
    if txt:
        with st.spinner("Test en cours..."):
            result = process_company(txt)
            st.write(result)
            
            if result["Statut"] == "❌":
                st.error("Diagnostic : Votre ordinateur bloque Python.")
                st.write("Conseil : Essayez de changer de réseau (Partage de connexion 4G).")
