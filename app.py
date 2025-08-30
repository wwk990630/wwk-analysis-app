import streamlit as st
import yinhedata as yh
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import date, timedelta

# --- 商品代码到中文名称的映射 ---
COMMODITY_MAP = { "SH": "烧碱", "SA": "纯碱", "FG": "玻璃" }

# --- 数据处理函数 (已升级，支持多策略) ---
@st.cache_data
def create_spread_dataframe(symbols: dict, timeframe: str, strategy_type: str):
    """
    统一的数据处理函数：根据策略类型获取数据并计算所有指标。
    """
    contract_legs = list(symbols.values())
    print(f"开始获取 {strategy_type} 数据: {contract_legs} @ {timeframe}")
    
    # --- 数据获取与对齐 ---
    try:
        dfs_raw = {f"leg{i+1}": yh.features_history(leg, timeframe) for i, leg in enumerate(contract_legs)}
    except Exception as e:
        st.error(f"API数据获取失败: {e}")
        return None

    # 检查返回的数据是否有效
    for i, (name, df) in enumerate(dfs_raw.items()):
        if df is None or df.empty:
            st.error(f"合约 {contract_legs[i]} 未能获取到数据，请检查代码是否有效。")
            return None

    dfs_processed = {}
    for i, (name, df) in enumerate(dfs_raw.items()):
        try:
            df['时间'] = pd.to_datetime(df['时间'])
            df.set_index('时间', inplace=True)
            df = df[['开盘价', '最高价', '最低价', '收盘价']].rename(columns={
                '开盘价': f'open_{name}', '最高价': f'high_{name}',
                '最低价': f'low_{name}', '收盘价': f'close_{name}'
            })
            dfs_processed[name] = df
        except KeyError:
            st.error(f"错误: {name} 的列名不正确。")
            return None
            
    df_merged = pd.concat(dfs_processed.values(), axis=1)
    df_merged.dropna(inplace=True)
    if df_merged.empty:
        st.error("错误：数据对齐后为空，可能是合约交易时间不一致或数据缺失。")
        return None

    # --- 【核心升级】根据策略类型计算价差OHLC ---
    spread_df = pd.DataFrame(index=df_merged.index)
    if strategy_type == '蝶式套利 (Butterfly)':
        spread_df['Open'] = df_merged['open_leg1'] + df_merged['open_leg3'] - 2 * df_merged['open_leg2']
        spread_df['Close'] = df_merged['close_leg1'] + df_merged['close_leg3'] - 2 * df_merged['close_leg2']
        spread_df['High'] = df_merged['high_leg1'] + df_merged['high_leg3'] - 2 * df_merged['low_leg2']
        spread_df['Low'] = df_merged['low_leg1'] + df_merged['low_leg3'] - 2 * df_merged['high_leg2']
    elif strategy_type == '秃鹰套利 (Condor)':
        # 公式: (L1-L2) - (L3-L4) = L1 - L2 - L3 + L4
        spread_df['Open'] = df_merged['open_leg1'] - df_merged['open_leg2'] - df_merged['open_leg3'] + df_merged['open_leg4']
        spread_df['Close'] = df_merged['close_leg1'] - df_merged['close_leg2'] - df_merged['close_leg3'] + df_merged['close_leg4']
        spread_df['High'] = df_merged['high_leg1'] - df_merged['low_leg2'] - df_merged['low_leg3'] + df_merged['high_leg4']
        spread_df['Low'] = df_merged['low_leg1'] - df_merged['high_leg2'] - df_merged['high_leg3'] + df_merged['low_leg4']
    
    # ... 后续的数据筛选和指标计算逻辑不变 ...
    if not spread_df.empty:
        last_timestamp = spread_df.index[-1]
        if timeframe == '1min': days_to_show = 2
        elif timeframe == '5min': days_to_show = 15
        else: days_to_show = None
        if days_to_show:
            start_date = last_timestamp - timedelta(days=days_to_show)
            filtered_df = spread_df[spread_df.index >= start_date].copy()
        else: filtered_df = spread_df.copy()
    else: return None
    if filtered_df.empty: return None
        
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

