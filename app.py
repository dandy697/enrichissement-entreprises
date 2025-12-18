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

# --- 1. DESACTIVATION SECURITE SSL (Pour forcer le passage) ---
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(page_title="Enrichissement Entreprises (V7)", page_icon="🚀", layout="wide")

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

NAF_BLACKLIST = ["7010Z", "6420Z"]

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
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    ]
    return random.choice(user_agents)

def analyze_web(company_name):
    """Partie Web Scraping (Google)"""
    try:
        # Pause anti-ban Google
        time.sleep(random.uniform(1.5, 3.0))
        
        query = f"{company_name} site officiel france"
        try:
            # Recherche Google
            urls = list(search(query, num_results=1, lang="fr", advanced=True))
            if not urls:
                return "Site introuvable", "⭐"
            url = urls[0].url
        except:
            return "Google Bloqué", "⭐"

        # Visite du site (Avec Verify=False pour passer les antivirus)
        try:
            headers = {"User-Agent": get_random_user_agent()}
            resp = requests.get(url, headers=headers, timeout=10, verify=False)
        except:
            return "Site inaccessible", "⭐"

        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            text_content = soup.get_text().lower()
            
            # 1. Mots clés
            best_sector = "Non déterminé"
            max_score = 0
            for sector, config in SECTOR_CONFIG.items():
                score = sum(1 for kw in config['kw'] if kw in text_content)
                if score > max_score:
                    max_score = score
                    best_sector = sector
            
            # 2. Liens sociaux (Signature)
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
            
    except Exception:
        return "Erreur Web", "⭐"
    
    return "Site non explicite", "⭐"

def process_company(raw_input):
    clean_name = clean_input(raw_input)
    api_url = "https://recherche-entreprises.api.gouv.fr/search"
    
    res = {
        "Statut": "❌", "Entrée": raw_input, "Nom Officiel": "-", 
        "Industrie": "-", "Confiance": "-", "Région": "-", "Site Web": "-"
    }
    
    # --- APPEL API GOUV (Corrigé avec verify=False) ---
    try:
        headers = {"User-Agent": get_random_user_agent()}
        params = {"q": clean_name, "per_page": 1, "limite_etablissements": 1}
        
        # ICI : verify=False est la clé pour corriger votre erreur "Erreur Connexion"
        response = requests.get(api_url, params=params, headers=headers, timeout=15, verify=False)
        
        if response.status_code == 200:
            results = response.json()
            if results and len(results) > 0:
                data = results[0]
                
                res["Statut"] = "✅"
                res["Nom Officiel"] = data.get('nom_complet', 'Inconnu')
                cp = data.get('code_postal', '')
                res["Région"] = f"{cp[:2]}" if cp else "-"
                
                # Analyse NAF
                naf = data.get('activite_principale', '').replace('.', '')
                found_naf = False
                
                if naf not in [x.replace('.', '') for x in NAF_BLACKLIST]:
                    for sector, config in SECTOR_CONFIG.items():
                        for prefix in config['naf']:
                            if naf.startswith(prefix):
                                res["Industrie"] = sector
                                res["Confiance"] = "⭐⭐⭐ (Officiel)"
                                found_naf = True
                                break
                        if found_naf: break
                
                # Analyse Web si besoin
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
        # On affiche l'erreur exacte pour comprendre si ça plante encore
        res["Statut"] = "❌"
        res["Nom Officiel"] = f"Err: {str(e)[:30]}"

    return res

# --- INTERFACE ---
st.title("Enrichissement Entreprises (V7)")
st.markdown("### Outil Gratuit & Robuste")
st.info("💡 Version avec sécurité SSL désactivée pour contourner les blocages réseau.")

raw_txt = st.text_area("Collez vos noms d'entreprises :", height=200, placeholder="Keyrus\nLVMH")

if st.button("Lancer l'analyse V7", type="primary"):
    if raw_txt:
        inputs = [x.strip() for x in raw_txt.split('\n') if x.strip()]
        results = []
        bar = st.progress(0)
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            future_to_url = {executor.submit(process_company, i): i for i in inputs}
            for i, future in enumerate(concurrent.futures.as_completed(future_to_url)):
                results.append(future.result())
                bar.progress((i + 1) / len(inputs))
        
        bar.empty()
        df = pd.DataFrame(results)
        st.dataframe(df, use_container_width=True)
        
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        st.download_button("📥 Télécharger Excel", buffer.getvalue(), "resultats.xlsx")
    else:
        st.warning("Veuillez entrer au moins un nom.")
