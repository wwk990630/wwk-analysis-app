import streamlit as st
import yinhedata as yh
import pandas as pd
import plotly.graph_objects as go
from datetime import date, timedelta

# --- 商品代码到中文名称的映射 ---
COMMODITY_MAP = {
    "SH": "烧碱",
    "SA": "纯碱",
    "FG": "玻璃",
}

# --- 数据处理函数 (已升级，增加timeframe和数据显示逻辑) ---
@st.cache_data
def create_spread_dataframe(leg1_symbol, leg2_symbol, leg3_symbol, timeframe):
    print(f"开始获取并处理数据：{leg1_symbol}, {leg2_symbol}, {leg3_symbol} @ {timeframe}")
    
    # --- 数据获取与对齐 ---
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

    # --- 计算价差OHLC ---
    spread_df = pd.DataFrame(index=df_merged.index)
    spread_df['Open'] = df_merged['open_leg1'] + df_merged['open_leg3'] - 2 * df_merged['open_leg2']
    spread_df['Close'] = df_merged['close_leg1'] + df_merged['close_leg3'] - 2 * df_merged['close_leg2']
    spread_df['High'] = df_merged['high_leg1'] + df_merged['high_leg3'] - 2 * df_merged['low_leg2']
    spread_df['Low'] = df_merged['low_leg1'] + df_merged['low_leg3'] - 2 * df_merged['high_leg2']
    
    # --- 【核心优化】根据选择的时间周期，筛选不同长度的数据 ---
    if not spread_df.empty:
        last_timestamp = spread_df.index[-1]
        if timeframe == '1min':
            days_to_show = 2
            start_date = last_timestamp - timedelta(days=days_to_show)
            filtered_df = spread_df[spread_df.index >= start_date].copy()
            print(f"数据筛选完成，1分钟周期仅显示最近 {days_to_show} 天的数据。")
        elif timeframe == '5min':
            days_to_show = 15
            start_date = last_timestamp - timedelta(days=days_to_show)
            filtered_df = spread_df[spread_df.index >= start_date].copy()
            print(f"数据筛选完成，5分钟周期仅显示最近 {days_to_show} 天的数据。")
        else: # 10min, 15min, 30min, 60min
            filtered_df = spread_df.copy()
            print(f"数据筛选完成，{timeframe} 周期显示全部可用数据。")
    else:
        return None

    if filtered_df.empty: return None
        
    # --- 在筛选后的数据上计算所有分析指标 ---
    filtered_df['avg_price'] = filtered_df['Close'].expanding().mean()
    filtered_df['open_price'] = filtered_df['Open'].iloc[0]
    window, std_multiplier = 20, 2
    filtered_df['sma_20'] = filtered_df['Close'].rolling(window=window).mean()
    filtered_df['std_dev'] = filtered_df['Close'].rolling(window=window).std()
    filtered_df['upper_band'] = filtered_df['sma_20'] + (filtered_df['std_dev'] * std_multiplier)
    filtered_df['lower_band'] = filtered_df['sma_20'] - (filtered_df['std_dev'] * std_multiplier)
    filtered_df['day_high'] = filtered_df['High'].expanding().max()
    filtered_df['day_low'] = filtered_df['Low'].expanding().min()
    
    return filtered_df

