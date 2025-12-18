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

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(page_title="Enrichissement entreprises", page_icon="🏢", layout="wide")

# Masquer le menu hamburger et ajuster le style
st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stTextArea textarea {font-size: 14px; font-family: monospace;}
</style>
""", unsafe_allow_html=True)

# --- 1. CONFIGURATION INTELLIGENTE ---

SECTOR_CONFIG = {
    "Agriculture / Livestock / Seafood": {"naf": ["01", "02", "03"], "kw": ["agriculture", "élevage", "pêche", "agricole", "bio"]},
    "Banking": {"naf": ["641"], "kw": ["banque", "crédit", "bancaire", "épargne", "financement"]},
    "Chemicals": {"naf": ["20"], "kw": ["chimie", "laboratoire", "molécules"]},
    "Communication / Media / Telecom": {"naf": ["59", "60", "61", "63"], "kw": ["télécom", "média", "publicité", "fibre", "internet", "agence"]},
    "Construction": {"naf": ["41", "42", "43"], "kw": ["btp", "construction", "bâtiment", "travaux", "chantier", "rénovation"]},
    "Consulting / IT Services": {"naf": ["6202", "6203", "6209", "702"], "kw": ["conseil", "consulting", "esn", "stratégie", "audit", "digital", "intégration"]},
    "CPG (Consumer Goods)": {"naf": [], "kw": ["grande consommation", "fmcg", "cosmétique", "hygiène", "shampoing"]},
    "Education": {"naf": ["85"], "kw": ["école", "formation", "université", "enseignement", "learning"]},
    "Energy / Utilities": {"naf": ["35", "05", "06", "09"], "kw": ["énergie", "électricité", "gaz", "pétrole", "solaire", "éolien"]},
    "Finance / Real Estate": {"naf": ["68", "642", "643", "649"], "kw": ["immobilier", "gestion", "patrimoine", "investissement", "foncière", "assets"]},
    "Food / Beverages": {"naf": ["10", "11"], "kw": ["alimentaire", "boisson", "agroalimentaire", "food", "nutrition", "snack"]},
    "Healthcare / Medical Services": {"naf": ["86", "87", "88"], "kw": ["santé", "clinique", "hôpital", "soins", "médecin", "médical", "patient"]},
    "Hotels / Restaurants": {"naf": ["55", "56"], "kw": ["hôtel", "restaurant", "tourisme", "hébergement", "cuisine", "chef"]},
    "Insurance": {"naf": ["65"], "kw": ["assurance", "mutuelle", "courtier", "protection", "sinistre"]},
    "Luxury": {"naf": [], "kw": ["luxe", "prestige", "haute couture", "joaillerie", "exception", "craftsmanship"]},
    "Manufacturing / Industry": {"naf": ["13", "14", "15", "16", "17", "22", "23", "24", "25", "26", "27", "28", "29", "30", "31", "32"], "kw": ["industrie", "usine", "fabrication", "mécanique", "production"]},
    "Not For Profit": {"naf": ["94"], "kw": ["association", "ong", "fondation", "bénévolat", "non lucratif"]},
    "Pharmaceutics": {"naf": ["21"], "kw": ["pharmacie", "médicament", "biotech", "laboratoire", "thérapeutique"]},
    "Public Administration": {"naf": ["84"], "kw": ["administration", "état", "ministère", "service public", "mairie"]},
    "Retail": {"naf": ["47"], "kw": ["commerce", "vente", "magasin", "boutique", "retail", "distributeur"]},
    "Tech / Software": {"naf": ["582", "6201", "631"], "kw": ["logiciel", "saas", "tech", "software", "application", "ia", "plateforme", "data"]},
    "Transportation / Logistics": {"naf": ["49", "50", "51", "52", "53"], "kw": ["transport", "logistique", "livraison", "fret", "colis", "supply chain"]}
}

NAF_BLACKLIST = ["7010Z", "6420Z"] # Holdings -> On force le Web

# --- 2. FONCTIONS TECHNIQUES ---

def clean_input(text):
    """Extrait le nom de l'entreprise si c'est un email."""
    text = str(text).strip()
    if "@" in text:
        try:
            return text.split('@')[1].split('.')[0]
        except:
            return text
    return text

def clean_text_content(text):
    return re.sub(r'[^\w\s]', '', text.lower()) if text else ""

def get_session():
    """Crée une session qui imite un vrai navigateur (Anti-Bot)."""
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7"
    })
    return s

def analyze_web(company_name, session):
    """
    Scraping Avancé V2 :
    1. Signature Sociale (Liens sortants)
    2. Open Graph (Description cachée)
    3. Mots-clés classiques
    """
    try:
        # Recherche URL via Google
        query = f"{company_name} site officiel france"
        urls = list(search(query, num_results=1, lang="fr"))
        if not urls:
            return "Web Introuvable", 0, "⭐"
            
        url = urls[0]
        try:
            resp = session.get(url, timeout=5)
        except:
            return "Site Inaccessible", 0, "⭐"

        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # --- A. SIGNATURE SOCIALE (Social Fingerprinting) ---
            # On cherche des liens spécifiques qui trahissent l'activité
            links = [a.get('href', '') for a in soup.find_all('a', href=True)]
            links_str = " ".join(links).lower()
            
            if any(x in links_str for x in ['github.com', 'gitlab.com']):
                return "Tech / Software", 100, "⭐⭐" # Forte probabilité Tech
            if 'doctolib.fr' in links_str:
                return "Healthcare / Medical Services", 100, "⭐⭐"
            if any(x in links_str for x in ['tripadvisor', 'thefork', 'ubereats', 'deliveroo']):
                return "Hotels / Restaurants", 100, "⭐⭐"

            # --- B. OPEN GRAPH & CONTENU ---
            # On cherche la description meta (souvent plus propre)
            text_content = ""
            og_desc = soup.find("meta", property="og:description")
            if og_desc:
                text_content += og_desc.get("content", "") + " "
            
            # On ajoute le titre et les H1
            text_content += " ".join([t.get_text() for t in soup.find_all(['title', 'h1'])])
            
            # Comptage mots-clés
            clean = clean_text_content(text_content)
            words = clean.split()
            counts = Counter(words)
            
            best_score = 0
            best_sector = "Autre"
            
            for sector, config in SECTOR_CONFIG.items():
                score = sum(counts[kw] for kw in config['kw'] if kw in counts)
                if score > best_score:
                    best_score = score
                    best_sector = sector
            
            if best_score > 0:
                return best_sector, best_score, "⭐⭐" # Déduit par sémantique
            
    except Exception:
        pass
    
    return "Non identifié", 0, "⭐"

def process_single_company(raw_input):
    """Fonction exécutée par chaque 'Worker' en parallèle."""
    search_term = clean_input(raw_input)
    api_url = "https://recherche-entreprises.api.gouv.fr/search"
    session = get_session()
    
    res = {
        "Statut": "❌", "Entrée": raw_input, "Nom Officiel": "-", 
        "Industrie": "-", "Confiance": "-", "Région": "-", 
        "Effectif": "-", "Lien Annuaire": "-"
    }
    
    try:
        # Appel API Gouv
        r = session.get(api_url, params={"q": search_term, "per_page": 1}, timeout=3)
        if r.status_code == 200 and r.json():
            data = r.json()[0]
            res["Nom Officiel"] = data.get('nom_complet')
            res["Statut"] = "✅"
            res["Adresse"] = data.get('adresse', '')
            res["Effectif"] = data.get('tranche_effectif_salarie', 'NC')
            res["Lien Annuaire"] = f"https://annuaire-entreprises.data.gouv.fr/entreprise/{data.get('siren')}"
            
            # Région simple
            cp = data.get('code_postal', '')
            res["Région"] = f"Dep. {cp[:2]}" if cp else "-"

            # --- ANALYSE SECTORIELLE ---
            naf = data.get('activite_principale', '').replace('.', '')
            found_naf = False
            
            # 1. Test Code NAF
            if naf and naf not in [x.replace('.', '') for x in NAF_BLACKLIST]:
                for sector, config in SECTOR_CONFIG.items():
                    for prefix in config['naf']:
                        if naf.startswith(prefix):
                            res["Industrie"] = sector
                            res["Confiance"] = "⭐⭐⭐"
                            found_naf = True
                            break
                    if found_naf: break
            
            # 2. Si échec NAF ou Blacklist -> Web Scraping
            if not found_naf:
                web_sector, score, conf = analyze_web(data.get('nom_complet'), session)
                res["Industrie"] = web_sector
                res["Confiance"] = conf

    except Exception as e:
        res["Statut"] = "⚠️"
        
    return res

# --- 3. INTERFACE UTILISATEUR ---

st.title("Enrichissement entreprises")
st.header("Recherche d'entreprise")
st.markdown("Trouvez le **secteur d'activité précis** grâce aux données officielles et au site web.")

tab1, tab2 = st.tabs(["📋 Copier-Coller", "📂 Import Excel"])
inputs = []

with tab1:
    st.markdown("##### Copier-Coller")
    st.markdown("Collez vos emails ou noms d'entreprises (un par ligne)")
    raw_txt = st.text_area("", height=150, placeholder="contact@keyrus.com\nCarrefour\nLVMH")
    if raw_txt:
        inputs = [x.strip() for x in raw_txt.split('\n') if x.strip()]

with tab2:
    st.markdown("##### Import Excel")
    up_file = st.file_uploader("Fichier .xlsx (Noms en 1ère colonne)", type=["xlsx"])
    if up_file:
        df = pd.read_excel(up_file)
        if not df.empty:
            inputs = df.iloc[:, 0].astype(str).tolist()

# --- MOTEUR D'EXECUTION (MULTITHREADING) ---
if st.button("Lancer l'analyse", type="primary"):
    if not inputs:
        st.warning("Veuillez saisir des données.")
    else:
        results = []
        bar = st.progress(0)
        status = st.empty()
        
        # Exécution Parallèle (5 à la fois)
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_input = {executor.submit(process_single_company, i): i for i in inputs}
            
            for idx, future in enumerate(concurrent.futures.as_completed(future_to_input)):
                data = future.result()
                results.append(data)
                # Mise à jour barre
                prog = (idx + 1) / len(inputs)
                bar.progress(prog)
                status.text(f"Analyse en cours : {idx+1}/{len(inputs)}")
        
        status.success("Terminé !")
        time.sleep(1)
        status.empty()
        bar.empty()
        
        df_res = pd.DataFrame(results)
        
        # --- CONFIGURATION DU TABLEAU ---
        st.dataframe(
            df_res,
            column_config={
                "Lien Annuaire": st.column_config.LinkColumn("Lien Annuaire", display_text="Voir"),
                "Statut": st.column_config.TextColumn("Statut", width="small"),
                # Largeur forcée pour éviter le retour à la ligne
                "Industrie": st.column_config.TextColumn("Industrie", width="large"),
                # Infobulle (Tooltip)
                "Confiance": st.column_config.TextColumn(
                    "Confiance", 
                    help="⭐⭐⭐ = Source Officielle (NAF)\n⭐⭐ = Web (Signature Sociale/Mots-clés)\n⭐ = Incertain"
                )
            },
            use_container_width=True
        )
        
        # Export Excel
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_res.to_excel(writer, index=False)
        st.download_button("📥 Télécharger Excel", buffer.getvalue(), "enrichissement_entreprises.xlsx")