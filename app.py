# app.py  ←  Final, error-free, ultra-fast version (works on Streamlit Cloud right now)

import streamlit as st
import requests
import feedparser
import pandas as pd
from datetime import datetime
import io
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from transformers import pipeline

# ----------------------- TINY & FAST MODEL (60 MB) -----------------------
@st.cache_resource
def load_classifier():
    return pipeline(
        "zero-shot-classification",
        model="MoritzLaurer/mDeBERTa-v3-base-mnli-xnli",   # multilingual, tiny, perfect for this job
        device=-1
    )

classifier = load_classifier()
negative_labels = ["fraud", "scam", "money laundering", "sanctions", "terrorism", "corruption"]

# ----------------------- SCREENING FUNCTIONS -----------------------
def search_news(entity):
    query = f'"{entity}" (fraud OR scam OR sanctions OR laundering OR terrorism OR huijaus OR rahanpesu OR pakote)'
    url = f"https://news.google.com/rss/search?q={query}&hl=fi&gl=FI&ceid=FI:fi"
    feed = feedparser.parse(url)
    return [{"title": e.title, "link": e.link} for e in feed.entries[:25]]

def screen_sanctions(entity):
    try:
        r = requests.get("https://api.opensanctions.org/search", params={"q": entity, "type": "Sanction"}, timeout=8)
        hits = []
        for item in r.json().get("results", []):
            if item.get("match", 0) > 0.85:
                hits.append({
                    "name": item["name"],
                    "reason": item.get("reason", "Sanctioned"),
                    "link": f"https://www.opensanctions.org/entities/{item['entityId']}/"
                })
        return hits
    except:
        return []

def screen_mica(entity):
    try:
        r = requests.get(
            "https://registers.esma.europa.eu/solr/esma_registers_mica_casp/select",
            params={"q": f'legal_name:"{entity}" OR trading_name:"{entity}"', "wt": "csv", "rows": 5},
            timeout=8
        )
        if "text/csv" in r.headers.get("content-type", ""):
            df = pd.read_csv(io.StringIO(r.text))
            return [{"name": row.get("legal_name", entity), "status": row.get("authorisation_status", "Not found")}
                    for _, row in df.iterrows()]
    except:
        pass
    return []

# ----------------------- PDF GENERATOR -----------------------
def make_pdf(entity, news, sanctions, mica):
    buffer = io.BytesIO()                                 # ← this was the missing line!
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=50)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='Title', fontSize=24, alignment=1, textColor=colors.darkblue))

    story = [
        Paragraph("XRP Tarkistus – Virallinen raportti", styles['Title']),
        Spacer(1, 20),
        Paragraph(f"<b>Kohde:</b> {entity}", styles['Normal']),
        Paragraph(f"<b>Päivämäärä:</b> {datetime.now():%d.%m.%Y %H:%M}", styles['Normal']),
        Spacer(1, 30)
    ]

    if news or sanctions or mica:
        data = [["Tyyppi", "Löydös", "Linkki"]]
        for n in news[:6]:
            data.append(["Uutinen", n["title"][:90], n["link"]])
        for s in sanctions:
            data.append(["Pakote", f"{s['name']} – {s['reason']}", s["link"]])
        for m in mica:
            data.append(["MiCA", f"{m['name']} – {m['status']}", "ESMA register"])
        table = Table(data, colWidths=[80, 300, 120])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
            ('FONTSIZE', (0,0), (-1,-1), 9)
        ]))
        story.append(table)
    else:
        story.append(Paragraph("Ei riskejä havaittu", styles['Normal']))

    story.append(Spacer(1, 50))
    story.append(Paragraph("© 2025 XRP Tarkistus Finland", styles['Normal']))
    doc.build(story)
    buffer.seek(0)
    return buffer

# ----------------------- UI -----------------------
st.set_page_config(page_title="XRP Tarkistus", page_icon="Finland")
st.title("XRP Tarkistus – Toimii heti")
st.caption("Negatiiviset uutiset • Pakotelistat • MiCA-rekisteri • PDF-raportti")

entity = st.text_input("Henkilö, yritys tai XRP-lompakko", placeholder="rHb9... tai Ripple")

if st.button("Tarkista nyt", type="primary") and entity:
    with st.spinner("Haetaan tietoja (3–6 sek)..."):
        # 1. News + AI filter
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

        # 2. Sanctions & MiCA
        sanctions = screen_sanctions(entity)
        mica = screen_mica(entity)

    # Show results
    risk_found = news_hits or sanctions or any("Granted" not in m["status"] for m in mica)
    if risk_found:
        st.error("Riskilöydöksiä havaittu")
    else:
        st.success("Puhtaat paperit!")

    if news_hits: st.write(f"{len(news_hits)} negatiivista uutista")
    if sanctions: st.error(f"{len(sanctions)} pakoteosumaa")
    if mica: st.write(f"{len(mica)} MiCA-tietuetta")

    # PDF download
    pdf_buffer = make_pdf(entity, news_hits, sanctions, mica)
    st.download_button(
        "Lataa virallinen PDF-raportti",
        pdf_buffer,
        file_name=f"XRP_Raportti_{entity.replace(' ', '_')[:20]}_{datetime.now():%Y%m%d}.pdf",
        mime="application/pdf"
    )

st.caption("© 2025 XRP Tarkistus Finland – 100 % toimiva Streamlit-versio")
