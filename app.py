import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import plotly.express as px
from datetime import datetime

# --- PAGE CONFIG ---
st.set_page_config(page_title="AO Tracking System", page_icon="📈", layout="wide")

# --- STYLE ---
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    div[data-testid="stMetricValue"] { font-size: 28px; color: #1f77b4; }
    /* Add padding to chart containers */
    .chart-container {
        padding: 20px;
    }
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
    
    # DATA CLEANING
    df = df.dropna(subset=['Date', 'Source'])
    df['Date'] = pd.to_datetime(df['Date']).dt.date # Keep as date objects for calendar filter
    df['Nombre'] = pd.to_numeric(df['Nombre'], errors='coerce').fillna(1)
    return df

# Initialize Data
try:
    df = get_data()
except Exception as e:
    st.error(f"❌ Connection Error: {e}")
    st.stop()

# --- SIDEBAR FILTERS ---
st.sidebar.header("🗓️ Timeframe")
# Date Range Filter (Mini Calendar)
min_date = df['Date'].min()
max_date = df['Date'].max()
date_range = st.sidebar.date_input(
    "Select Date Range",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date
)

st.sidebar.header("🔍 Category Filters")
sources = st.sidebar.multiselect("Source Name", options=df["Source"].unique(), default=df["Source"].unique())
status_options = df["Status"].unique()
status = st.sidebar.multiselect("Status", options=status_options, default=status_options)

# Apply Filters
if len(date_range) == 2:
    start_date, end_date = date_range
    df_filtered = df[
        (df["Date"] >= start_date) & 
        (df["Date"] <= end_date) & 
        (df["Source"].isin(sources)) & 
        (df["Status"].isin(status))
    ]
else:
    df_filtered = df[df["Source"].isin(sources) & df["Status"].isin(status)]

# --- MAIN UI ---
st.title("📊 Appel d'Offres (AO) Dashboard")

# --- ROW 1: CORE METRICS ---
st.subheader("General Overview")
m1, m2, m3, m4 = st.columns(4)

# Calculations
total_ao = int(df_filtered["Nombre"].sum())
today_date = datetime.now().date()
ao_today = int(df_filtered[df_filtered["Date"] == today_date]["Nombre"].sum())
total_refus = len(df_filtered[df_filtered["Status"] == "Refus"])
total_opp = len(df_filtered[df_filtered["Status"] == "Opportunité"])
total_accept = len(df_filtered[df_filtered["Status"] == "Accepté"])

with m1:
    st.metric("Total AO (Filtered)", total_ao)
with m2:
    st.metric("Scraped Today", ao_today)
with m3:
    st.metric("Total Refus", total_refus)
with m4:
    st.metric("Total Opportunité", total_opp)

# --- ROW 2: CONVERSION RATES ---
st.write("##")
st.subheader("Conversion Rates")
c_col1, c_col2, c_col3 = st.columns(3)

# Rate Calculations
rate_refus = (total_refus / total_ao * 100) if total_ao > 0 else 0
rate_accept = (total_accept / total_ao * 100) if total_ao > 0 else 0
rate_opp = (total_opp / total_accept * 100) if total_ao > 0 else 0

with c_col1:
    st.metric("Taux de Conversion (Scraped to Refus)", f"{rate_refus:.1f}%")
with c_col2:
    st.metric("Taux de Conversion (Scraped to Accepté)", f"{rate_accept:.1f}%")
with c_col3:
    st.metric("Taux de Conversion (Accepté to Opportunité)", f"{rate_opp:.1f}%")

st.divider()

# --- ROW 3: VISUALIZATIONS WITH SPACING ---
col_left, spacer, col_right = st.columns([4.5, 1, 4.5]) # Added a 'spacer' column

with col_left:
    st.subheader("📁 Distribution by Source")
    fig_bar = px.bar(
        df_filtered.groupby("Source")["Nombre"].count().reset_index(),
        x="Nombre", y="Source", orientation='h',
        color="Source", template="plotly_white",
    )
    fig_bar.update_layout(showlegend=False, margin=dict(l=0, r=0, t=20, b=0))
    st.plotly_chart(fig_bar, use_container_width=True)

with col_right:
    st.subheader("🎯 Status Breakdown")
    fig_pie = px.pie(
        df_filtered, names="Status", 
        color_discrete_map={"Refus": "#ef4444", "Opportunité": "#10b981"},
        hole=0.5
    )
    fig_pie.update_layout(margin=dict(l=0, r=0, t=20, b=0))
    st.plotly_chart(fig_pie, use_container_width=True)

# --- ROW 4: TIMELINE ---
st.write("##")
st.subheader("📅 Activity Over Time")
df_timeline = df_filtered.groupby('Date').size().reset_index(name='counts')
fig_line = px.area(df_timeline, x='Date', y='counts', template="plotly_white")
fig_line.update_traces(line_color='#007bff')
st.plotly_chart(fig_line, use_container_width=True)

# Data Explorer
with st.expander("🔍 View Detailed Data List"):
    st.dataframe(df_filtered, use_container_width=True, hide_index=True)
