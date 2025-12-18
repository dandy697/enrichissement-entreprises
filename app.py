import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from googlesearch import search
from collections import Counter
import re
import io
import concurrent.futures
import time
import urllib3
import random

# Désactiver les avertissements SSL (Utile pour le scraping gratuit)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(page_title="Enrichissement Entreprises (Gratuit)", page_icon="🕵️", layout="wide")

st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stTextArea textarea {font-size: 14px; font-family: monospace;}
</style>
""", unsafe_allow_html=True)

# --- CONFIGURATION SECTORIELLE ---
SECTOR_CONFIG = {
    "Agriculture / Pêche": {"naf": ["01", "02", "03"], "kw": ["agriculture", "élevage", "vin", "agricole", "bio"]},
    "BTP / Construction": {"naf": ["41", "42", "43"], "kw": ["btp", "construction", "bâtiment", "travaux", "rénovation", "architecte"]},
    "Consulting / IT / Tech": {"naf": ["62", "702", "582"], "kw": ["conseil", "consulting", "esn", "digital", "logiciel", "saas", "data", "web"]},
    "Commerce / Retail": {"naf": ["46", "47"], "kw": ["boutique", "vente", "magasin", "distributeur", "commerce", "e-commerce"]},
    "Finance / Banque / Assur": {"naf": ["64", "65", "66"], "kw": ["banque", "assurance", "crédit", "investissement", "courtier", "finance"]},
    "Immobilier": {"naf": ["68"], "kw": ["immobilier", "agence", "syndic", "location", "gestion", "foncière"]},
    "Industrie / Manufacture": {"naf": ["10", "33"], "kw": ["usine", "fabrication", "industrie", "production", "mécanique", "atelier"]},
    "Santé / Médical": {"naf": ["86", "87"], "kw": ["santé", "médical", "clinique", "docteur", "soins", "pharmacie"]},
    "Hôtellerie / Restauration": {"naf": ["55", "56"], "kw": ["hôtel", "restaurant", "bar", "cuisine", "chef", "repas", "menu"]},
    "Transport / Logistique": {"naf": ["49", "50", "51", "52"], "kw": ["transport", "logistique", "livraison", "camion", "fret", "colis"]},
    "Service Public / Asso": {"naf": ["84", "94"], "kw": ["mairie", "association", "public", "état", "ministère", "collectivité"]}
}

NAF_BLACKLIST = ["7010Z", "6420Z"] # Holdings (Sociétés sans activité propre)

# --- FONCTIONS TECHNIQUES ---

def clean_input(text):
    text = str(text).strip()
    if "@" in text:
        try:
            return text.split('@')[1].split('.')[0]
        except:
            return text
    return text

def get_random_user_agent():
    """Génère une fausse identité de navigateur pour éviter le blocage"""
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/118.0"
    ]
    return random.choice(user_agents)

def analyze_web(company_name):
    """Partie Scraping (Google + Site Web)"""
    try:
        # 1. Recherche Google
        # On fait une pause aléatoire pour ne pas énerver Google (Gratuit = Patience)
        time.sleep(random.uniform(1.0, 2.0))
        
        query = f"{company_name} site officiel france"
        try:
            # Recherche via la librairie googlesearch
            urls = list(search(query, num_results=1, lang="fr", advanced=True))
            if not urls:
                return "Site introuvable", "⭐"
            url = urls[0].url
        except:
            return "Google Bloqué (Réessayez + tard)", "⭐"

        # 2. Visite du site trouvé
        try:
            headers = {"User-Agent": get_random_user_agent()}
            resp = requests.get(url, headers=headers, timeout=10, verify=False)
        except:
            return "Site inaccessible", "⭐"

        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            text_content = soup.get_text().lower()
            
            # Analyse des mots-clés dans le site
            best_sector = "Non déterminé"
            max_score = 0
            
            for sector, config in SECTOR_CONFIG.items():
                score = 0
                for kw in config['kw']:
                    if kw in text_content:
                        score += 1
                
                if score > max_score:
                    max_score = score
                    best_sector = sector
            
            # Vérification des liens sociaux (Github, Doctolib, Tripadvisor...)
            links = [a.get('href', '') for a in soup.find_all('a', href=True)]
            links_str = " ".join(links).lower()
            
            if "github.com" in links_str or "gitlab" in links_str:
                return "Consulting / IT / Tech", "⭐⭐"
            if "tripadvisor" in links_str or "thefork" in links_str:
                return "Hôtellerie / Restauration", "⭐⭐"
            if "doctolib" in links_str:
                return "Santé / Médical", "⭐⭐"

            if max_score > 0:
                return best_sector, "⭐⭐"
            
    except Exception as e:
        return f"Erreur Web: {str(e)[:20]}", "⭐"
    
    return "Site non explicite", "⭐"

def process_company(raw_input):
    clean_name = clean_input(raw_input)
    
    # URL OFFICIELLE DE L'API (C'est ici que vous aviez l'erreur 404)
    api_url = "https://recherche-entreprises.api.gouv.fr/search"
    
    res = {
        "Statut": "❌", "Entrée": raw_input, "Nom Officiel": "-", 
        "Industrie": "-", "Confiance": "-", "Région": "-", "Site Web": "-"
    }
    
    # Etape 1 : API GOUV (Gratuite)
    try:
        headers = {"User-Agent": get_random_user_agent()}
        # On demande 1 résultat, le plus pertinent
        params = {"q": clean_name, "per_page": 1, "limite_etablissements": 1}
        
        response = requests.get(api_url, params=params, headers=headers, timeout=10)
        
        if response.status_code == 200:
            results = response.json()
            if results and len(results) > 0:
                data = results[0]
                
                res["Statut"] = "✅"
                res["Nom Officiel"] = data.get('nom_complet', 'Inconnu')
                cp = data.get('code_postal', '')
                res["Région"] = f"{cp[:2]}" if cp else "-"
                
                # Analyse via code NAF
                naf = data.get('activite_principale', '').replace('.', '')
                found_naf = False
                
                # On ne se fie pas au NAF si c'est une Holding (Blacklist)
                if naf not in [x.replace('.', '') for x in NAF_BLACKLIST]:
                    for sector, config in SECTOR_CONFIG.items():
                        for prefix in config['naf']:
                            if naf.startswith(prefix):
                                res["Industrie"] = sector
                                res["Confiance"] = "⭐⭐⭐ (Officiel)"
                                found_naf = True
                                break
                        if found_naf: break
                
                # Etape 2 : Si NAF pas clair -> WEB SCRAPING
                if not found_naf:
                    web_sector, conf = analyze_web(data.get('nom_complet'))
                    res["Industrie"] = web_sector
                    res["Confiance"] = conf
                    
            else:
                res["Statut"] = "⚠️"
                res["Nom Officiel"] = "Introuvable"
        else:
            res["Statut"] = "❌"
            res["Nom Officiel"] = f"Erreur API: {response.status_code}"

    except Exception as e:
        res["Statut"] = "❌"
        res["Nom Officiel"] = "Erreur Connexion"

    return res

# --- INTERFACE UTILISATEUR ---

st.title("Enrichissement Entreprises 🕵️")
st.markdown("### Outil 100% Gratuit (API Publique + Web Scraping)")
st.info("💡 Astuce : Cet outil utilise votre connexion internet. Ne lancez pas 1000 lignes d'un coup pour éviter d'être bloqué par Google.")

raw_txt = st.text_area("Collez vos noms d'entreprises (un par ligne) :", height=200, placeholder="LVMH\nRenault\nBoulangerie Paul")

if st.button("Lancer l'analyse Gratuite", type="primary"):
    if raw_txt:
        inputs = [x.strip() for x in raw_txt.split('\n') if x.strip()]
        
        results = []
        bar = st.progress(0)
        
        # On limite à 3 recherches en parallèle pour que Google ne nous bloque pas
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            future_to_url = {executor.submit(process_company, i): i for i in inputs}
            for i, future in enumerate(concurrent.futures.as_completed(future_to_url)):
                results.append(future.result())
                bar.progress((i + 1) / len(inputs))
        
        bar.empty()
        df = pd.DataFrame(results)
        
        st.dataframe(df, use_container_width=True)
        
        # Export Excel
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        st.download_button("📥 Télécharger Excel", buffer.getvalue(), "resultats.xlsx")
    else:
        st.warning("Veuillez entrer au moins un nom.")
