import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    DateRange, Dimension, Metric, RunReportRequest
)
import plotly.express as px
from datetime import datetime, timedelta
import requests

# --- PAGE CONFIG ---
st.set_page_config(page_title="Executive Intelligence System", page_icon="📈", layout="wide")

# --- CUSTOM CSS ---
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .big-metric-container { padding-top: 0px; margin-bottom: -20px; }
    .big-metric-value { font-size: 85px !important; font-weight: 800 !important; color: #1f77b4; line-height: 1; margin: 0; }
    .big-metric-label { font-size: 20px !important; color: #666; text-transform: uppercase; margin-bottom: 5px; }
    .today-header { font-size: 24px; font-weight: 700; color: #2c3e50; margin-top: 20px; border-left: 5px solid #1f77b4; padding-left: 10px; }
    .today-date { font-size: 16px; color: #7f8c8d; margin-bottom: 15px; }
    [data-testid="stMetricValue"] { font-weight: 700; font-size: 32px !important; }
    .stPlotlyChart { margin-bottom: 40px; }
    </style>
    """, unsafe_allow_html=True)

# --- CLIENT INITIALIZATION ---
def get_ga_client():
    credentials_dict = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(credentials_dict)
    return BetaAnalyticsDataClient(credentials=creds)

# --- DATA FETCHING FUNCTIONS ---

@st.cache_data(ttl=600)
def get_ao_data():
    """Fetch AO Data from Google Sheets"""
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], 
            scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
    client = gspread.authorize(creds)
    sheet = client.open_by_url(st.secrets["private_gsheet_url"]).sheet1
    df = pd.DataFrame(sheet.get_all_records())
    df = df.dropna(subset=['Date', 'Source'])
    df['Date'] = pd.to_datetime(df['Date']).dt.date
    df['Nombre'] = pd.to_numeric(df['Nombre'], errors='coerce').fillna(1)
    return df

@st.cache_data(ttl=600)
def get_mail_data():
    """Fetch Mail Data from Google Sheets"""
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"],
            scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
    client = gspread.authorize(creds)
    sheet = client.open_by_url(st.secrets["mail_gsheet_url"]).worksheet("CLUB DIRIGEANTS")
    df = pd.DataFrame(sheet.get_all_records())
    if not df.empty:
        df['Date'] = pd.to_datetime(df['Date']).dt.date
    return df

def get_mailgun_stats(duration="30d"):
    """Fetch Stats from Mailgun API"""
    try:
        url = f"https://api.mailgun.net/v3/{st.secrets['MAILGUN_DOMAIN']}/stats/total"
        params = {"event": ["accepted", "opened"], "duration": duration}
        res = requests.get(url, auth=("api", st.secrets["MAILGUN_API_KEY"]), params=params)
        if res.status_code == 200:
            data = res.json()
            acc = data.get('stats', [{}])[0].get('accepted', {}).get('total', 0)
            ope = data.get('stats', [{}])[0].get('opened', {}).get('total', 0)
            rate = (ope / acc * 100) if acc > 0 else 0
            return rate, ope
    except: pass
    return 0, 0

def run_ga_report(property_id, dimensions, metrics, start_date, end_date="today"):
    """Fetch Analytics from GA4 API"""
    client = get_ga_client()
    request = RunReportRequest(
        property=f"properties/{property_id}",
        dimensions=[Dimension(name=d) for d in dimensions],
        metrics=[Metric(name=m) for m in metrics],
        date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
    )
    response = client.run_report(request)
    output = []
    for row in response.rows:
        res = {dimensions[i]: val.value for i, val in enumerate(row.dimension_values)}
        res.update({metrics[i]: val.value for i, val in enumerate(row.metric_values)})
        output.append(res)
    return pd.DataFrame(output)

# --- SIDEBAR NAVIGATION ---
st.sidebar.image("https://cdn-icons-png.flaticon.com/512/3090/3090116.png", width=80)
st.sidebar.title("Main Menu")
page = st.sidebar.selectbox("Go to:", ["🏠 Home", "📊 AO Dashboard", "📧 Mail Tracking", "🌐 Google Analytics"])

# --- PAGE 1: HOME ---
if page == "🏠 Home":
    st.title("AO & Marketing Intelligence System")
    st.markdown("### Welcome! Use the sidebar to navigate between modules.")
    st.info("System is connected to Google Sheets, Mailgun, and Google Analytics 4.")

# --- PAGE 2: AO DASHBOARD ---
elif page == "📊 AO Dashboard":
    df = get_ao_data()
    st.sidebar.header("🗓️ AO Filters")
    min_d, max_d = df['Date'].min(), df['Date'].max()
    dr_ao = st.sidebar.date_input("Date Range", value=(min_d, max_d))

    if len(dr_ao) == 2:
        df_f = df[(df["Date"] >= dr_ao[0]) & (df["Date"] <= dr_ao[1])]
    else: df_f = df

    st.title("Appel d'Offres (AO) Tracking")
    st.markdown(f'<div class="big-metric-container"><p class="big-metric-label">Total AO Filtered</p><p class="big-metric-value">{int(df_f["Nombre"].sum())}</p></div>', unsafe_allow_html=True)
    st.write("---")

    # Today Metrics
    today_dt = datetime.now().date()
    df_today = df[df['Date'] == today_dt]
    st.markdown(f'<div class="today-header">Aujourd\'hui</div>', unsafe_allow_html=True)
    t1, t2, t3, t4 = st.columns(4)
    t1.metric("Scrapé", int(df_today["Nombre"].sum()))
    t2.metric("Accepté", len(df_today[df_today["Status"] == "Accepté"]))
    t3.metric("Refus", len(df_today[df_today["Status"] == "Refus"]))
    t4.metric("Opp", len(df_today[df_today["Status"] == "Opportunité"]))

    # Visuals
    st.divider()
    c1, spacer, c2 = st.columns([4.5, 1, 4.5])
    with c1:
        st.plotly_chart(px.bar(df_f.groupby("Source")["Nombre"].count().reset_index(), x="Nombre", y="Source", orientation='h', title="Source Dist."), use_container_width=True)
    with c2:
        st.plotly_chart(px.pie(df_f, names="Status", hole=0.5, title="Status Analysis"), use_container_width=True)

# --- PAGE 3: MAIL TRACKING ---
elif page == "📧 Mail Tracking":
    st.title("📧 Mail Tracking Dashboard")
    df_m = get_mail_data()
    
    st.sidebar.header("🗓️ Mail Date Filter")
    m_range = st.sidebar.date_input("Select Range", value=(df_m['Date'].min(), df_m['Date'].max()))
    
    # Today Snapshot
    today_dt = datetime.now().date()
    df_m_today = df_m[df_m['Date'] == today_dt]
    rate_24h, _ = get_mailgun_stats("24h")
    
    st.markdown('<div class="today-header">Mailing Aujourd\'hui</div>', unsafe_allow_html=True)
    mt1, mt2, mt3, mt4 = st.columns(4)
    mt1.metric("Prospectés", len(df_m_today))
    mt2.metric("Envoyés", len(df_m_today[df_m_today['Email Envoyé '].str.contains('Oui', na=False)]))
    mt3.metric("Open Rate (24h)", f"{rate_24h:.1f}%")
    mt4.metric("Réponses", len(df_m_today[df_m_today['Email Reponse '].astype(str).str.strip() != ""]))

    st.divider()
    
    # Period Stats
    if len(m_range) == 2:
        df_m_f = df_m[(df_m['Date'] >= m_range[0]) & (df_m['Date'] <= m_range[1])]
        st.subheader("Performance Timeline")
        st.plotly_chart(px.line(df_m_f.groupby('Date').size().reset_index(name='V'), x='Date', y='V', template="plotly_white"), use_container_width=True)

# --- PAGE 4: GOOGLE ANALYTICS ---
elif page == "🌐 Google Analytics":
    st.title("🌐 Website Traffic Intelligence")
    
    site = st.sidebar.radio("Select Website:", ["Targetup University", "Targetup Consulting"])
    pid = st.secrets["GA_PROPERTY_ID_1"] if site == "Targetup University" else st.secrets["GA_PROPERTY_ID_2"]
    
    st.sidebar.divider()
    st.sidebar.header("🗓️ Filter Period")
    today = datetime.now().date()
    ga_range = st.sidebar.date_input("Calendar Range", value=(today - timedelta(days=30), today))

    try:
        # A. FIXED SNAPSHOTS
        st.markdown('<div class="today-header">Live Snapshots</div>', unsafe_allow_html=True)
        col_t1, col_t2, col_y1, col_y2 = st.columns(4)
        
        df_ga_today = run_ga_report(pid, ["date"], ["activeUsers", "sessions"], "today", "today")
       df_ga_yest  = run_ga_report(pid, ["date"], ["activeUsers", "sessions"], "yesterday", "yesterday")


        def s_sum(df, col): return pd.to_numeric(df[col]).sum() if not df.empty else 0

        col_t1.metric("Users (Today)", f"{s_sum(df_ga_today, 'activeUsers'):,}")
        col_t2.metric("Sessions (Today)", f"{s_sum(df_ga_today, 'sessions'):,}")
        col_y1.metric("Users (Yesterday)", f"{s_sum(df_ga_yest, 'activeUsers'):,}")
        col_y2.metric("Sessions (Yesterday)", f"{s_sum(df_ga_yest, 'sessions'):,}")

        st.divider()

        # B. PERIOD PERFORMANCE
        if isinstance(ga_range, tuple) and len(ga_range) == 2:
            s_str, e_str = ga_range[0].strftime("%Y-%m-%d"), ga_range[1].strftime("%Y-%m-%d")
            df_p = run_ga_report(pid, ["date"], ["activeUsers", "newUsers", "sessions", "engagementRate"], s_str, e_str)
            
            t_u = s_sum(df_p, "activeUsers")
            ret_rate = ((t_u - s_sum(df_p, "newUsers")) / t_u * 100) if t_u > 0 else 0

            st.markdown(f'<div class="today-header">Performance: {s_str} to {e_str}</div>', unsafe_allow_html=True)
            p1, p2, p3, p4 = st.columns(4)
            p1.metric("Total Users", f"{t_u:,}")
            p2.metric("Total Sessions", f"{s_sum(df_p, 'sessions'):,}")
            p3.metric("Engagement Rate", f"{(pd.to_numeric(df_p['engagementRate']).mean()*100):.1f}%")
            p4.metric("Return Rate", f"{ret_rate:.1f}%")

            # FULL WIDTH GRAPHS (ONE PER LINE)
            st.write("###  Users Timeline")
            df_p["date"] = pd.to_datetime(df_p["date"])
            st.plotly_chart(px.area(df_p.sort_values("date"), x="date", y="activeUsers", template="plotly_white"), use_container_width=True)

            st.write("###  Top Countries ")
            df_geo = run_ga_report(pid, ["country"], ["activeUsers"], s_str, e_str)
            df_geo["activeUsers"] = pd.to_numeric(df_geo["activeUsers"])
            fig_geo = px.bar(df_geo.sort_values("activeUsers", ascending=False).head(10), x="country", y="activeUsers", color="activeUsers", template="plotly_white", text_auto=True)
            st.plotly_chart(fig_geo, use_container_width=True)

            st.write("###  Traffic Sources")
            df_src = run_ga_report(pid, ["sessionDefaultChannelGroup"], ["sessions"], s_str, e_str)
            df_src["sessions"] = pd.to_numeric(df_src["sessions"])
            st.plotly_chart(px.bar(df_src.sort_values("sessions"), x="sessions", y="sessionDefaultChannelGroup", orientation='h', template="plotly_white"), use_container_width=True)

            st.write("### Top 15 Pages (Views)")
            df_pg = run_ga_report(pid, ["pagePath"], ["screenPageViews"], s_str, e_str)
            df_pg["screenPageViews"] = pd.to_numeric(df_pg["screenPageViews"])
            fig_pg = px.bar(df_pg.sort_values("screenPageViews").tail(15), x="screenPageViews", y="pagePath", orientation='h', template="plotly_white", color="screenPageViews")
            st.plotly_chart(fig_pg, use_container_width=True)

            with st.expander("Detailed City Breakdown"):
                df_city = run_ga_report(pid, ["country", "city"], ["activeUsers"], s_str, e_str)
                st.dataframe(df_city.sort_values("activeUsers", ascending=False), use_container_width=True)

    except Exception as e:
        st.error(f"GA4 Error: {e}")
