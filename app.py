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
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"],
            scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
    client = gspread.authorize(creds)
    sheet = client.open_by_url(st.secrets["mail_gsheet_url"]).worksheet("CLUB DIRIGEANTS")
    df = pd.DataFrame(sheet.get_all_records())
    if not df.empty:
        df['Date'] = pd.to_datetime(df['Date']).dt.date
    return df

def get_mailgun_stats(duration="30d"):
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
    st.sidebar.header("🗓️ AO Filters")
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

    st.subheader("Activité Timeline")
    df_timeline = df_filtered.groupby('Date').size().reset_index(name='counts')
    st.plotly_chart(px.area(df_timeline, x='Date', y='counts', template="plotly_white"), use_container_width=True)

# --- PAGE 3: MAIL TRACKING ---
elif page == "📧 Mail Tracking":
    st.title("📧 Mail Tracking Dashboard")
    
    try:
        df_m = get_mail_data()
    except Exception as e:
        st.error(f"Error loading data: {e}"); st.stop()

    # --- SIDEBAR DATE FILTER (Mini Calendar) ---
    st.sidebar.divider()
    st.sidebar.header("🗓️ Mail Date Filter")
    m_min, m_max = df_m['Date'].min(), df_m['Date'].max()
    mail_date_range = st.sidebar.date_input("Select Range", value=(m_min, m_max), min_value=m_min, max_value=m_max)

    # Filter data based on sidebar calendar
    if isinstance(mail_date_range, tuple) and len(mail_date_range) == 2:
        start_m, end_m = mail_date_range
        df_m_filtered = df_m[(df_m['Date'] >= start_m) & (df_m['Date'] <= end_m)]
        # Fetch Mailgun stats relative to days selected (approx)
        days_diff = (end_m - start_m).days
        duration_str = f"{days_diff if days_diff > 0 else 1}d"
        open_rate, opens = get_mailgun_stats(duration_str)
    else:
        df_m_filtered = df_m
        open_rate, opens = get_mailgun_stats("30d")

    # Fetch Today's fixed stats from Mailgun
    today_rate, today_opens = get_mailgun_stats("24h")

    # --- SECTION: AUJOURD'HUI (FIXED) ---
    today_dt = datetime.now().date()
    df_m_today = df_m[df_m['Date'] == today_dt]
    
    st.markdown(f'<div class="today-header">Aujourd\'hui (Mailing)</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="today-date">{today_dt.strftime("%A %d %B %Y")}</div>', unsafe_allow_html=True)

    mt1, mt2, mt3, mt4 = st.columns(4)
    mt1.metric("Prospectés Aujourd'hui", len(df_m_today))
    mt2.metric("Envoyés Aujourd'hui", len(df_m_today[df_m_today['Email Envoyé '].str.contains('Oui', na=False)]))
    mt3.metric("Open Rate (Mailgun 24h)", f"{today_rate:.1f}%")
    mt4.metric("Réponses Aujourd'hui", len(df_m_today[df_m_today['Email Reponse '].astype(str).str.strip() != ""]))

    st.divider()

    # --- SECTION: FILTERED PERFORMANCE (BASED ON CALENDAR) ---
    st.subheader("Performance sur la période sélectionnée")
    g1, g2, g3, g4 = st.columns(4)
    g1.metric("Contacts dans la période", len(df_m_filtered))
    g2.metric("Emails Envoyés", len(df_m_filtered[df_m_filtered['Email Envoyé '].str.contains('Oui', na=False)]))
    g3.metric("Open Rate (Mailgun)", f"{open_rate:.1f}%")
    g4.metric("Réponses Reçues", len(df_m_filtered[df_m_filtered['Email Reponse '].astype(str).str.strip() != ""]))

    st.divider()

    # Graph Timeline
    st.subheader("Volume des envois sur la période")
    mail_timeline = df_m_filtered.groupby('Date').size().reset_index(name='Volume')
    st.plotly_chart(px.line(mail_timeline, x='Date', y='Volume', markers=True, template="plotly_white"), use_container_width=True)

    with st.expander("🔍 View Raw Mailing Database"):
        st.dataframe(df_m_filtered, use_container_width=True, hide_index=True)


# --- PAGE 1: HOME ---
if page == "🏠 Home":
    st.title("AO & Marketing Intelligence System")
    st.markdown("### Welcome! Use the sidebar to navigate.")

# --- PAGE 2: AO DASHBOARD ---
elif page == "📊 AO Dashboard":
    df = get_ao_data()
    st.sidebar.header("🗓️ AO Filters")
    min_d, max_d = df['Date'].min(), df['Date'].max()
    dr_ao = st.sidebar.date_input("Date Range", value=(min_d, max_d))
    if len(dr_ao) == 2:
        df_f = df[(df["Date"] >= dr_ao[0]) & (df["Date"] <= dr_ao[1])]
        st.title("Appel d'Offres Tracking")
        st.metric("Total AO", int(df_f["Nombre"].sum()))
        st.plotly_chart(px.pie(df_f, names="Status", hole=0.5), use_container_width=True)

# --- PAGE 3: MAIL TRACKING ---
elif page == "📧 Mail Tracking":
    st.title("📧 Mail Tracking Dashboard")
    df_m = get_mail_data()
    # (Existing Mail logic here...)

