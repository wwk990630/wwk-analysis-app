import streamlit as st
import yinhedata as yh
import pandas as pd
import plotly.graph_objects as go
from datetime import date

# --- Commodity code to Chinese name mapping ---
COMMODITY_MAP = {
    "SH": "烧碱",
    "SA": "纯碱",
    "FG": "玻璃",
}

# --- Data processing function ---
@st.cache_data
def create_spread_dataframe(leg1_symbol, leg2_symbol, leg3_symbol):
    timeframe = '1min'
    try:
        df_leg1 = yh.features_history(leg1_symbol, timeframe)
        df_leg2 = yh.features_history(leg2_symbol, timeframe)
        df_leg3 = yh.features_history(leg3_symbol, timeframe)
    except Exception: return None
    if df_leg1 is None or df_leg2 is None or df_leg3 is None or df_leg1.empty or df_leg2.empty or df_leg3.empty: return None
    dfs = {}
    for df, name in [(df_leg1, 'leg1'), (df_leg2, 'leg2'), (df_leg3, 'leg3')]:
        try:
            df['时间'] = pd.to_datetime(df['时间'])
            df.set_index('时间', inplace=True)
            df = df[['开盘价', '最高价', '最低价', '收盘价']].rename(columns={'开盘价': f'open_{name}', '最高价': f'high_{name}', '最低价': f'low_{name}', '收盘价': f'close_{name}'})
            dfs[name] = df
        except KeyError: return None
    df_merged = pd.concat(dfs.values(), axis=1)
    df_merged.dropna(inplace=True)
    spread_df = pd.DataFrame(index=df_merged.index)
    spread_df['Open'] = df_merged['open_leg1'] + df_merged['open_leg3'] - 2 * df_merged['open_leg2']
    spread_df['Close'] = df_merged['close_leg1'] + df_merged['close_leg3'] - 2 * df_merged['close_leg2']
    spread_df['High'] = df_merged['high_leg1'] + df_merged['high_leg3'] - 2 * df_merged['low_leg2']
    spread_df['Low'] = df_merged['low_leg1'] + df_merged['low_leg3'] - 2 * df_merged['high_leg2']
    latest_date = spread_df.index[-1].date()
    daily_df = spread_df[spread_df.index.date == latest_date].copy()
    if daily_df.empty: return None
    daily_df['avg_price'] = daily_df['Close'].expanding().mean()
    daily_df['open_price'] = daily_df['Open'].iloc[0]
    window, std_multiplier = 20, 2
    daily_df['sma_20'] = daily_df['Close'].rolling(window=window).mean()
    daily_df['std_dev'] = daily_df['Close'].rolling(window=window).std()
    daily_df['upper_band'] = daily_df['sma_20'] + (daily_df['std_dev'] * std_multiplier)
    daily_df['lower_band'] = daily_df['sma_20'] - (daily_df['std_dev'] * std_multiplier)
    daily_df['day_high'] = daily_df['High'].expanding().max()
    daily_df['day_low'] = daily_df['Low'].expanding().min()
    return daily_df

