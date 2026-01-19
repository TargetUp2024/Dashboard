import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import plotly.express as px
from datetime import datetime

# --- PAGE CONFIG ---
st.set_page_config(page_title="AO Tracking System", page_icon="📈", layout="wide")

# --- CUSTOM CSS FOR DESIGN ---
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .big-metric-container { padding-top: 0px; margin-bottom: -20px; }
    .big-metric-value { font-size: 85px !important; font-weight: 800 !important; color: #1f77b4; line-height: 1; margin: 0; }
    .big-metric-label { font-size: 20px !important; color: #666; text-transform: uppercase; margin-bottom: 5px; }
    .today-header { font-size: 22px; font-weight: 700; color: #2c3e50; margin-top: 20px; margin-bottom: 2px; }
    .today-date { font-size: 16px; color: #7f8c8d; margin-bottom: 15px; }
    .block-container { padding-top: 2rem !important; }
    [data-testid="stMetricValue"] { font-weight: 700; }
    </style>
    """, unsafe_allow_html=True)

# --- GOOGLE SHEETS CONNECTION ---
@st.cache_data(ttl=600)
def get_data():
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

# Load Data
try:
    df = get_data()
except Exception as e:
    st.error(f"❌ Connection Error: {e}")
    st.stop()

# --- SIDEBAR NAVIGATION (THE SUB-MENU) ---
st.sidebar.image("https://cdn-icons-png.flaticon.com/512/3090/3090116.png", width=80)
st.sidebar.title("Main Menu")
# This is your "button" / menu selection
page = st.sidebar.selectbox("Go to:", ["🏠 Home", "📊 View Dashboard"])

# --- PAGE 1: HOME ---
if page == "🏠 Home":
    st.title("Welcome to AO Tracking")
    st.markdown("""
    ### Welcome! 
    Use the sidebar menu on the left to navigate.
    
    **Instructions:**
    1. Select **"View Dashboard"** to see the analytics.
    2. Use the filters that will appear in the sidebar to drill down into data.
    """)
    st.info("The data is synced live with your Google Drive sheet.")

# --- PAGE 2: DASHBOARD ---
else:
    # --- FILTERS (Only show when Dashboard is selected) ---
    st.sidebar.divider()
    st.sidebar.header("🗓️ Filters")
    min_d, max_d = df['Date'].min(), df['Date'].max()
    date_range = st.sidebar.date_input("Date Range", value=(min_d, max_d), min_value=min_d, max_value=max_d)
    sources = st.sidebar.multiselect("Sources", options=df["Source"].unique(), default=df["Source"].unique())
    status_list = st.sidebar.multiselect("Status", options=df["Status"].unique(), default=df["Status"].unique())

    # Filter Logic
    if len(date_range) == 2:
        start_date, end_date = date_range
        df_filtered = df[(df["Date"] >= start_date) & (df["Date"] <= end_date) & 
                         (df["Source"].isin(sources)) & (df["Status"].isin(status_list))]
    else:
        df_filtered = df

    # --- DASHBOARD UI ---
    st.title("Appel d'Offres (AO) Tracking")

    # SECTION 1: HUGE TOTAL
    st.markdown('<div class="big-metric-container">', unsafe_allow_html=True)
    st.markdown('<p class="big-metric-label">Total AO Filtered</p>', unsafe_allow_html=True)
    st.markdown(f'<p class="big-metric-value">{int(df_filtered["Nombre"].sum())}</p>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    st.write("---")

    # SECTION 2: TODAY'S METRICS
    today_dt = datetime.now().date()
    df_today = df[df['Date'] == today_dt]

    st.markdown(f'<div class="today-header">Aujourd\'hui</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="today-date">{today_dt.strftime("%A %d %B %Y")}</div>', unsafe_allow_html=True)

    t1, t2, t3, t4 = st.columns(4)
    with t1:
        st.metric("Scrapé Aujourd'hui", int(df_today["Nombre"].sum()))
    with t2:
        st.metric("Accepté Aujourd'hui", len(df_today[df_today["Status"] == "Accepté"]))
    with t3:
        st.metric("Refus Aujourd'hui", len(df_today[df_today["Status"] == "Refus"]))
    with t4:
        st.metric("Opp Aujourd'hui", len(df_today[df_today["Status"] == "Opportunité"]))

    st.write("##")

    # SECTION 3: CONVERSION KPIs
    st.subheader("Conversion KPIs")
    c1, c2, c3 = st.columns(3)
    tot = len(df_filtered)
    if tot > 0:
        rate_refus = (len(df_filtered[df_filtered["Status"] == "Refus"]) / tot) * 100
        rate_accep = (len(df_filtered[df_filtered["Status"] == "Accepté"]) / tot) * 100
        # Avoid division by zero for Opp rate
        count_accep = len(df_filtered[df_filtered["Status"] == "Accepté"])
        rate_opp = (len(df_filtered[df_filtered["Status"] == "Opportunité"]) / count_accep * 100) if count_accep > 0 else 0
    else:
        rate_refus = rate_accep = rate_opp = 0

    with c1:
        st.metric("Taux Scraped ➔ Refus", f"{rate_refus:.1f}%")
    with c2:
        st.metric("Taux Scraped ➔ Accepté", f"{rate_accep:.1f}%")
    with c3:
        st.metric("Taux Accepté ➔ Opportunité", f"{rate_opp:.1f}%")

    st.divider()

    # SECTION 4: CHARTS
    chart_col_left, spacer, chart_col_right = st.columns([4.5, 1, 4.5])

    with chart_col_left:
        st.subheader("Distribution en Source")
        fig_bar = px.bar(
            df_filtered.groupby("Source")["Nombre"].count().reset_index(),
            x="Nombre", y="Source", orientation='h',
            color="Source", template="plotly_white",
            color_discrete_sequence=px.colors.qualitative.G10
        )
        fig_bar.update_layout(showlegend=False, margin=dict(l=0, r=0, t=10, b=0), height=350)
        st.plotly_chart(fig_bar, use_container_width=True)

    with chart_col_right:
        st.subheader("Status Analyse")
        fig_pie = px.pie(
            df_filtered, names="Status", 
            hole=0.5,
            color_discrete_map={"Refus": "#FF4B4B", "Opportunité": "#00CC96", "Accepté": "#636EFA"}
        )
        fig_pie.update_layout(margin=dict(l=0, r=0, t=10, b=0), height=350)
        st.plotly_chart(fig_pie, use_container_width=True)

    # SECTION 5: TIMELINE
    st.write("##")
    st.subheader("Activité Timeline")
    df_timeline = df_filtered.groupby('Date').size().reset_index(name='counts')
    fig_line = px.area(df_timeline, x='Date', y='counts', template="plotly_white")
    fig_line.update_traces(line_color='#1f77b4', fillcolor='rgba(31, 119, 180, 0.2)')
    st.plotly_chart(fig_line, use_container_width=True)

    # SECTION 6: TABLE
    with st.expander("🔍 View Raw Database"):
        st.dataframe(df_filtered, use_container_width=True, hide_index=True)