# --- 绘图函数 (已升级，动态显示周期) ---
def plot_unified_chart(daily_df, symbols, timeframe):
    commodity_code = symbols['near'][:2]
    commodity_name = COMMODITY_MAP.get(commodity_code.upper(), commodity_code)
    # 动态标题
    title_text = f"{commodity_name} 蝶式价差 ({symbols['near']}-{symbols['mid']}-{symbols['far']}) - {timeframe}周期"

    fig = go.Figure()
    # ... (添加图层和按钮的代码与上一版完全相同)
    fig.add_trace(go.Scatter(x=daily_df.index, y=daily_df['Close'], mode='lines', name='价差分时线', line=dict(color='#4A90E2', width=1.5), fill='tozeroy', fillcolor='rgba(74, 144, 226, 0.1)', visible=True))
    fig.add_trace(go.Scatter(x=daily_df.index, y=daily_df['avg_price'], mode='lines', name='日内均价', line=dict(color='#F5A623', width=1), visible=True))
    fig.add_trace(go.Scatter(x=daily_df.index, y=daily_df['open_price'], mode='lines', name='开盘价', line=dict(color='grey', width=1, dash='dash'), visible=True))
    fig.add_trace(go.Candlestick(x=daily_df.index, open=daily_df['Open'], high=daily_df['High'], low=daily_df['Low'], close=daily_df['Close'], name='价差K线', increasing_line_color='#ff5a5a', decreasing_line_color='#49c98a', visible=False))
    fig.add_trace(go.Scatter(x=daily_df.index, y=daily_df['upper_band'], mode='lines', name='布林带上轨', line=dict(color='purple', width=1, dash='dash'), visible=False))
    fig.add_trace(go.Scatter(x=daily_df.index, y=daily_df['sma_20'], mode='lines', name='中轨线', line=dict(color='purple', width=0.8), visible=False))
    fig.add_trace(go.Scatter(x=daily_df.index, y=daily_df['lower_band'], mode='lines', name='布林带下轨', line=dict(color='purple', width=1, dash='dash'), visible=False))
    fig.add_trace(go.Scatter(x=daily_df.index, y=daily_df['day_high'], mode='lines', name='日内高点', line=dict(color='#ff9b85', width=1.5, dash='dot'), visible=False))
    fig.add_trace(go.Scatter(x=daily_df.index, y=daily_df['day_low'], mode='lines', name='日内低点', line=dict(color='#90be6d', width=1.5, dash='dot'), visible=False))
    fig.update_layout(updatemenus=[dict(type="buttons", direction="right", active=0, x=0.5, y=1.15, xanchor="center", yanchor="top", buttons=list([dict(label="简洁分时图", method="update", args=[{"visible": [True, True, True, False, False, False, False, False, False]}]), dict(label="精密分析图", method="update", args=[{"visible": [False, False, False, True, True, True, True, True, True]}])]))])
    fig.update_layout(title=title_text, yaxis_title='价差值', xaxis_title='时间', template='plotly_white', xaxis_rangeslider_visible=False, font=dict(family="Hiragino Sans GB, PingFang SC, SimHei"), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    return fig

# --- Streamlit Web 应用界面 ---
st.set_page_config(layout="wide")
st.title("🦋 多周期蝶式套利分析工具")

with st.sidebar:
    st.header("参数选择")
    
    preset = st.selectbox('选择预置组合', ('烧碱 (SH)', '纯碱 (SA)', '玻璃 (FG)', '自定义'))
    if preset == '烧碱 (SH)':
        near_leg_default, mid_leg_default, far_leg_default = "SH2511", "SH2512", "SH2601"
    elif preset == '纯碱 (SA)':
        near_leg_default, mid_leg_default, far_leg_default = "SA2601", "SA2605", "SA2609"
    elif preset == '玻璃 (FG)':
        near_leg_default, mid_leg_default, far_leg_default = "FG2601", "FG2605", "FG2609"
    else:
        near_leg_default, mid_leg_default, far_leg_default = "", "", ""

    near_leg = st.text_input("近端合约", value=near_leg_default)
    mid_leg = st.text_input("中间合约", value=mid_leg_default)
    far_leg = st.text_input("远端合约", value=far_leg_default)

    # --- 【新增UI】时间周期选择框 ---
    timeframe_options = ['1min', '5min', '10min', '15min', '30min', '60min']
    selected_timeframe = st.selectbox(
        '选择时间周期',
        options=timeframe_options,
        index=0 # 默认选择第一个'1min'
    )

    submitted = st.button("🚀 生成图表")

if submitted:
    if near_leg and mid_leg and far_leg:
        with st.spinner(f'正在获取 {selected_timeframe} 周期数据并计算...'):
            symbols = {"near": near_leg, "mid": mid_leg, "far": far_leg}
            final_df = create_spread_dataframe(symbols["near"], symbols["mid"], symbols["far"], selected_timeframe)
        
        if final_df is not None:
            st.success('数据处理完成！')
            fig = plot_unified_chart(final_df, symbols, selected_timeframe)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.error('无法获取或处理数据，请检查合约代码是否正确或该周期下数据是否充足。')
    else:
        st.warning('请输入全部三个合约代码。')