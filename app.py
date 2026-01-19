import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import DateRange, Dimension, Metric, RunReportRequest
import plotly.express as px
from datetime import datetime, timedelta
import requests

# =====================================================
# PAGE CONFIG
# =====================================================
st.set_page_config(
    page_title="Executive Intelligence System",
    page_icon="📈",
    layout="wide"
)

# =====================================================
# CUSTOM CSS
# =====================================================
st.markdown("""
<style>
.main { background-color: #f8f9fa; }
.big-metric-container { padding-top: 0px; margin-bottom: -20px; }
.big-metric-value { font-size: 85px !important; font-weight: 800 !important; color: #1f77b4; line-height: 1; margin: 0; }
.big-metric-label { font-size: 20px !important; color: #666; text-transform: uppercase; margin-bottom: 5px; }
.today-header { font-size: 24px; font-weight: 700; color: #2c3e50; margin-top: 20px; border-left: 5px solid #1f77b4; padding-left: 10px; }
[data-testid="stMetricValue"] { font-weight: 700; font-size: 32px !important; }
</style>
""", unsafe_allow_html=True)

# =====================================================
# CLIENT INITIALIZATION
# =====================================================
def get_ga_client():
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"])
    return BetaAnalyticsDataClient(credentials=creds)

# =====================================================
# DATA FETCHING
# =====================================================
@st.cache_data(ttl=600)
def get_ao_data():
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
    )
    client = gspread.authorize(creds)
    sheet = client.open_by_url(st.secrets["private_gsheet_url"]).sheet1
    df = pd.DataFrame(sheet.get_all_records())

    df = df.dropna(subset=["Date", "Source"])
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.date
    df["Nombre"] = pd.to_numeric(df.get("Nombre", 1), errors="coerce").fillna(1)

    return df

@st.cache_data(ttl=600)
def get_mail_data():
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
    )
    client = gspread.authorize(creds)
    sheet = client.open_by_url(st.secrets["mail_gsheet_url"]).worksheet("CLUB DIRIGEANTS")
    df = pd.DataFrame(sheet.get_all_records())

    if not df.empty:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.date

    return df

def get_mailgun_stats(duration="30d"):
    try:
        url = f"https://api.mailgun.net/v3/{st.secrets['MAILGUN_DOMAIN']}/stats/total"
        params = {"event": ["accepted", "opened"], "duration": duration}
        r = requests.get(
            url,
            auth=("api", st.secrets["MAILGUN_API_KEY"]),
            params=params,
            timeout=10
        )
        if r.status_code == 200:
            stats = r.json().get("stats", [{}])[0]
            acc = stats.get("accepted", {}).get("total", 0)
            ope = stats.get("opened", {}).get("total", 0)
            rate = (ope / acc * 100) if acc else 0
            return rate, ope
    except Exception:
        pass
    return 0.0, 0

# =====================================================
# GA4 REPORT
# =====================================================
def run_ga_report(property_id, dimensions, metrics, start_date, end_date):
    client = get_ga_client()

    request = RunReportRequest(
        property=f"properties/{property_id}",
        dimensions=[Dimension(name=d) for d in dimensions],
        metrics=[Metric(name=m) for m in metrics],
        date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
    )

    response = client.run_report(request)
    rows = []

    for r in response.rows:
        row = {}
        for i, d in enumerate(dimensions):
            row[d] = r.dimension_values[i].value
        for i, m in enumerate(metrics):
            row[m] = r.metric_values[i].value
        rows.append(row)

    return pd.DataFrame(rows)

# =====================================================
# SIDEBAR NAVIGATION
# =====================================================
st.sidebar.image("https://cdn-icons-png.flaticon.com/512/3090/3090116.png", width=80)
st.sidebar.title("Main Menu")

page = st.sidebar.selectbox(
    "Go to:",
    ["🏠 Home", "📊 AO Dashboard", "📧 Mail Tracking", "🌐 Google Analytics"]
)

# =====================================================
# HOME
# =====================================================
if page == "🏠 Home":
    st.title("AO & Marketing Intelligence System")
    st.info("Connected to Google Sheets, Mailgun, and Google Analytics 4.")

