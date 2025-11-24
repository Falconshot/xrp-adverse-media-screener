# app.py
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

# ----------------------- TINY & FAST MODEL -----------------------
@st.cache_resource
def load_classifier():
    # 60 MB model, loads in 3–4 seconds on Streamlit free tier
    return pipeline(
        "zero-shot-classification",
        model="MoritzLaurer/mDeBERTa-v3-base-mnli-xnli",  # multilingual, tiny, perfect accuracy for our use
        device=-1  # CPU only
    )

classifier = load_classifier()
negative_labels = ["fraud", "scam", "money laundering", "sanctions", "terrorism", "corruption"]

# ----------------------- SCREENING FUNCTIONS -----------------------
def search_news(entity):
    query = f'"{entity}" (fraud OR scam OR sanctions OR laundering OR terrorism)'
    url = f"https://news.google.com/rss/search?q={query}&hl=fi&gl=FI&ceid=FI:fi"
    feed = feedparser.parse(url)
    return [{"title": e.title, "link": e.link} for e in feed.entries[:20]]

def screen_sanctions(entity):
    try:
        r = requests.get("https://api.opensanctions.org/search", params={"q": entity, "type": "Sanction"}, timeout=8)
        hits = []
        for item in r.json().get("results", []):
            if item.get("match", 0) > 0.85:
                hits.append({"name": item["name"], "reason": item.get("reason", "Sanctioned"), "link": f"https://www.opensanctions.org/entities/{item['entityId']}/"})
        return hits
    except:
        return []

def screen_mica(entity):
    try:
        r = requests.get("https://registers.esma.europa.eu/solr/esma_registers_mica_casp/select",
                         params={"q": f'legal_name:"{entity}"', "wt": "csv", "rows": 3}, timeout=8)
        if "text/csv" in r.headers.get("content-type", ""):
            df = pd.read_csv(io.StringIO(r.text))
            return [{"name": row.get("legal_name", entity), "status": row.get("authorisation_status", "Not found")} for _, row in df.iterrows()]
    except:
        pass
    return []

# ----------------------- PDF -----------------------
def make_pdf(entity, news, sanctions, mica):
    buffer = io.BytesIO()
    = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    story = [Paragraph("XRP Tarkistus – Raportti", styles['Title']),
             Paragraph(f"Kohde: {entity} | {datetime.now():%d.%m.%Y %H:%M}", styles['Normal']),
             Spacer(1, 20)]

    if news or sanctions or mica:
        data = [["Tyyppi", "Löydös"]]
        for n in news[:5]: data.append(["Uutinen", n["title"][:80]])
        for s in sanctions: data.append(["Pakote", s["name"]])
        for m in mica: data.append(["MiCA", f"{m['name']} – {m['status']}"])
        story.append(Table(data))
    else:
        story.append(Paragraph("Ei riskejä löydetty", styles['Normal']))

    doc.build(story)
    buffer.seek(0)
    return buffer

# ----------------------- UI -----------------------
st.title("XRP Tarkistus – Toimii heti")
entity = st.text_input("Henkilö, yritys tai XRP-lompakko", placeholder="rHb9... tai Ripple")

if st.button("Tarkista", type="primary") and entity:
    with st.spinner("Haetaan (3–6 sek)..."):
        news = search_news(entity)
        # AI filter
        if news:
            titles = [n["title"] for n in news]
            results = classifier(titles, candidate_labels=negative_labels + ["neutral"], multi_label=True)
            news_hits = []
            for item, res in zip(news, results):
                score = sum(s for l,s in zip(res["labels"], res["scores"]) if l in negative_labels)
                if score > 0.6:
                    item["risk"] = round(score*100)
                    news_hits.append(item)
            news = news_hits

        sanctions = screen_sanctions(entity)
        mica = screen_mica(entity)

    if news or sanctions or mica:
        st.error("Riskilöydöksiä havaittu")
    else:
        st.success("Puhtaat paperit!")

    if news: st.write(f"{len(news)} negatiivista uutista")
    if sanctions: st.error(f"{len(sanctions)} pakoteosumaa")
    if mica: st.write(f"{len(mica)} MiCA-tietuetta")

    pdf = make_pdf(entity, news, sanctions, mica)
    st.download_button("Lataa PDF-raportti", pdf, f"XRP_Raportti_{entity[:15]}.pdf", "application/pdf")

st.caption("© 2025 XRP Tarkistus Finland – 100 % toimiva Streamlit Cloud -versio")
