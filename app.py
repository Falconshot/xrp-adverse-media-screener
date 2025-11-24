# app.py  ←  PRO VERSION – WALLET NAMING + SCORING + FINNISH UBO

import streamlit as st
import requests
import feedparser
import pandas as pd
import io
import urllib.parse
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from transformers import pipeline

# ----------------------- LOAD MODEL WITH SPINNER -----------------------
st.set_page_config(page_title="XRP Tarkistus Pro", page_icon="Finland")
st.title("XRP Tarkistus Pro")
st.caption("Pro AML-screening XRP-lompakoille ja nimille • Pakotelistat • MiCA • PRH UBO • Riskipisteet")

with st.spinner("Ladataan tekoälymallia (ensimmäinen kerta kestää 15–30 sek)..."):
    @st.cache_resource
    def load_classifier():
        return pipeline("zero-shot-classification",
                        model="MoritzLaurer/mDeBERTa-v3-base-mnli-xnli",
                        device=-1)
    classifier = load_classifier()

st.success("Valmis! Voit nyt tehdä tarkistuksia")

# ----------------------- PRO SCREENING -----------------------
negative_labels = ["fraud", "scam", "money laundering", "sanctions", "terrorism", "corruption"]

def is_xrp_wallet(entity):
    return entity.startswith('r') and len(entity) == 34  # Basic XRP address check

def get_wallet_label(entity):
    try:
        r = requests.get(f"https://bithomp.com/api/v2/account/{entity}", timeout=8)
        if r.status_code == 200:
            data = r.json()
            return data.get("username", "") or data.get("service", "") or "Unknown Wallet"
    except:
        return "Unknown Wallet"

def search_news(entity):
    try:
        search = f'"{entity}" (fraud OR scam OR sanctions OR laundering OR terrorism OR huijaus OR rahanpesu OR pakote)'
        url = f"https://news.google.com/rss/search?q={urllib.parse.quote(search)}&hl=fi&gl=FI&ceid=FI:fi"
        feed = feedparser.parse(url)
        return [{"title": e.title, "link": e.link} for e in feed.entries[:25]]
    except:
        return []

def screen_sanctions(entity):
    try:
        r = requests.get("https://api.opensanctions.org/search", params={"q": entity, "type": "Sanction"}, timeout=8)
        hits = []
        for item in r.json().get("results", []):
            if item.get("match", 0) > 0.85:
                hits.append({
                    "name": item["name"],
                    "reason": item.get("reason", "Sanctioned"),
                    "link": f"https://www.opensanctions.org/entities/{item.get('entityId','')}/"
                })
        return hits
    except:
        return []

def screen_mica(entity):
    try:
        r = requests.get("https://registers.esma.europa.eu/solr/esma_registers_mica_casp/select",
                         params={"q": f'legal_name:"{entity}"', "wt": "csv", "rows": 5}, timeout=8)
        if "text/csv" in r.headers.get("content-type", ""):
            df = pd.read_csv(io.StringIO(r.text))
            return [{"name": row.get("legal_name", entity),
                     "status": row.get("authorisation_status", "Not found")}
                    for _, row in df.iterrows()]
    except:
        pass
    return []

def screen_prh_ubo(entity):
    try:
        # PRH/YTJ open data for company search (free API)
        r = requests.get("https://avoindata.prh.fi/bis/v1", params={"name": entity}, timeout=8)
        if r.status_code == 200:
            data = r.json().get("results", [])
            if data:
                company = data[0]
                business_id = company.get("businessId", "")
                ubo_note = "UBO-ilmoitus tehty" if company.get("beneficialOwners", False) else "UBO-ilmoitus puuttuu – Tilaa täysi UBO-extract PRH:lta (€8)"
                return [{"name": company.get("name", entity),
                         "business_id": business_id,
                         "ubo_status": ubo_note}]
        return []
    except:
        return []

# ----------------------- PRO SCORING -----------------------
def calculate_risk(news, sanctions, mica, ubo):
    score = 0
    explanation = []

    if news:
        news_score = min(len(news) * 10, 30)
        score += news_score
        explanation.append(f"Negatiiviset uutiset: +{news_score}% ({len(news)} osumaa)")

    if sanctions:
        sanctions_score = min(len(sanctions) * 50, 100)
        score += sanctions_score
        explanation.append(f"Pakoteosumat: +{sanctions_score}% (korkea riski)")

    if mica and any(m["status"] != "Granted" for m in mica):
        mica_score = 20
        score += mica_score
        explanation.append(f"MiCA-valtuutus puuttuu/ vireillä: +{mica_score}%")

    if ubo and any("puuttuu" in u["ubo_status"] for u in ubo):
        ubo_score = 10
        score += ubo_score
        explanation.append(f"UBO-ilmoitus puuttuu: +{ubo_score}%")

    score = min(score, 100)
    risk_level = "Korkea" if score > 70 else "Kohtalainen" if score > 30 else "Matala"
    return score, risk_level, explanation