# =====================================================
# AO DASHBOARD
# =====================================================
elif page == "📊 AO Dashboard":
    df = get_ao_data()

    st.sidebar.header("🗓️ AO Filters")
    dr = st.sidebar.date_input(
        "Date Range",
        value=(df["Date"].min(), df["Date"].max())
    )

    if isinstance(dr, tuple):
        df_f = df[(df["Date"] >= dr[0]) & (df["Date"] <= dr[1])]
    else:
        df_f = df

    st.title("Appel d'Offres Tracking")

    st.markdown(
        f"""
        <div class="big-metric-container">
            <p class="big-metric-label">Total AO Filtered</p>
            <p class="big-metric-value">{int(df_f["Nombre"].sum())}</p>
        </div>
        """,
        unsafe_allow_html=True
    )

    today = datetime.now().date()
    df_today = df[df["Date"] == today]

    st.markdown('<div class="today-header">Aujourd’hui</div>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)

    c1.metric("Scrapé", int(df_today["Nombre"].sum()))
    c2.metric("Accepté", len(df_today[df_today["Status"] == "Accepté"]))
    c3.metric("Refus", len(df_today[df_today["Status"] == "Refus"]))
    c4.metric("Opportunité", len(df_today[df_today["Status"] == "Opportunité"]))

    st.divider()

    col1, col2 = st.columns(2)

    with col1:
        src = df_f.groupby("Source")["Nombre"].count().reset_index()
        st.plotly_chart(
            px.bar(src, x="Nombre", y="Source", orientation="h"),
            use_container_width=True
        )

    with col2:
        st.plotly_chart(
            px.pie(df_f, names="Status", hole=0.5),
            use_container_width=True
        )

# =====================================================
# MAIL TRACKING
# =====================================================
elif page == "📧 Mail Tracking":
    df_m = get_mail_data()

    st.sidebar.header("🗓️ Mail Filters")
    dr = st.sidebar.date_input(
        "Date Range",
        value=(df_m["Date"].min(), df_m["Date"].max())
    )

    today = datetime.now().date()
    df_today = df_m[df_m["Date"] == today]
    rate_24h, _ = get_mailgun_stats("24h")

    st.markdown('<div class="today-header">Mailing Aujourd’hui</div>', unsafe_allow_html=True)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Prospectés", len(df_today))
    m2.metric("Envoyés", len(df_today[df_today["Email Envoyé "].str.contains("Oui", na=False)]))
    m3.metric("Open Rate (24h)", f"{rate_24h:.1f}%")
    m4.metric("Réponses", len(df_today[df_today["Email Reponse "].astype(str).str.strip() != ""]))

    if isinstance(dr, tuple):
        df_f = df_m[(df_m["Date"] >= dr[0]) & (df_m["Date"] <= dr[1])]
        timeline = df_f.groupby("Date").size().reset_index(name="Volume")
        st.plotly_chart(px.line(timeline, x="Date", y="Volume"), use_container_width=True)

# =====================================================
# GOOGLE ANALYTICS
# =====================================================
elif page == "🌐 Google Analytics":
    st.title("Website Traffic Intelligence")

    site = st.sidebar.radio("Website", ["Targetup University", "Targetup Consulting"])
    pid = st.secrets["GA_PROPERTY_ID_1"] if site == "Targetup University" else st.secrets["GA_PROPERTY_ID_2"]

    today = datetime.now().date()
    dr = st.sidebar.date_input(
        "Date Range",
        value=(today - timedelta(days=30), today)
    )

    s_today = today.strftime("%Y-%m-%d")
    s_yest = (today - timedelta(days=1)).strftime("%Y-%m-%d")

    df_t = run_ga_report(pid, ["date"], ["activeUsers", "sessions"], s_today, s_today)
    df_y = run_ga_report(pid, ["date"], ["activeUsers", "sessions"], s_yest, s_yest)

    def ssum(df, col):
        return pd.to_numeric(df[col]).sum() if not df.empty else 0

    st.markdown('<div class="today-header">Live Snapshots</div>', unsafe_allow_html=True)
    a, b, c, d = st.columns(4)

    a.metric("Users Today", ssum(df_t, "activeUsers"))
    b.metric("Sessions Today", ssum(df_t, "sessions"))
    c.metric("Users Yesterday", ssum(df_y, "activeUsers"))
    d.metric("Sessions Yesterday", ssum(df_y, "sessions"))

    if isinstance(dr, tuple):
        s, e = dr[0].strftime("%Y-%m-%d"), dr[1].strftime("%Y-%m-%d")

        df_p = run_ga_report(
            pid,
            ["date"],
            ["activeUsers", "newUsers", "sessions", "engagementRate"],
            s,
            e
        )

        df_p["date"] = pd.to_datetime(df_p["date"])

        total_users = ssum(df_p, "activeUsers")
        new_users = ssum(df_p, "newUsers")
        ret_rate = ((total_users - new_users) / total_users * 100) if total_users else 0

        st.markdown(f'<div class="today-header">Performance {s} → {e}</div>', unsafe_allow_html=True)
        p1, p2, p3, p4 = st.columns(4)

        p1.metric("Total Users", total_users)
        p2.metric("Total Sessions", ssum(df_p, "sessions"))
        p3.metric("Engagement Rate", f"{pd.to_numeric(df_p['engagementRate']).mean() * 100:.1f}%")
        p4.metric("Return Rate", f"{ret_rate:.1f}%")

        st.plotly_chart(px.area(df_p, x="date", y="activeUsers"), use_container_width=True)