# --- 绘图函数 (已升级，支持多策略标题) ---
def plot_final_chart(df, symbols, timeframe, strategy_type):
    commodity_code = list(symbols.values())[0][:2]
    commodity_name = COMMODITY_MAP.get(commodity_code.upper(), commodity_code)
    
    # 动态生成标题
    if strategy_type == '蝶式套利 (Butterfly)':
        strategy_name = "蝶式价差"
        contract_str = f"({symbols['near']}-{symbols['mid']}-{symbols['far']})"
    else: # Condor
        strategy_name = "秃鹰价差"
        contract_str = f"({symbols['leg1']}-{symbols['leg2']} vs {symbols['leg3']}-{symbols['leg4']})"
        
    title_text = f"{commodity_name} {strategy_name} {contract_str} - {timeframe}周期"

    # ... 后续绘图逻辑不变 ...
    fig = go.Figure()
    x_axis_labels = df.index
    x_axis_values = list(range(len(x_axis_labels)))
    fig.add_trace(go.Scatter(x=x_axis_values, y=df['Close'], mode='lines', name='价差分时线', line=dict(color='#4A90E2', width=1.5), visible=True, hovertemplate='%{y:.2f}'))
    fig.add_trace(go.Scatter(x=x_axis_values, y=df['avg_price'], mode='lines', name='日内均价', line=dict(color='#F5A623', width=1), visible=True, hovertemplate='%{y:.2f}'))
    fig.add_trace(go.Scatter(x=x_axis_values, y=df['open_price'], mode='lines', name='开盘价', line=dict(color='grey', width=1, dash='dash'), visible=True, hovertemplate='%{y:.2f}'))
    fig.add_trace(go.Candlestick(x=x_axis_values, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='价差K线', increasing_line_color='#ff5a5a', decreasing_line_color='#49c98a', visible=False))
    fig.add_trace(go.Scatter(x=x_axis_values, y=df['upper_band'], mode='lines', name='布林带上轨', line=dict(color='purple', width=1, dash='dash'), visible=False, hovertemplate='%{y:.2f}'))
    fig.add_trace(go.Scatter(x=x_axis_values, y=df['sma_20'], mode='lines', name='中轨线', line=dict(color='purple', width=0.8), visible=False, hovertemplate='%{y:.2f}'))
    fig.add_trace(go.Scatter(x=x_axis_values, y=df['lower_band'], mode='lines', name='布林带下轨', line=dict(color='purple', width=1, dash='dash'), visible=False, hovertemplate='%{y:.2f}'))
    fig.add_trace(go.Scatter(x=x_axis_values, y=df['day_high'], mode='lines', name='日内高点', line=dict(color='#ff9b85', width=1.5, dash='dot'), visible=False, hovertemplate='%{y:.2f}'))
    fig.add_trace(go.Scatter(x=x_axis_values, y=df['day_low'], mode='lines', name='日内低点', line=dict(color='#90be6d', width=1.5, dash='dot'), visible=False, hovertemplate='%{y:.2f}'))
    tick_vals, tick_texts, last_date = [], [], None
    label_spacing = {'1min': 60, '5min': 24, '10min': 12, '15min': 8, '30min': 4, '60min': 2}
    spacing = label_spacing.get(timeframe, 10)
    for i, timestamp in enumerate(x_axis_labels):
        if i % spacing == 0:
            current_date = timestamp.date()
            if current_date != last_date:
                tick_texts.append(f"<b><span style='color:red;'>{timestamp.strftime('%m-%d')}</span></b>")
                last_date = current_date
            else:
                tick_texts.append(timestamp.strftime('%H:%M'))
            tick_vals.append(i)
    fig.update_layout(title=title_text, updatemenus=[dict(type="buttons", direction="right", active=0, x=0.5, y=1.12, xanchor="center", yanchor="top", buttons=list([dict(label="简洁分时图", method="update", args=[{"visible": [True, True, True, False, False, False, False, False, False]}]), dict(label="精密分析图", method="update", args=[{"visible": [False, False, False, True, True, True, True, True, True]}])]))])
    fig.update_layout(yaxis_title='价差值', template='plotly_white', xaxis_rangeslider_visible=False, font=dict(family="Hiragino Sans GB, PingFang SC, SimHei"), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1), hovermode='x unified')
    fig.update_xaxes(tickmode='array', tickvals=tick_vals, ticktext=tick_texts, showspikes=True, spikemode='across', spikesnap='cursor', spikedash='dot', spikecolor='grey', spikethickness=1)
    fig.update_yaxes(showspikes=True, spikemode='across', spikesnap='cursor', spikedash='dot', spikecolor='grey', spikethickness=1)
    fig.update_traces(xhoverformat='%m-%d %H:%M')
    return fig

