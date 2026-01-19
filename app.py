import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    DateRange, Dimension, Metric, RunReportRequest, OrderBy
)
import plotly.express as px
from datetime import datetime, timedelta
import requests

# --- PAGE CONFIG ---
st.set_page_config(page_title="Executive Tracking System", page_icon="📈", layout="wide")

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

# --- CLIENT INITIALIZATION ---
def get_ga_client():
    credentials_dict = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(credentials_dict)
    return BetaAnalyticsDataClient(credentials=creds)

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
        params = {"event": ["accepted", "opened"], "duration": duration}
        response = requests.get(url, auth=("api", st.secrets["MAILGUN_API_KEY"]), params=params)
        if response.status_code == 200:
            res_data = response.json()
            accepted = res_data.get('stats', [{}])[0].get('accepted', {}).get('total', 0)
            opened = res_data.get('stats', [{}])[0].get('opened', {}).get('total', 0)
            rate = (opened / accepted * 100) if accepted > 0 else 0
            return rate, opened
        return 0, 0
    except: return 0, 0

def run_ga_report(property_id, dimensions, metrics, date_range_start="30daysAgo", date_range_end="today"):
    """Fetch data from GA4"""
    client = get_ga_client()
    request = RunReportRequest(
        property=f"properties/{property_id}",
        dimensions=[Dimension(name=d) for d in dimensions],
        metrics=[Metric(name=m) for m in metrics],
        date_ranges=[DateRange(start_date=date_range_start, end_date=date_range_end)],
    )
    response = client.run_report(request)
    
    data = []
    for row in response.rows:
        row_data = {}
        for i, dim_val in enumerate(row.dimension_values):
            row_data[dimensions[i]] = dim_val.value
        for i, metric_val in enumerate(row.metric_values):
            row_data[metrics[i]] = metric_val.value
        data.append(row_data)
    return pd.DataFrame(data)

# --- SIDEBAR NAVIGATION ---
st.sidebar.image("https://cdn-icons-png.flaticon.com/512/3090/3090116.png", width=80)
st.sidebar.title("Main Menu")
page = st.sidebar.selectbox("Go to:", ["🏠 Home", "📊 AO Dashboard", "📧 Mail Tracking", "🌐 Google Analytics"])

# --- PAGE 1: HOME ---
if page == "🏠 Home":
    st.title("AO & Marketing Intelligence System")
    st.markdown("### Select a module from the sidebar to begin.")

# --- PAGE 2: AO DASHBOARD ---
elif page == "📊 AO Dashboard":
    try:
        df = get_data()
    except Exception as e:
        st.error(f"❌ Connection Error: {e}"); st.stop()

    st.sidebar.divider()
    st.sidebar.header("🗓️ AO Filters")
    min_d, max_d = df['Date'].min(), df['Date'].max()
    date_range = st.sidebar.date_input("Date Range", value=(min_d, max_d))
    sources = st.sidebar.multiselect("Sources", options=df["Source"].unique(), default=df["Source"].unique())
    status_list = st.sidebar.multiselect("Status", options=df["Status"].unique(), default=df["Status"].unique())

    if len(date_range) == 2:
        start_date, end_date = date_range
        df_filtered = df[(df["Date"] >= start_date) & (df["Date"] <= end_date) & (df["Source"].isin(sources)) & (df["Status"].isin(status_list))]
    else: df_filtered = df

    st.title("Appel d'Offres (AO) Tracking")
    st.markdown(f'<div class="big-metric-container"><p class="big-metric-label">Total AO Filtered</p><p class="big-metric-value">{int(df_filtered["Nombre"].sum())}</p></div>', unsafe_allow_html=True)
    st.write("---")
    
    today_dt = datetime.now().date()
    df_today = df[df['Date'] == today_dt]
    st.markdown(f'<div class="today-header">Aujourd\'hui</div>', unsafe_allow_html=True)
    t1, t2, t3, t4 = st.columns(4)
    t1.metric("Scrapé", int(df_today["Nombre"].sum()))
    t2.metric("Accepté", len(df_today[df_today["Status"] == "Accepté"]))
    t3.metric("Refus", len(df_today[df_today["Status"] == "Refus"]))
    t4.metric("Opp", len(df_today[df_today["Status"] == "Opportunité"]))

    st.divider()
    c1, spacer, c2 = st.columns([4.5, 1, 4.5])
    with c1: st.plotly_chart(px.bar(df_filtered.groupby("Source")["Nombre"].count().reset_index(), x="Nombre", y="Source", orientation='h', title="Source Dist."), use_container_width=True)
    with c2: st.plotly_chart(px.pie(df_filtered, names="Status", hole=0.5, title="Status Analysis"), use_container_width=True)

