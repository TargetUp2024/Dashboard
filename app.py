import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import plotly.express as px
from datetime import datetime
import requests

# --- PAGE CONFIG ---
st.set_page_config(page_title="AO & Mail Tracking System", page_icon="📈", layout="wide")

# --- CUSTOM CSS ---
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .big-metric-container { padding-top: 0px; margin-bottom: -20px; }
    .big-metric-value { font-size: 85px !important; font-weight: 800 !important; color: #1f77b4; line-height: 1; margin: 0; }
    .big-metric-label { font-size: 20px !important; color: #666; text-transform: uppercase; margin-bottom: 5px; }
    .today-header { font-size: 22px; font-weight: 700; color: #2c3e50; margin-top: 20px; margin-bottom: 2px; }
    .today-date { font-size: 16px; color: #7f8c8d; margin-bottom: 15px; }
    [data-testid="stMetricValue"] { font-weight: 700; }
    </style>
    """, unsafe_allow_html=True)

# --- DATA FETCHING FUNCTIONS ---

@st.cache_data(ttl=600)
def get_data():
    """Original AO Data Fetching"""
    credentials_dict = st.secrets["gcp_service_account"]
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(credentials_dict, scopes=scope)
    client = gspread.authorize(creds)
    SHEET_URL = st.secrets["private_gsheet_url"]
    sheet = client.open_by_url(SHEET_URL).sheet1
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    df = df.dropna(subset=['Date', 'Source'])
    df['Date'] = pd.to_datetime(df['Date']).dt.date
    df['Nombre'] = pd.to_numeric(df['Nombre'], errors='coerce').fillna(1)
    return df

@st.cache_data(ttl=600)
def get_mail_data():
    """Mail GSheet Data Fetching"""
    credentials_dict = st.secrets["gcp_service_account"]
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(credentials_dict, scopes=scope)
    client = gspread.authorize(creds)
    MAIL_SHEET_URL = st.secrets["mail_gsheet_url"]
    sheet = client.open_by_url(MAIL_SHEET_URL).worksheet("CLUB DIRIGEANTS")
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    if not df.empty:
        df['Date'] = pd.to_datetime(df['Date']).dt.date
    return df

def get_mailgun_stats(duration="30d"):
    """Fetch Open Rate from Mailgun API"""
    try:
        url = f"https://api.mailgun.net/v3/{st.secrets['MAILGUN_DOMAIN']}/stats/total"
        # API returns counts for various events
        params = {"event": ["accepted", "opened"], "duration": duration}
        response = requests.get(url, auth=("api", st.secrets["MAILGUN_API_KEY"]), params=params)
        if response.status_code == 200:
            res_data = response.json()
            accepted = res_data.get('stats', [{}])[0].get('accepted', {}).get('total', 0)
            opened = res_data.get('stats', [{}])[0].get('opened', {}).get('total', 0)
            rate = (opened / accepted * 100) if accepted > 0 else 0
            return rate, opened
        return 0, 0
    except:
        return 0, 0

# --- SIDEBAR NAVIGATION ---
st.sidebar.image("https://cdn-icons-png.flaticon.com/512/3090/3090116.png", width=80)
st.sidebar.title("Main Menu")
page = st.sidebar.selectbox("Go to:", ["🏠 Home", "📊 View Dashboard", "📧 Mail Tracking"])

# --- PAGE 1: HOME ---
if page == "🏠 Home":
    st.title("Welcome to AO & Mail Tracking")
    st.markdown("### Select a module from the sidebar to begin.")

# --- PAGE 2: AO DASHBOARD (ORIGINAL CODE UNCHANGED) ---
elif page == "📊 View Dashboard":
    try:
        df = get_data()
    except Exception as e:
        st.error(f"❌ Connection Error: {e}"); st.stop()

    st.sidebar.divider()
    st.sidebar.header("🗓️ Filters")
    min_d, max_d = df['Date'].min(), df['Date'].max()
    date_range = st.sidebar.date_input("Date Range", value=(min_d, max_d), min_value=min_d, max_value=max_d)
    sources = st.sidebar.multiselect("Sources", options=df["Source"].unique(), default=df["Source"].unique())
    status_list = st.sidebar.multiselect("Status", options=df["Status"].unique(), default=df["Status"].unique())

    if len(date_range) == 2:
        start_date, end_date = date_range
        df_filtered = df[(df["Date"] >= start_date) & (df["Date"] <= end_date) & 
                         (df["Source"].isin(sources)) & (df["Status"].isin(status_list))]
    else:
        df_filtered = df

    st.title("Appel d'Offres (AO) Tracking")
    st.markdown(f'<div class="big-metric-container"><p class="big-metric-label">Total AO Filtered</p><p class="big-metric-value">{int(df_filtered["Nombre"].sum())}</p></div>', unsafe_allow_html=True)
    st.write("---")

    today_dt = datetime.now().date()
    df_today = df[df['Date'] == today_dt]
    st.markdown(f'<div class="today-header">Aujourd\'hui</div><div class="today-date">{today_dt.strftime("%A %d %B %Y")}</div>', unsafe_allow_html=True)

    t1, t2, t3, t4 = st.columns(4)
    t1.metric("Scrapé Aujourd'hui", int(df_today["Nombre"].sum()))
    t2.metric("Accepté Aujourd'hui", len(df_today[df_today["Status"] == "Accepté"]))
    t3.metric("Refus Aujourd'hui", len(df_today[df_today["Status"] == "Refus"]))
    t4.metric("Opp Aujourd'hui", len(df_today[df_today["Status"] == "Opportunité"]))

    # Conversion KPIs
    st.write("##"); st.subheader("Conversion KPIs")
    c1, c2, c3 = st.columns(3)
    tot = len(df_filtered)
    if tot > 0:
        rate_refus = (len(df_filtered[df_filtered["Status"] == "Refus"]) / tot) * 100
        rate_accep = (len(df_filtered[df_filtered["Status"] == "Accepté"]) / tot) * 100
        count_accep = len(df_filtered[df_filtered["Status"] == "Accepté"])
        rate_opp = (len(df_filtered[df_filtered["Status"] == "Opportunité"]) / count_accep * 100) if count_accep > 0 else 0
    else: rate_refus = rate_accep = rate_opp = 0
    c1.metric("Taux Scraped ➔ Refus", f"{rate_refus:.1f}%")
    c2.metric("Taux Scraped ➔ Accepté", f"{rate_accep:.1f}%")
    c3.metric("Taux Accepté ➔ Opportunité", f"{rate_opp:.1f}%")

    st.divider()
    chart_col_left, spacer, chart_col_right = st.columns([4.5, 1, 4.5])
    with chart_col_left:
        fig_bar = px.bar(df_filtered.groupby("Source")["Nombre"].count().reset_index(), x="Nombre", y="Source", orientation='h', color="Source", template="plotly_white")
        st.plotly_chart(fig_bar, use_container_width=True)
    with chart_col_right:
        fig_pie = px.pie(df_filtered, names="Status", hole=0.5, color_discrete_map={"Refus": "#FF4B4B", "Opportunité": "#00CC96", "Accepté": "#636EFA"})
        st.plotly_chart(fig_pie, use_container_width=True)

# --- PAGE 3: MAIL TRACKING (NEW SECTION ADDED) ---
elif page == "📧 Mail Tracking":
    st.title("📧 Mail Tracking Dashboard")
    
    try:
        df_m = get_mail_data()
        # Fetch Mailgun stats (Global 30d and Today)
        global_open_rate, global_opens = get_mailgun_stats("30d")
        today_open_rate, today_opens = get_mailgun_stats("24h")
    except Exception as e:
        st.error(f"Error: {e}"); st.stop()

    # SECTION: TODAY'S MAIL STATS
    today_dt = datetime.now().date()
    df_m_today = df_m[df_m['Date'] == today_dt]
    
    st.markdown(f'<div class="today-header">Aujourd\'hui (Mailing)</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="today-date">{today_dt.strftime("%A %d %B %Y")}</div>', unsafe_allow_html=True)

    mt1, mt2, mt3, mt4 = st.columns(4)
    with mt1:
        st.metric("Prospectés Aujourd'hui", len(df_m_today))
    with mt2:
        sent_today = len(df_m_today[df_m_today['Email Envoyé '].str.contains('Oui', na=False)])
        st.metric("Envoyés Aujourd'hui", sent_today)
    with mt3:
        # Mailgun Real-time Open Rate for last 24h
        st.metric("Open Rate (Mailgun 24h)", f"{today_open_rate:.1f}%")
    with mt4:
        reponse_today = len(df_m_today[df_m_today['Email Reponse '].astype(str).str.strip() != ""])
        st.metric("Réponses Aujourd'hui", reponse_today)

    st.divider()

    # SECTION: GLOBAL PERFORMANCE
    st.subheader("Performance Globale")
    g1, g2, g3, g4 = st.columns(4)
    with g1:
        st.metric("Total Contacts Database", len(df_m))
    with g2:
        total_sent = len(df_m[df_m['Email Envoyé '].str.contains('Oui', na=False)])
        st.metric("Total Emails Envoyés", total_sent)
    with g3:
        st.metric("Open Rate Global (Mailgun)", f"{global_open_rate:.1f}%", help="Based on last 30 days")
    with g4:
        total_rep = len(df_m[df_m['Email Reponse '].astype(str).str.strip() != ""])
        st.metric("Total Réponses", total_rep)

    st.divider()

    # CHARTS
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Top Secteurs")
        sector_counts = df_m['Sector'].value_counts().reset_index().head(10)
        sector_counts.columns = ['Sector', 'Count']
        st.plotly_chart(px.bar(sector_counts, x='Count', y='Sector', orientation='h', color='Sector', template="plotly_white"), use_container_width=True)

    with col_b:
        st.subheader("Volume par Ville")
        city_counts = df_m['City'].value_counts().reset_index()
        city_counts.columns = ['City', 'Count']
        st.plotly_chart(px.pie(city_counts, names='City', values='Count', hole=0.4), use_container_width=True)

    st.subheader("Chronologie des envois")
    mail_timeline = df_m.groupby('Date').size().reset_index(name='Volume')
    st.plotly_chart(px.area(mail_timeline, x='Date', y='Volume', template="plotly_white"), use_container_width=True)

    with st.expander("🔍 View Raw Mailing Database"):
        st.dataframe(df_m, use_container_width=True, hide_index=True)
