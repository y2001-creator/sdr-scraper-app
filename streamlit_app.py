import streamlit as st
import pandas as pd
import urllib.request
import urllib.parse
import json
import time
import re
import os
from bs4 import BeautifulSoup
import ssl
import altair as alt

st.set_page_config(page_title="SDR Scraper 360", page_icon="⚡", layout="wide", initial_sidebar_state="expanded")

# --- CUSTOM CSS ---
st.markdown("""
<style>
/* Dashboard background and main container */
.stApp {
    background-color: #0E1222;
    color: #A0AEC0;
}

/* Sidebar styling */
[data-testid="stSidebar"] {
    background-color: #161B2E;
    border-right: 1px solid #2D3748;
}

[data-testid="stSidebar"] * {
    color: #E2E8F0;
}

/* Headers and text */
h1, h2, h3, h4, .stMarkdown p {
    color: #FFFFFF;
}

/* Card metrics (custom CSS classes) */
.metric-card {
    background-color: #1A1F36;
    border: 1px solid #2A2F45;
    border-radius: 10px;
    padding: 20px;
    margin-bottom: 20px;
    color: #fff;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
}
.metric-title {
    font-size: 14px;
    color: #A0AEC0;
    margin-bottom: 5px;
}
.metric-value {
    font-size: 28px;
    font-weight: 700;
    margin-bottom: 5px;
}
.metric-delta {
    font-size: 12px;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: 4px;
    background-color: rgba(72, 187, 120, 0.1);
    color: #48BB78;
    display: inline-block;
}

/* Forms and Inputs */
.stTextInput > div > div > input {
    background-color: #1A1F36;
    color: #FFFFFF;
    border: 1px solid #2D3748;
    border-radius: 6px;
}
.stTextInput > div > div > input:focus {
    border-color: #6366F1;
}

/* Primary Button */
.stButton > button {
    background-color: #6366F1 !important;
    color: white !important;
    border-radius: 6px !important;
    border: none !important;
    padding: 0.5rem 1rem !important;
    font-weight: 600 !important;
    width: 100%;
}
.stButton > button:hover {
    background-color: #4F46E5 !important;
}

/* Expander/Dataframe */
.stDataFrame {
    background-color: #1A1F36;
    border-radius: 10px;
    border: 1px solid #2D3748;
}

/* Hide Streamlit default hamburger & footer */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# -----------------
# FUNCIONES NÚCLEO
# -----------------
@st.cache_data(show_spinner=False)
def extract_company_data(item):
    name = item.get("name") or "No disponible"
    if str(name).strip() == "": name = "No disponible"
    address = item.get("full_address") or item.get("address")
    if not address:
        street = item.get("street", "")
        city = item.get("city", "")
        if street or city: address = f"{street} {city}".strip()
    if not address or str(address).strip() == "": address = "No disponible"
    phone = item.get("phone") or item.get("phone_numbers") or "No disponible"
    if isinstance(phone, list) and len(phone) > 0: phone = phone[0]
    if str(phone).strip() == "": phone = "No disponible"
    
    email = "No disponible"
    if item.get("emails") and isinstance(item.get("emails"), list) and len(item.get("emails")) > 0:
        email = item.get("emails")[0]
    elif item.get("email_1"): email = item.get("email_1")
    elif item.get("email"): email = item.get("email")
    elif item.get("contacts"):
        contacts = item.get("contacts")
        if isinstance(contacts, list):
            for c in contacts:
                if isinstance(c, dict) and c.get("email"):
                    email = c.get("email")
                    break
                elif isinstance(c, str) and "@" in c:
                    email = c
                    break
        elif isinstance(contacts, str) and "@" in contacts: email = contacts
        elif isinstance(contacts, dict) and contacts.get("email"): email = contacts.get("email")

    website = item.get("site") or item.get("website") or item.get("domain") or item.get("url")
    if not website:
        def find_website(obj):
            if isinstance(obj, str):
                if (".com" in obj or ".com.ar" in obj or "www." in obj) and "@" not in obj: return obj
            elif isinstance(obj, list):
                for v in obj:
                    res = find_website(v)
                    if res: return res
            elif isinstance(obj, dict):
                for k, v in obj.items():
                    res = find_website(v)
                    if res: return res
            return None
        website = find_website(item) or "No disponible"
    if str(website).strip() == "": website = "No disponible"

    linkedin = "No disponible"
    if item.get("linkedin") and isinstance(item.get("linkedin"), str):
        linkedin = item.get("linkedin")
    else:
        socials = item.get("socials") or item.get("social_networks") or item.get("social_links", [])
        if isinstance(socials, dict) and socials.get("linkedin"):
            linkedin = socials.get("linkedin")
        elif isinstance(socials, list):
            for link in socials:
                if isinstance(link, str) and "linkedin.com" in link:
                    linkedin = link
                    break
        if linkedin == "No disponible":
            def find_linkedin(obj):
                if isinstance(obj, str) and "linkedin.com/company" in obj: return obj
                elif isinstance(obj, list):
                    for v in obj:
                        res = find_linkedin(v)
                        if res: return res
                elif isinstance(obj, dict):
                    for k, v in obj.items():
                        res = find_linkedin(v)
                        if res: return res
                return None
            linkedin = find_linkedin(item) or "No disponible"

    return {
        "Empresa": name,
        "Direccion": address,
        "Telefono": phone,
        "Email": email,
        "SitioWeb": website,
        "LinkedInEmpresa": linkedin,
        "Instagram": "No disponible",
        "Facebook": "No disponible"
    }

def scrape_contact_info(url, serper_key, company_name):
    if "googleusercontent.com" in url or "googleapis.com" in url or not url.startswith("http"): return None
    extracted = {"email": None, "linkedin": None, "instagram": None, "facebook": None}
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    html_content = ""
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
            html_content = response.read().decode('utf-8', errors='ignore')
    except Exception:
        html_content = None

    if html_content:
        soup = BeautifulSoup(html_content, 'html.parser')
        emails_found = set(re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', html_content))
        valid_emails = [e for e in emails_found if not e.endswith(('.png', '.jpg', '.jpeg', '.gif', '.css', '.js'))]
        if valid_emails: extracted["email"] = valid_emails[0]
        for a in soup.find_all('a', href=True):
            href = a['href']
            if "linkedin.com/company" in href and not extracted["linkedin"]: extracted["linkedin"] = href
            elif "instagram.com" in href and not extracted["instagram"]: extracted["instagram"] = href
            elif "facebook.com" in href and not extracted["facebook"]: extracted["facebook"] = href
                
    if not html_content or (not extracted["email"] and not extracted["linkedin"]):
        domain = urllib.parse.urlparse(url).netloc
        search_query = f'site:{domain} ("@" OR "instagram.com" OR "facebook.com" OR "linkedin.com/company")'
        try:
            sreq = urllib.request.Request("https://google.serper.dev/search", data=json.dumps({"q": search_query}).encode("utf-8"), method="POST")
            sreq.add_header("X-API-KEY", serper_key)
            sreq.add_header("Content-Type", "application/json")
            with urllib.request.urlopen(sreq, timeout=10) as s_response:
                for item in json.loads(s_response.read().decode()).get("organic", []):
                    snippet, link = item.get("snippet", ""), item.get("link", "")
                    if not extracted["email"]:
                        s_emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', snippet)
                        if s_emails: extracted["email"] = s_emails[0]
                    if "linkedin.com/company" in link and not extracted["linkedin"]: extracted["linkedin"] = link
                    elif "instagram.com" in link and not extracted["instagram"]: extracted["instagram"] = link
                    elif "facebook.com" in link and not extracted["facebook"]: extracted["facebook"] = link
        except Exception:
            pass
    return extracted

def enrich_c_level(companies, api_key):
    serper_url = "https://google.serper.dev/search"
    for c in companies:
        if c["Empresa"] == "No disponible":
            c["NombreDirectivo"] = "No disponible"
            c["Cargo"] = "No disponible"
            c["LinkedInDirectivo"] = "No disponible"
            continue
        search_query = f'site:linkedin.com/in/ ("CEO" OR "Founder" OR "Director" OR "Fundador" OR "Dueño") "{c["Empresa"]}"'
        try:
            req = urllib.request.Request(serper_url, data=json.dumps({"q": search_query}).encode("utf-8"), method="POST")
            req.add_header("X-API-KEY", api_key)
            req.add_header("Content-Type", "application/json")
            with urllib.request.urlopen(req) as response:
                serper_data = json.loads(response.read().decode())
                d_name, d_title, d_linkedin = "No disponible", "No disponible", "No disponible"
                if "organic" in serper_data and len(serper_data["organic"]) > 0:
                    first = serper_data["organic"][0]
                    title_str = first.get("title", "")
                    parts = title_str.split(" - ")
                    if len(parts) >= 2:
                        d_name = parts[0].strip()
                        d_title = parts[1].strip().split(" |")[0]
                    else:
                        d_name = title_str.split(" |")[0]
                    d_linkedin = first.get("link", "No disponible")
                c["NombreDirectivo"] = d_name
                c["Cargo"] = d_title
                c["LinkedInDirectivo"] = d_linkedin
        except Exception:
            c["NombreDirectivo"] = "No disponible"
            c["Cargo"] = "No disponible"
            c["LinkedInDirectivo"] = "No disponible"

# -----------------
# INTERFAZ (UI)
# -----------------

# Sidebar
with st.sidebar:
    st.markdown("### ⚡ Dashdark X SDR")
    st.text_input("🔍 Search for...", placeholder="Type here...")
    
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("**All pages**")
    st.button("🏠 Dashboard", key="nav_dash", type="secondary")
    st.button("📊 Reports", key="nav_reports", type="primary") # Active look
    st.button("📦 Products", key="nav_prod", type="secondary")
    st.button("📋 Tasks", key="nav_tasks", type="secondary")
    
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("**Account**")
    outscraper_key = st.text_input("Outscraper API Key", value="NGE4NjZjZDQ5YzBmNGZkNDgzNjVjNmJiNTk2MzVkMGF8MzBlYzQ3NzE1MQ", type="password")
    serper_key = st.text_input("Serper API Key", value="0e34f7a5bcf1bf4db7f5d9b77ba4e273d11fabb1", type="password")


# Main Area
colTop1, colTop2 = st.columns([0.8, 0.2])
with colTop1:
    st.markdown("<h3>Welcome back, John</h3>", unsafe_allow_html=True)
    st.markdown("<p style='color:#A0AEC0; font-size: 14px;'>Launch new extraction commands and report B2B traffic.</p>", unsafe_allow_html=True)
with colTop2:
    st.button("Create report", type="primary")

st.markdown("<br>", unsafe_allow_html=True)

# Metrics Row
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.markdown("""
    <div class="metric-card">
        <div class="metric-title">👁 Total Leads Scraped</div>
        <div class="metric-value">1,402 <span class="metric-delta">28.4% ↗</span></div>
    </div>
    """, unsafe_allow_html=True)
with col2:
    st.markdown("""
    <div class="metric-card">
        <div class="metric-title">📧 Emails Enriched</div>
        <div class="metric-value">845 <span class="metric-delta">12.6% ↗</span></div>
    </div>
    """, unsafe_allow_html=True)
with col3:
    st.markdown("""
    <div class="metric-card">
        <div class="metric-title">👔 C-Level Found</div>
        <div class="metric-value">756 <span class="metric-delta">3.1% ↗</span></div>
    </div>
    """, unsafe_allow_html=True)
with col4:
    st.markdown("""
    <div class="metric-card">
        <div class="metric-title">⭐ Campaign Success</div>
        <div class="metric-value">12.3% <span class="metric-delta">1.5% ↗</span></div>
    </div>
    """, unsafe_allow_html=True)

# Scraper Box
st.markdown("#### 🎯 Launch New Target Extraction")
with st.container():
    st.markdown('<div class="metric-card" style="margin-bottom: 30px;">', unsafe_allow_html=True)
    with st.form("scraping_form"):
        f_col1, f_col2, f_col3 = st.columns([2, 2, 1])
        with f_col1:
            nicho = st.text_input("Nicho / Rubro", placeholder="Ej: Agencias de Marketing")
        with f_col2:
            ubicacion = st.text_input("Ubicación", placeholder="Ej: Madrid, España")
        with f_col3:
            st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
            submitted = st.form_submit_button("Extraer Leads")
    st.markdown('</div>', unsafe_allow_html=True)

# Execution Logic
if submitted and nicho and ubicacion:
    if not outscraper_key or not serper_key:
        st.error("Por favor, introduce las API Keys en el panel lateral.")
    else:
        query = f"{nicho} {ubicacion}"
        encoded_query = urllib.parse.quote(query)
        url = f"https://api.outscraper.com/maps/search-v2?query={encoded_query}&limit=20&async=false"
        
        with st.status("🚀 Iniciando extracción...", expanded=True) as status:
            st.write("Fase 1: Extrayendo empresas de Google Maps (Outscraper)...")
            req = urllib.request.Request(url)
            req.add_header('X-API-KEY', outscraper_key)
            try:
                with urllib.request.urlopen(req) as response:
                    data = json.loads(response.read().decode())
            except Exception as e:
                st.error(f"Error HTTP Outscraper: {e}")
                st.stop()
                
            companies_raw = []
            if "data" in data and len(data["data"]) > 0:
                companies_raw = data["data"][0]
                
            companies = []
            for item in companies_raw: companies.append(extract_company_data(item))
                
            if not companies:
                status.update(label="Fallido", state="error", expanded=False)
                st.warning("No se encontraron empresas para esa búsqueda.")
                st.stop()
                
            st.write("Fase 1.5: Visitando sitios web y extrayendo correos y Redes Sociales...")
            for i, c in enumerate(companies):
                if c["SitioWeb"] != "No disponible":
                    scraped = scrape_contact_info(c["SitioWeb"], serper_key, c["Empresa"])
                    if scraped:
                        if c["Email"] == "No disponible" and scraped["email"]: c["Email"] = scraped["email"]
                        if c["LinkedInEmpresa"] == "No disponible" and scraped["linkedin"]: c["LinkedInEmpresa"] = scraped["linkedin"]
                        c["Instagram"] = scraped["instagram"] or "No disponible"
                        c["Facebook"] = scraped["facebook"] or "No disponible"
                        
            st.write("Fase 2: Enriqueciendo perfiles directivos en LinkedIn...")
            enrich_c_level(companies, serper_key)
            status.update(label="Extracción Completada!", state="complete", expanded=False)
        
        st.markdown("#### Reports overview")
        df = pd.DataFrame(companies)
        cols = ["Empresa", "Direccion", "Telefono", "SitioWeb", "Email", "LinkedInEmpresa", "Instagram", "Facebook", "NombreDirectivo", "Cargo", "LinkedInDirectivo"]
        df = df[cols]
        
        # Display the custom styled dataframe
        st.dataframe(df, use_container_width=True, height=400)
        
        # Download button
        csv = df.to_csv(index=False).encode('utf-8')
        col_down1, _ = st.columns([1, 4])
        with col_down1:
            st.download_button(
                label="📥 Export Data (CSV)",
                data=csv,
                file_name=f'Leads_{nicho}_{ubicacion}.csv',
                mime='text/csv',
            )
