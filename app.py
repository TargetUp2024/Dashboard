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

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Executive Intelligence System", 
    page_icon="📈", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 2. CUSTOM CSS STYLING ---
st.markdown("""
    <style>
    /* General Background */
    .main { background-color: #f8f9fa; }
    
    /* Big Metric Styling */
    .big-metric-container { 
        background-color: white; 
        padding: 20px; 
        border-radius: 10px; 
        box-shadow: 0 2px 4px rgba(0,0,0,0.1); 
        text-align: center;
        margin-bottom: 10px;
    }
    .big-metric-value { 
        font-size: 60px !important; 
        font-weight: 800 !important; 
        color: #1f77b4; 
        line-height: 1; 
        margin: 0; 
    }
    .big-metric-label { 
        font-size: 18px !important; 
        color: #666; 
        text-transform: uppercase; 
        font-weight: 600;
        margin-bottom: 5px; 
    }
    
    /* Headers */
    .today-header { 
        font-size: 22px; 
        font-weight: 700; 
        color: #2c3e50; 
        margin-top: 25px; 
        margin-bottom: 15px;
        border-left: 6px solid #1f77b4; 
        padding-left: 15px; 
        background-color: #eef2f5;
        padding-top: 5px;
        padding-bottom: 5px;
        border-radius: 0 5px 5px 0;
    }
    
    /* Adjust Streamlit Default Metrics */
    [data-testid="stMetricValue"] { font-weight: 700; font-size: 28px !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. AUTHENTICATION & CLIENTS ---

def get_gcp_creds():
    """Retrieve Service Account Creds from Secrets"""
    return Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
            "https://www.googleapis.com/auth/analytics.readonly"
        ]
    )

@st.cache_resource
def get_ga_client():
    """Init Google Analytics Client"""
    creds = get_gcp_creds()
    return BetaAnalyticsDataClient(credentials=creds)

@st.cache_resource
def get_gsheet_client():
    """Init Google Sheets Client"""
    creds = get_gcp_creds()
    return gspread.authorize(creds)

# --- 4. DATA FETCHING FUNCTIONS (CACHED) ---

@st.cache_data(ttl=600)
def get_ao_data():
    """Fetch AO Data from Google Sheets"""
    try:
        client = get_gsheet_client()
        sheet = client.open_by_url(st.secrets["private_gsheet_url"]).sheet1
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        
        # Data Cleaning
        if not df.empty:
            df = df.dropna(subset=['Date'])
            df['Date'] = pd.to_datetime(df['Date'], errors='coerce').dt.date
            # Ensure 'Nombre' is numeric, default to 1 if missing
            if 'Nombre' in df.columns:
                df['Nombre'] = pd.to_numeric(df['Nombre'], errors='coerce').fillna(1)
            else:
                df['Nombre'] = 1
        return df
    except Exception as e:
        st.error(f"Error fetching AO Data: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=600)
def get_mail_data():
    """Fetch Mail Data from Google Sheets"""
    try:
        client = get_gsheet_client()
        # Adjust worksheet name if needed
        sheet = client.open_by_url(st.secrets["mail_gsheet_url"]).worksheet("CLUB DIRIGEANTS")
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        
        if not df.empty:
            df['Date'] = pd.to_datetime(df['Date'], errors='coerce').dt.date
        return df
    except Exception as e:
        st.error(f"Error fetching Mail Data: {e}")
        return pd.DataFrame()

def get_mailgun_stats(duration="30d"):
    """Fetch Real-time Stats from Mailgun API"""
    try:
        domain = st.secrets["MAILGUN_DOMAIN"]
        api_key = st.secrets["MAILGUN_API_KEY"]
        url = f"https://api.mailgun.net/v3/{domain}/stats/total"
        params = {"event": ["accepted", "opened"], "duration": duration}
        
        res = requests.get(url, auth=("api", api_key), params=params)
        
        if res.status_code == 200:
            data = res.json()
            stats = data.get('stats', [{}])[0]
            acc = stats.get('accepted', {}).get('total', 0)
            ope = stats.get('opened', {}).get('total', 0)
            rate = (ope / acc * 100) if acc > 0 else 0
            return rate, ope, acc
    except Exception as e:
        pass # Fail silently or log
    return 0, 0, 0

def run_ga_report(property_id, dimensions, metrics, start_date, end_date="today"):
    """Fetch Analytics from GA4 API"""
    try:
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
            res = {}
            for i, val in enumerate(row.dimension_values):
                res[dimensions[i]] = val.value
            for i, val in enumerate(row.metric_values):
                res[metrics[i]] = val.value
            output.append(res)
        return pd.DataFrame(output)
    except Exception as e:
        st.error(f"GA4 API Error: {e}")
        return pd.DataFrame()

# --- 5. SIDEBAR NAVIGATION ---
st.sidebar.image("https://cdn-icons-png.flaticon.com/512/3090/3090116.png", width=60)
st.sidebar.title("Executive Menu")
page = st.sidebar.radio("Navigate to:", ["🏠 Home", "📊 AO Dashboard", "📧 Mail Tracking", "🌐 Google Analytics"])

st.sidebar.markdown("---")
st.sidebar.caption(f"Last Updated: {datetime.now().strftime('%H:%M:%S')}")

# --- 6. PAGE LOGIC ---

# === PAGE: HOME ===
if page == "🏠 Home":
    st.title("AO & Marketing Intelligence System")
    st.markdown("### Executive Summary")
    
    # Quick Status Check
    col1, col2, col3 = st.columns(3)
    with col1:
        st.info("**AO Tracking**\n\nConnected to Google Sheets live feed.")
    with col2:
        st.success("**Email Marketing**\n\nConnected to GSheets & Mailgun API.")
    with col3:
        st.warning("**Web Analytics**\n\nConnected to GA4 (University & Consulting).")

    st.markdown("---")
    st.image("https://images.unsplash.com/photo-1551288049-bebda4e38f71?auto=format&fit=crop&w=1600&q=80", caption="Data Intelligence Hub")

# === PAGE: AO DASHBOARD ===
elif page == "📊 AO Dashboard":
    df = get_ao_data()
    
    # Filters
    st.sidebar.header("🗓️ AO Date Filters")
    if not df.empty:
        min_d, max_d = df['Date'].min(), df['Date'].max()
        dr_ao = st.sidebar.date_input("Select Date Range", value=(min_d, max_d))
        
        # Apply Filter
        if isinstance(dr_ao, tuple) and len(dr_ao) == 2:
            df_f = df[(df["Date"] >= dr_ao[0]) & (df["Date"] <= dr_ao[1])]
        else:
            df_f = df
    else:
        st.error("No data found in AO Sheet.")
        st.stop()

    st.title("Appel d'Offres (AO) Tracking")
    
    # Big Metric
    total_ao = int(df_f["Nombre"].sum())
    st.markdown(f"""
        <div class="big-metric-container">
            <p class="big-metric-label">TOTAL AO TRAITÉ (Filtered)</p>
            <p class="big-metric-value">{total_ao}</p>
        </div>
    """, unsafe_allow_html=True)
    
    # Today's Performance
    today_dt = datetime.now().date()
    df_today = df[df['Date'] == today_dt]
    
    st.markdown(f'<div class="today-header">Performance Aujourd\'hui ({today_dt})</div>', unsafe_allow_html=True)
    
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total Scrapé", int(df_today["Nombre"].sum()))
    k2.metric("✅ Accepté", len(df_today[df_today["Status"].astype(str).str.contains("Accept", case=False, na=False)]))
    k3.metric("❌ Refus", len(df_today[df_today["Status"].astype(str).str.contains("Refus", case=False, na=False)]))
    k4.metric("⭐ Opportunité", len(df_today[df_today["Status"].astype(str).str.contains("Opp", case=False, na=False)]))

    st.divider()

    # Charts
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Distribution par Source")
        if not df_f.empty:
            source_counts = df_f.groupby("Source")["Nombre"].count().reset_index().sort_values("Nombre", ascending=True)
            fig_source = px.bar(source_counts, x="Nombre", y="Source", orientation='h', text_auto=True, color="Nombre")
            st.plotly_chart(fig_source, use_container_width=True)
    
    with c2:
        st.subheader("Analyse des Statuts")
        if not df_f.empty:
            fig_status = px.pie(df_f, names="Status", hole=0.5, color_discrete_sequence=px.colors.sequential.RdBu)
            st.plotly_chart(fig_status, use_container_width=True)

    # Detailed View
    with st.expander("Voir les données brutes (Détails)"):
        st.dataframe(df_f.sort_values("Date", ascending=False), use_container_width=True)


# === PAGE: MAIL TRACKING ===
elif page == "📧 Mail Tracking":
    st.title("📧 Mail Marketing Dashboard")
    df_m = get_mail_data()
    
    if df_m.empty:
        st.error("Mail data empty or connection failed.")
        st.stop()

    # Filter
    st.sidebar.header("🗓️ Mail Filters")
    min_m, max_m = df_m['Date'].min(), df_m['Date'].max()
    m_range = st.sidebar.date_input("Select Range", value=(min_m, max_m))
    
    # Mailgun API Stats (Last 30 days general, or specific)
    mg_rate, mg_open, mg_acc = get_mailgun_stats("30d")

    # Today's Snapshot
    today_dt = datetime.now().date()
    df_m_today = df_m[df_m['Date'] == today_dt]
    
    # Calculate daily metrics manually from sheet
    sent_today = len(df_m_today[df_m_today['Email Envoyé '].astype(str).str.contains('Oui', case=False, na=False)])
    resp_today = len(df_m_today[df_m_today['Email Reponse '].astype(str).str.strip() != ""])

    st.markdown(f'<div class="today-header">Activité Aujourd\'hui ({today_dt})</div>', unsafe_allow_html=True)
    mt1, mt2, mt3, mt4 = st.columns(4)
    
    mt1.metric("Prospects Identifiés", len(df_m_today))
    mt2.metric("Emails Envoyés", sent_today)
    mt3.metric("Réponses Reçues", resp_today)
    mt4.metric("Global Open Rate (API)", f"{mg_rate:.1f}%", help="From Mailgun (Last 30 days)")

    st.divider()
    
    # Historical Analysis
    if isinstance(m_range, tuple) and len(m_range) == 2:
        df_m_f = df_m[(df_m['Date'] >= m_range[0]) & (df_m['Date'] <= m_range[1])]
        
        st.subheader("📅 Évolution des Envois")
        daily_counts = df_m_f.groupby('Date').size().reset_index(name='Volume')
        fig_line = px.line(daily_counts, x='Date', y='Volume', markers=True, template="plotly_white", line_shape="spline")
        fig_line.update_traces(line_color='#1f77b4', line_width=3)
        st.plotly_chart(fig_line, use_container_width=True)


# === PAGE: GOOGLE ANALYTICS ===
elif page == "🌐 Google Analytics":
    st.title("🌐 Web Traffic Intelligence")
    
    # Select Profile
    site = st.sidebar.selectbox("Select Website Asset:", ["Targetup University", "Targetup Consulting"])
    pid = st.secrets["GA_PROPERTY_ID_1"] if site == "Targetup University" else st.secrets["GA_PROPERTY_ID_2"]
    
    # Date Range
    st.sidebar.divider()
    st.sidebar.header("🗓️ Analysis Period")
    today = datetime.now().date()
    ga_range = st.sidebar.date_input("Select Date Range", value=(today - timedelta(days=28), today))

    try:
        # 1. LIVE COMPARISON (Fixed: Today vs Yesterday)
        st.markdown(f'<div class="today-header">Comparaison Directe (Live)</div>', unsafe_allow_html=True)
        col_t1, col_t2, col_y1, col_y2 = st.columns(4)
        
        # Helper to sum column safely
        def safe_sum(df, col): return pd.to_numeric(df[col]).sum() if not df.empty else 0

        # Run minimal reports
        df_ga_today = run_ga_report(pid, ["date"], ["activeUsers", "sessions"], "today", "today")
        df_ga_yest  = run_ga_report(pid, ["date"], ["activeUsers", "sessions"], "yesterday", "yesterday")

        u_today = safe_sum(df_ga_today, 'activeUsers')
        s_today = safe_sum(df_ga_today, 'sessions')
        u_yest = safe_sum(df_ga_yest, 'activeUsers')
        s_yest = safe_sum(df_ga_yest, 'sessions')

        u_delta = u_today - u_yest
        s_delta = s_today - s_yest

        col_t1.metric("Users (Today)", f"{u_today:,}", delta=int(u_delta))
        col_t2.metric("Sessions (Today)", f"{s_today:,}", delta=int(s_delta))
        col_y1.metric("Users (Yesterday)", f"{u_yest:,}")
        col_y2.metric("Sessions (Yesterday)", f"{s_yest:,}")

        st.divider()

        # 2. PERIOD ANALYSIS
        if isinstance(ga_range, tuple) and len(ga_range) == 2:
            s_str, e_str = ga_range[0].strftime("%Y-%m-%d"), ga_range[1].strftime("%Y-%m-%d")
            
            # Fetch Main Data
            with st.spinner("Fetching Google Analytics Data..."):
                df_main = run_ga_report(pid, ["date"], ["activeUsers", "newUsers", "sessions", "engagementRate"], s_str, e_str)
            
            if df_main.empty:
                st.warning("No data received from GA4 for this period.")
            else:
                # Conversions
                df_main["activeUsers"] = pd.to_numeric(df_main["activeUsers"])
                df_main["sessions"] = pd.to_numeric(df_main["sessions"])
                df_main["newUsers"] = pd.to_numeric(df_main["newUsers"])
                df_main["engagementRate"] = pd.to_numeric(df_main["engagementRate"])
                df_main["date"] = pd.to_datetime(df_main["date"])

                # Period KPIs
                tot_users = df_main["activeUsers"].sum()
                tot_sessions = df_main["sessions"].sum()
                avg_eng = df_main["engagementRate"].mean() * 100
                tot_new = df_main["newUsers"].sum()
                ret_rate = ((tot_users - tot_new) / tot_users * 100) if tot_users > 0 else 0

                st.markdown(f'<div class="today-header">Performance: {s_str} to {e_str}</div>', unsafe_allow_html=True)
                p1, p2, p3, p4 = st.columns(4)
                p1.metric("Total Users", f"{tot_users:,}")
                p2.metric("Total Sessions", f"{tot_sessions:,}")
                p3.metric("Engagement Rate", f"{avg_eng:.2f}%")
                p4.metric("Returning Users Rate", f"{ret_rate:.1f}%")

                # GRAPHS SECTION
                st.write("---")
                
                # 1. Timeline
                st.subheader("📈 Traffic Timeline (Users)")
                fig_area = px.area(df_main.sort_values("date"), x="date", y="activeUsers", template="plotly_white")
                fig_area.update_traces(line_color='#1f77b4', fillcolor='rgba(31, 119, 180, 0.3)')
                st.plotly_chart(fig_area, use_container_width=True)

                c_g1, c_g2 = st.columns(2)

                # 2. Geography
                with c_g1:
                    st.subheader("🌍 Top Countries")
                    df_geo = run_ga_report(pid, ["country"], ["activeUsers"], s_str, e_str)
                    if not df_geo.empty:
                        df_geo["activeUsers"] = pd.to_numeric(df_geo["activeUsers"])
                        fig_geo = px.bar(df_geo.sort_values("activeUsers", ascending=False).head(8), 
                                        x="country", y="activeUsers", text_auto=True, 
                                        color="activeUsers", color_continuous_scale="Blues")
                        st.plotly_chart(fig_geo, use_container_width=True)

                # 3. Sources
                with c_g2:
                    st.subheader("📢 Traffic Sources")
                    df_src = run_ga_report(pid, ["sessionDefaultChannelGroup"], ["sessions"], s_str, e_str)
                    if not df_src.empty:
                        df_src["sessions"] = pd.to_numeric(df_src["sessions"])
                        fig_src = px.bar(df_src.sort_values("sessions", ascending=True), 
                                        x="sessions", y="sessionDefaultChannelGroup", orientation='h', 
                                        text_auto=True, color="sessions", color_continuous_scale="Teal")
                        st.plotly_chart(fig_src, use_container_width=True)

                # 4. Content (Pages)
                st.subheader("📄 Top Visited Pages")
                df_pg = run_ga_report(pid, ["pagePath"], ["screenPageViews"], s_str, e_str)
                if not df_pg.empty:
                    df_pg["screenPageViews"] = pd.to_numeric(df_pg["screenPageViews"])
                    fig_pg = px.bar(df_pg.sort_values("screenPageViews", ascending=True).tail(10), 
                                    x="screenPageViews", y="pagePath", orientation='h', 
                                    text_auto=True, color_discrete_sequence=['#2c3e50'])
                    st.plotly_chart(fig_pg, use_container_width=True)

    except Exception as e:
        st.error(f"Critical Analytics Error: {e}")