# --- Plotting function ---
def plot_unified_chart(daily_df, symbols):
    commodity_code = symbols['near'][:2]
    commodity_name = COMMODITY_MAP.get(commodity_code.upper(), commodity_code)
    title_text = f"{commodity_name} 蝶式价差 ({symbols['near']}-{symbols['mid']}-{symbols['far']}) - 1分钟"

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=daily_df.index, y=daily_df['Close'], mode='lines', name='价差分时线', line=dict(color='#4A90E2', width=1.5), fill='tozeroy', fillcolor='rgba(74, 144, 226, 0.1)', visible=True))
    fig.add_trace(go.Scatter(x=daily_df.index, y=daily_df['avg_price'], mode='lines', name='日内均价', line=dict(color='#F5A623', width=1), visible=True))
    fig.add_trace(go.Scatter(x=daily_df.index, y=daily_df['open_price'], mode='lines', name='开盘价', line=dict(color='grey', width=1, dash='dash'), visible=True))
    fig.add_trace(go.Candlestick(x=daily_df.index, open=daily_df['Open'], high=daily_df['High'], low=daily_df['Low'], close=daily_df['Close'], name='价差K线', increasing_line_color='#ff5a5a', decreasing_line_color='#49c98a', visible=False))
    fig.add_trace(go.Scatter(x=daily_df.index, y=daily_df['upper_band'], mode='lines', name='布林带上轨', line=dict(color='purple', width=1, dash='dash'), visible=False))
    fig.add_trace(go.Scatter(x=daily_df.index, y=daily_df['sma_20'], mode='lines', name='中轨线', line=dict(color='purple', width=0.8), visible=False))
    fig.add_trace(go.Scatter(x=daily_df.index, y=daily_df['lower_band'], mode='lines', name='布林带下轨', line=dict(color='purple', width=1, dash='dash'), visible=False))
    fig.add_trace(go.Scatter(x=daily_df.index, y=daily_df['day_high'], mode='lines', name='日内高点', line=dict(color='#ff9b85', width=1.5, dash='dot'), visible=False))
    fig.add_trace(go.Scatter(x=daily_df.index, y=daily_df['day_low'], mode='lines', name='日内低点', line=dict(color='#90be6d', width=1.5, dash='dot'), visible=False))
    
    # --- Create switcher buttons ---
    fig.update_layout(
        updatemenus=[
            dict(
                type="buttons",
                direction="right",
                active=0,
                x=0.5, y=1.15,
                xanchor="center", yanchor="top",
                buttons=list([
                    dict(label="简洁分时图", method="update", args=[{"visible": [True, True, True, False, False, False, False, False, False]}]),
                    dict(label="精密分析图", method="update", args=[{"visible": [False, False, False, True, True, True, True, True, True]}]),
                ])
            )
        ]
    )
    
    # --- Beautify chart layout (with corrected spelling) ---
    fig.update_layout(
        title=title_text,
        yaxis_title='价差值',
        xaxis_title=f'时间 ({daily_df.index[-1].date()})',
        template='plotly_white',
        xaxis_rangeslider_visible=False, # Corrected: 'timer' to 'slider'
        font=dict(family="Hiragino Sans GB, PingFang SC, SimHei"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    return fig

# --- Streamlit Web App Interface ---
st.set_page_config(layout="wide")
st.title("🦋 交互式蝶式套利分析工具")

with st.sidebar:
    st.header("合约选择")
    preset = st.selectbox('选择预置组合', ('烧碱 (SH)', '纯碱 (SA)', '玻璃 (FG)', '自定义'))
    if preset == '烧碱 (SH)':
        near_leg_default, mid_leg_default, far_leg_default = "SH2511", "SH2512", "SH2601"
    elif preset == '纯碱 (SA)':
        near_leg_default, mid_leg_default, far_leg_default = "SA2601", "SA2605", "SA2609"
    elif preset == '玻璃 (FG)':
        near_leg_default, mid_leg_default, far_leg_default = "FG2601", "FG2605", "FG2609"
    else:
        near_leg_default, mid_leg_default, far_leg_default = "", "", ""
    near_leg = st.text_input("近端合约 (Near Leg)", value=near_leg_default)
    mid_leg = st.text_input("中间合约 (Middle Leg)", value=mid_leg_default)
    far_leg = st.text_input("远端合约 (Far Leg)", value=far_leg_default)
    submitted = st.button("🚀 生成图表")

if submitted:
    if near_leg and mid_leg and far_leg:
        with st.spinner('正在获取数据并计算指标...'):
            symbols = {"near": near_leg, "mid": mid_leg, "far": far_leg}
            final_df = create_spread_dataframe(symbols["near"], symbols["mid"], symbols["far"])
        if final_df is not None:
            st.success('数据处理完成！')
            fig = plot_unified_chart(final_df, symbols)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.error('无法获取或处理数据，请检查合约代码是否正确或稍后再试。')
    else:
        st.warning('请输入全部三个合约代码。')