# --- PAGE 3: MAIL TRACKING ---
elif page == "📧 Mail Tracking":
    st.title("📧 Mail Tracking Dashboard")
    df_m = get_mail_data()
    
    st.sidebar.header("🗓️ Mail Filter")
    m_range = st.sidebar.date_input("Range", value=(df_m['Date'].min(), df_m['Date'].max()))
    
    if len(m_range) == 2:
        df_m_filtered = df_m[(df_m['Date'] >= m_range[0]) & (df_m['Date'] <= m_range[1])]
    else: df_m_filtered = df_m

    today_dt = datetime.now().date()
    df_m_today = df_m[df_m['Date'] == today_dt]
    today_rate, _ = get_mailgun_stats("24h")
    
    st.markdown(f'<div class="today-header">Mailing Aujourd\'hui</div>', unsafe_allow_html=True)
    mt1, mt2, mt3, mt4 = st.columns(4)
    mt1.metric("Prospectés", len(df_m_today))
    mt2.metric("Envoyés", len(df_m_today[df_m_today['Email Envoyé '].str.contains('Oui', na=False)]))
    mt3.metric("Open Rate (24h)", f"{today_rate:.1f}%")
    mt4.metric("Réponses", len(df_m_today[df_m_today['Email Reponse '].astype(str).str.strip() != ""]))

    st.divider()
    st.subheader("Timeline Envois")
    st.plotly_chart(px.line(df_m_filtered.groupby('Date').size().reset_index(name='V'), x='Date', y='V'), use_container_width=True)

# --- PAGE 4: GOOGLE ANALYTICS (NEW) ---
elif page == "🌐 Google Analytics":
    st.title("🌐 Website Traffic Intelligence")
    
    # Website Selection
    website = st.sidebar.radio("Select Website:", ["Website 1", "Website 2"])
    property_id = st.secrets["GA_PROPERTY_ID_1"] if website == "Website 1" else st.secrets["GA_PROPERTY_ID_2"]
    
    # Date Filter
    st.sidebar.divider()
    days_to_show = st.sidebar.slider("Days to look back", 7, 90, 30)
    start_date = f"{days_to_show}daysAgo"

    try:
        # 1. Fetch Overview Metrics
        df_overview = run_ga_report(property_id, ["date"], ["activeUsers", "sessions", "engagementRate"], start_date)
        df_overview["engagementRate"] = pd.to_numeric(df_overview["engagementRate"]) * 100
        
        # 2. Fetch Top Pages
        df_pages = run_ga_report(property_id, ["pagePath"], ["screenPageViews"], start_date)
        
        # 3. Fetch Geography (Country & City)
        df_geo = run_ga_report(property_id, ["country", "city"], ["activeUsers"], start_date)
        
        # 4. Fetch Acquisition
        df_channels = run_ga_report(property_id, ["sessionDefaultChannelGroup"], ["sessions"], start_date)

        # --- UI DISPLAY ---
        col1, col2, col3 = st.columns(3)
        with col1:
            total_users = pd.to_numeric(df_overview["activeUsers"]).sum()
            st.metric("Total Active Users", f"{total_users:,}")
        with col2:
            total_sessions = pd.to_numeric(df_overview["sessions"]).sum()
            st.metric("Total Sessions", f"{total_sessions:,}")
        with col3:
            avg_eng = pd.to_numeric(df_overview["engagementRate"]).mean()
            st.metric("Avg Engagement Rate", f"{avg_eng:.1f}%")

        st.divider()

        # Graphs Row 1: Timeline & Channels
        g1, g2 = st.columns([6, 4])
        with g1:
            st.subheader("Users Trend")
            df_overview["date"] = pd.to_datetime(df_overview["date"])
            fig_trend = px.area(df_overview.sort_values("date"), x="date", y="activeUsers", template="plotly_white")
            st.plotly_chart(fig_trend, use_container_width=True)
        with g2:
            st.subheader("Acquisition Channels")
            fig_chan = px.pie(df_channels, names="sessionDefaultChannelGroup", values="sessions", hole=0.4)
            st.plotly_chart(fig_chan, use_container_width=True)

        # Graphs Row 2: Top Pages & Countries
        st.divider()
        g3, g4 = st.columns(2)
        with g3:
            st.subheader("Top 10 Pages")
            df_pages["screenPageViews"] = pd.to_numeric(df_pages["screenPageViews"])
            st.dataframe(df_pages.sort_values("screenPageViews", ascending=False).head(10), use_container_width=True)
        with g4:
            st.subheader("Top Countries")
            df_country = df_geo.groupby("country")["activeUsers"].apply(lambda x: pd.to_numeric(x).sum()).reset_index()
            fig_country = px.bar(df_country.sort_values("activeUsers", ascending=False).head(10), x="activeUsers", y="country", orientation='h')
            st.plotly_chart(fig_country, use_container_width=True)

        # Detailed Geo Table
        with st.expander("Detailed City Breakdown"):
            df_geo["activeUsers"] = pd.to_numeric(df_geo["activeUsers"])
            st.dataframe(df_geo.sort_values(["country", "activeUsers"], ascending=[True, False]), use_container_width=True)

    except Exception as e:
        st.error(f"GA4 Error: {e}")
        st.info("Ensure your Property ID is correct and Service Account has access.")
