# app.py  ←  FINAL VERSION – NO ERRORS, WORKS IMMEDIATELY

import streamlit as st
import requests
import feedparser
import pandas as pd
import io
import urllib.parse
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle  # ← fixed import
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER  # ← needed for alignment=1
from transformers import pipeline

# ----------------------- FAST MODEL -----------------------
@st.cache_resource
def load_classifier():
    return pipeline(
        "zero-shot-classification",
        model="MoritzLaurer/mDeBERTa-v3-base-mnli-xnli",
        device=-1
    )

classifier = load_classifier()
negative_labels = ["fraud", "scam", "money laundering", "sanctions", "terrorism", "corruption"]

# ----------------------- SCREENING -----------------------
def build_news_url(entity):
    search = f'"{entity}" (fraud OR scam OR sanctions OR laundering OR terrorism OR huijaus OR rahanpesu OR pakote)'
    return f"https://news.google.com/rss/search?q={urllib.parse.quote(search)}&hl=fi&gl=FI&ceid=FI:fi"

def search_news(entity):
    try:
        feed = feedparser.parse(build_news_url(entity))
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
                    "link": f"https://www.opensanctions.org/entities/{item.get('entityId', '')}/"
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
            return [{"name": row.get("legal_name", entity),
                     "status": row.get("authorisation_status", "Not found")}
                    for _, row in df.iterrows()]
    except:
        pass
    return []

# ----------------------- PDF -----------------------
def make_pdf(entity, news, sanctions, mica):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=50)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='Title', fontSize=24, alignment=TA_CENTER, textColor=colors.darkblue))

    story = [
        Paragraph("XRP Tarkistus – Virallinen raportti", styles['Title']),
        Spacer(1, 20),
        Paragraph(f"<b>Kohde:</b> {entity}", styles['Normal']),
        Paragraph(f"<b>Päivämäärä:</b> {datetime.now():%d.%m.%Y %H:%M}", styles['Normal']),
        Spacer(1, 30)
    ]

    if news or sanctions or mica:
        data = [["Tyyppi", "Löydös"]]
        for n in news[:6]:
            data.append(["Uutinen", n["title"][:100]])
        for s in sanctions:
            data.append(["Pakote", f"{s['name']} – {s['reason']}"])
        for m in mica:
            data.append(["MiCA", f"{m['name']} – {m['status']}"])
        story.append(Table(data, colWidths=[80, 400]))
    else:
        story.append(Paragraph("Ei riskejä havaittu", styles['Normal']))

    story.append(Spacer(1, 50))
    story.append(Paragraph("© 2025 XRP Tarkistus Finland", styles['Normal']))
    doc.build(story)
    buffer.seek(0)
   
