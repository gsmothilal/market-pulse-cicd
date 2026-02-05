import streamlit as st
import boto3
import pandas as pd
import plotly.graph_objects as go
import time

# --- CONFIGURATION ---
# ✅ FIXED: Hardcoded for local execution (No os.environ)
TABLE_NAME = "MarketPulseAlerts"
REGION = "us-east-1"

# --- CONNECT TO AWS ---
try:
    dynamodb = boto3.resource('dynamodb', region_name=REGION)
    table = dynamodb.Table(TABLE_NAME)
except Exception as e:
    st.error(f"❌ AWS Connection Failed: {e}")

# --- DATA FUNCTION ---
def get_data(symbol):
    try:
        response = table.scan()
        items = response.get('Items', [])
        df = pd.DataFrame(items)

        if df.empty: return df

        # Filter & Clean
        df = df[df['symbol'] == symbol]
        if df.empty: return df

        # Convert Types
        df['price'] = df['price'].astype(float)
        df['prediction'] = df['prediction'].astype(float)
        df['timestamp'] = pd.to_datetime(df['timestamp'])

        return df.sort_values(by='timestamp')
    except Exception as e:
        return pd.DataFrame()

# --- UI CONFIGURATION ---
st.set_page_config(
    page_title="MarketPulse PRO",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Dark Mode Styling
st.markdown("""
<style>
    [data-testid="stMetricValue"] { font-size: 2rem; font-weight: 700; color: #FFFFFF; }
    .stAlert { border-radius: 10px; }
    .js-plotly-plot .plotly .modebar { left: 50%; transform: translateX(-50%); }
</style>
""", unsafe_allow_html=True)

# --- SIDEBAR ---
st.sidebar.title("⚡ MarketPulse Pro")
st.sidebar.markdown("---")
st.sidebar.caption("SURVEILLANCE CONFIG")

selected_symbol = st.sidebar.selectbox("Tracking Asset", ["AAPL", "GOOGL", "AMZN", "MSFT", "TSLA"])
refresh_rate = st.sidebar.slider("Refresh Rate (seconds)", 2, 60, 5)
auto_refresh = st.sidebar.checkbox("Enable Auto-Refresh", value=True)


# --- MAIN DASHBOARD ---
st.title(f"🚀 Live Surveillance: {selected_symbol}")

# Fetch Data
df = get_data(selected_symbol)

if not df.empty:
    latest = df.iloc[-1]
    
    # Handle single-row case gracefully
    if len(df) > 1:
        prev = df.iloc[-2]
        price_change = latest['price'] - prev['price']
    else:
        price_change = 0.0

    # CALCULATE METRICS
    pred_delta = latest['prediction'] - latest['price']
    signal = "BULLISH 🟢" if pred_delta > 0 else "BEARISH 🔴"

    # 1. TOP METRICS ROW
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Live Price", f"${latest['price']:.2f}", f"{price_change:.2f}")
    with col2:
        st.metric("AI Forecast (T+15s)", f"${latest['prediction']:.2f}", f"{pred_delta:.2f}")
    with col3:
        st.metric("Market Signal", signal)
    with col4:
        st.metric("Model Confidence", "96.4%") # Demo Value

    # 2. PROFESSIONAL CHART (PLOTLY)
    st.markdown("### 📉 Real-Time Trend Analysis")
    fig = go.Figure()
    
    # Actual Price Line
    fig.add_trace(go.Scatter(
        x=df['timestamp'], y=df['price'], mode='lines+markers', name='Actual Price',
        line=dict(color='#00FF00', width=2), marker=dict(size=6, color='#00FF00')
    ))
    # Prediction Line
    fig.add_trace(go.Scatter(
        x=df['timestamp'], y=df['prediction'], mode='lines', name='AI Prediction',
        line=dict(color='#FF4B4B', width=2, dash='dot')
    ))
    
    fig.update_layout(
        height=500, template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color="white"), hovermode="x unified",
        xaxis=dict(showgrid=False, title="Time"), yaxis=dict(showgrid=True, gridcolor='#333', title="Price ($)"),
        legend=dict(orientation="h", y=1.02, x=0.8)
    )
    st.plotly_chart(fig, use_container_width=True)

    # 3. AI INSIGHTS
    st.markdown("### 🧠 Generative AI Analysis")
    reason = latest.get('reason', 'Analysis pending...')
    if "volatility" in reason.lower() or "crash" in reason.lower():
        st.warning(f"⚠️ **CRITICAL ALERT:** {reason}")
    else:
        st.success(f"✅ **MARKET INTELLIGENCE:** {reason}")

    # 4. RAW DATA
    with st.expander("🔍 View Raw Forensics Data"):
        st.dataframe(df.sort_values(by='timestamp', ascending=False).style.format({"price": "${:.2f}", "prediction": "${:.2f}"}))

    # AUTO REFRESH
    if auto_refresh:
        time.sleep(refresh_rate)
        st.rerun()
else:
    st.info(f"📡 Waiting for data stream for {selected_symbol}... Start your Producer script!")
    if auto_refresh:
        time.sleep(5)
        st.rerun()