# --- Streamlit Web 应用界面 ---
st.set_page_config(layout="wide")
st.title("🦋 多策略跨期套利分析工具 v4.0")

with st.sidebar:
    st.header("参数选择")
    
    # --- 【核心升级】策略选择器 ---
    strategy_type = st.selectbox(
        '选择分析策略',
        ('蝶式套利 (Butterfly)', '秃鹰套利 (Condor)')
    )
    
    st.subheader("合约配置")
    
    # --- 【核心升级】根据策略动态显示输入框 ---
    symbols = {}
    if strategy_type == '蝶式套利 (Butterfly)':
        preset = st.selectbox('选择预置组合', ('烧碱 (SH)', '纯碱 (SA)', '玻璃 (FG)', '自定义'))
        if preset == '烧碱 (SH)': near_d, mid_d, far_d = "SH2511", "SH2512", "SH2601"
        elif preset == '纯碱 (SA)': near_d, mid_d, far_d = "SA2601", "SA2605", "SA2609"
        elif preset == '玻璃 (FG)': near_d, mid_d, far_d = "FG2601", "FG2605", "FG2609"
        else: near_d, mid_d, far_d = "", "", ""
        symbols['near'] = st.text_input("近端合约 (Near)", value=near_d)
        symbols['mid'] = st.text_input("中间合约 (Mid)", value=mid_d)
        symbols['far'] = st.text_input("远端合约 (Far)", value=far_d)
        
    else: # 秃鹰套利 (Condor)
        st.info("请输入4个连续或相近的合约月份。")
        symbols['leg1'] = st.text_input("第一腿 (Leg 1)", value="SH2511")
        symbols['leg2'] = st.text_input("第二腿 (Leg 2)", value="SH2512")
        symbols['leg3'] = st.text_input("第三腿 (Leg 3)", value="SH2601")
        symbols['leg4'] = st.text_input("第四腿 (Leg 4)", value="SH2602")

    timeframe_options = ['1min', '5min', '10min', '15min', '30min', '60min']
    selected_timeframe = st.selectbox('选择时间周期', options=timeframe_options, index=0)

    submitted = st.button("🚀 生成图表")

# --- 主页面逻辑 ---
if submitted:
    # 检查所有合约代码是否都已输入
    if all(symbols.values()):
        with st.spinner(f'正在为 {strategy_type} 获取 {selected_timeframe} 周期数据...'):
            final_df = create_spread_dataframe(symbols, selected_timeframe, strategy_type)
        
        if final_df is not None:
            st.success('数据处理完成！')
            fig = plot_final_chart(final_df, symbols, selected_timeframe, strategy_type)
            st.plotly_chart(fig, use_container_width=True)
        else:
            # 错误信息已在函数内部通过 st.error 显示
            pass 
    else:
        st.warning('请输入策略所需的所有合约代码。')
else:
    st.info("请在左侧侧边栏选择策略和合约，然后点击“生成图表”。")