# ----------------------- PDF – PRO LAYOUT -----------------------
def make_pdf(entity, news, sanctions, mica, ubo, score, risk_level, explanation):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=50)
    styles = getSampleStyleSheet()

    if 'CustomTitle' not in styles:
        styles.add(ParagraphStyle(name='CustomTitle', fontSize=24, alignment=TA_CENTER, textColor=colors.darkblue, spaceAfter=30))

    story = [
        Paragraph("XRP Tarkistus Pro – AML Raportti", styles['CustomTitle']),
        Spacer(1, 20),
        Paragraph(f"<b>Kohde:</b> {entity}", styles['Normal']),
        Paragraph(f"<b>Päivämäärä:</b> {datetime.now():%d.%m.%Y %H:%M}", styles['Normal']),
        Paragraph(f"<b>Riskipisteet:</b> {score}/100 ({risk_level})", styles['Normal']),
        Spacer(1, 30)
    ]

    # Explanation
    story.append(Paragraph("Riskiselitys:", styles['Bold']))
    for exp in explanation:
        story.append(Paragraph(exp, styles['Normal']))

    # Data tables
    if news or sanctions or mica or ubo:
        data = [["Tyyppi", "Löydös"]]
        for n in news[:6]: data.append(["Uutinen", n["title"][:100]])
        for s in sanctions: data.append(["Pakote", f"{s['name']} – {s['reason']}"])
        for m in mica: data.append(["MiCA", f"{m['name']} – {m['status']}"])
        for u in ubo: data.append(["PRH UBO", f"{u['name']} – {u['ubo_status']}"])
        story.append(Table(data, colWidths=[80, 420]))
    else:
        story.append(Paragraph("Ei riskejä havaittu", styles['Normal']))

    story.append(Spacer(1, 50))
    story.append(Paragraph("© 2025 XRP Tarkistus Finland Pro", styles['Normal']))
    doc.build(story)
    buffer.seek(0)
    return buffer

# ----------------------- UI -----------------------
entity = st.text_input("Anna nimi, yritys tai XRP-lompakko", placeholder="Ripple, rHb9..., Binance")

if st.button("Tarkista nyt", type="primary") and entity:
    with st.spinner("Haetaan tietoja (3–6 sek)..."):
        # Pro: Wallet labeling
        if is_xrp_wallet(entity):
            label = get_wallet_label(entity)
            st.info(f"Lompakko label: {label}")
            entity = f"{entity} ({label})"  # Use label for further screening

        news_raw = search_news(entity)
        news_hits = []
        if news_raw:
            titles = [n["title"] for n in news_raw]
            results = classifier(titles, candidate_labels=negative_labels + ["neutral"], multi_label=True)
            for item, res in zip(news_raw, results):
                score = sum(s for l,s in zip(res["labels"], res["scores"]) if l in negative_labels)
                if score > 0.6:
                    item["risk"] = round(score*100)
                    news_hits.append(item)

        sanctions = screen_sanctions(entity)
        mica = screen_mica(entity)
        ubo = screen_prh_ubo(entity)

        score, risk_level, explanation = calculate_risk(news_hits, sanctions, mica, ubo)

    st.subheader(f"Riski: {score}/100 ({risk_level})")
    for exp in explanation:
        st.write(exp)

    if news_hits: st.write(f"{len(news_hits)} negatiivista uutista")
    if sanctions: st.error(f"{len(sanctions)} pakoteosumaa")
    if mica: st.write(f"{len(mica)} MiCA-tietuetta")
    if ubo: st.write(f"{len(ubo)} PRH UBO-tietuetta")

    pdf = make_pdf(entity, news_hits, sanctions, mica, ubo, score, risk_level, explanation)
    st.download_button(
        "Lataa Pro PDF-raportti (€19)",
        pdf,
        file_name=f"XRP_Pro_Raportti_{entity.replace(' ', '_')[:20]}_{datetime.now():%Y%m%d}.pdf",
        mime="application/pdf"
    )

st.caption("© 2025 XRP Tarkistus Finland Pro – MiCA-ready AML")