# --- PAGE 4: GOOGLE ANALYTICS (WITH FILTERS) ---
elif page == "🌐 Google Analytics":
    st.title("🌐 Website Traffic Intelligence")
    
    site = st.sidebar.radio("Select Website:", ["Targetup University", "Targetup Consulting"])
    pid = st.secrets["GA_PROPERTY_ID_1"] if site == "Targetup University" else st.secrets["GA_PROPERTY_ID_2"]
    
    st.sidebar.divider()
    st.sidebar.header("🗓️ Global Filters")
    today = datetime.now().date()
    ga_range = st.sidebar.date_input("Calendar Range", value=(today - timedelta(days=30), today))

    try:
        if isinstance(ga_range, tuple) and len(ga_range) == 2:
            s_str, e_str = ga_range[0].strftime("%Y-%m-%d"), ga_range[1].strftime("%Y-%m-%d")
            
            # Fetch Master Data for Filtering
            # We fetch all necessary dimensions in one report to allow cross-filtering
            with st.spinner('Fetching Analytics Data...'):
                df_master = run_ga_report(
                    pid, 
                    ["date", "sessionDefaultChannelGroup", "country", "pagePath"], 
                    ["activeUsers", "newUsers", "sessions", "screenPageViews", "engagementRate"], 
                    s_str, e_str
                )

            if df_master.empty:
                st.warning("No data found for this period.")
            else:
                # Convert metrics to numeric
                cols_to_fix = ["activeUsers", "newUsers", "sessions", "screenPageViews", "engagementRate"]
                for col in cols_to_fix:
                    df_master[col] = pd.to_numeric(df_master[col], errors='coerce').fillna(0)

                # --- SIDEBAR FILTERS ---
                st.sidebar.subheader("🔍 Refine Results")
                
                selected_countries = st.sidebar.multiselect("Filter by Country", options=sorted(df_master["country"].unique()))
                selected_sources = st.sidebar.multiselect("Filter by Source Type", options=sorted(df_master["sessionDefaultChannelGroup"].unique()))
                selected_pages = st.sidebar.multiselect("Filter by Page Path", options=sorted(df_master["pagePath"].unique()))

                # Apply Filters to Dataframe
                df_filtered = df_master.copy()
                if selected_countries:
                    df_filtered = df_filtered[df_filtered["country"].isin(selected_countries)]
                if selected_sources:
                    df_filtered = df_filtered[df_filtered["sessionDefaultChannelGroup"].isin(selected_sources)]
                if selected_pages:
                    df_filtered = df_filtered[df_filtered["pagePath"].isin(selected_pages)]

                # --- A. SNAPSHOTS (Filtered based on Sidebar only, ignoring calendar) ---
                st.markdown('<div class="today-header">Performance Metrics</div>', unsafe_allow_html=True)
                
                t_u = df_filtered["activeUsers"].sum()
                t_s = df_filtered["sessions"].sum()
                t_pv = df_filtered["screenPageViews"].sum()
                # Return rate calculation
                ret_rate = ((t_u - df_filtered["newUsers"].sum()) / t_u * 100) if t_u > 0 else 0

                p1, p2, p3, p4 = st.columns(4)
                p1.metric("Users", f"{int(t_u):,}")
                p2.metric("Sessions", f"{int(t_s):,}")
                p3.metric("Page Views", f"{int(t_pv):,}")
                p4.metric("Returning Rate", f"{ret_rate:.1f}%")

                st.divider()

                # --- B. GRAPHS ---
                
                # 1. TIMELINE
                st.write("### 📈 Users Timeline")
                df_filtered["date_dt"] = pd.to_datetime(df_filtered["date"])
                df_timeline = df_filtered.groupby("date_dt")["activeUsers"].sum().reset_index()
                st.plotly_chart(px.area(df_timeline.sort_values("date_dt"), x="date_dt", y="activeUsers", template="plotly_white"), use_container_width=True)

                # 2. TOP COUNTRIES
                st.write("### 🌍 Top Countries")
                df_geo = df_filtered.groupby("country")["activeUsers"].sum().reset_index()
                fig_geo = px.bar(df_geo.sort_values("activeUsers", ascending=False).head(10), 
                                 x="country", y="activeUsers", color="activeUsers", template="plotly_white")
                st.plotly_chart(fig_geo, use_container_width=True)

                # 3. SOURCES
                st.write("### 🚥 Traffic Sources")
                df_src = df_filtered.groupby("sessionDefaultChannelGroup")["sessions"].sum().reset_index()
                st.plotly_chart(px.bar(df_src.sort_values("sessions"), x="sessions", y="sessionDefaultChannelGroup", orientation='h', template="plotly_white"), use_container_width=True)

                # 4. PAGES
                st.write("### 📄 Top Pages")
                df_pg = df_filtered.groupby("pagePath")["screenPageViews"].sum().reset_index()
                fig_pg = px.bar(df_pg.sort_values("screenPageViews").tail(15), 
                                x="screenPageViews", y="pagePath", orientation='h', template="plotly_white", color="screenPageViews")
                st.plotly_chart(fig_pg, use_container_width=True)

                # 5. DETAILED TABLE
                with st.expander("🔍 View Raw Filtered Data"):
                    st.dataframe(df_filtered.drop(columns=["date_dt"]), use_container_width=True)

    except Exception as e:
        st.error(f"GA4 Error: {e}")
