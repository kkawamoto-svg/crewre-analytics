"""crewre EC分析ダッシュボード"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

# ── パスワード保護 ────────────────────────────────────
def check_password():
    """パスワード認証"""
    if "password" not in st.secrets:
        return True  # ローカル開発時はスキップ
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if st.session_state.authenticated:
        return True
    pw = st.text_input("パスワードを入力してください", type="password")
    if pw == st.secrets["password"]:
        st.session_state.authenticated = True
        st.rerun()
    elif pw:
        st.error("パスワードが違います")
    return False

if not check_password():
    st.stop()
from data_loader import (
    load_sales_by_period,
    load_sales_by_product,
    load_sales_by_member,
    load_sales_by_age,
    load_sales_by_occupation,
    load_orders,
    load_logizard_orders,
    load_customers,
    load_products,
    load_categories,
)
from shopify_loader import (
    load_shopify_orders,
    load_shopify_customers,
    load_shopify_products,
    load_shopify_line_items,
)
from ga4_loader import (
    load_ga4_daily,
    load_ga4_channel,
    load_ga4_source_medium,
    load_ga4_device,
    load_ga4_landing_page,
)

st.set_page_config(page_title="crewre EC分析", page_icon="📊", layout="wide")

# ── サイドバー ─────────────────────────────────────────
st.sidebar.title("crewre EC分析")
page = st.sidebar.radio(
    "ページ選択",
    ["売上ダッシュボード", "顧客分析", "商品分析", "受注詳細", "Shopify統合", "GA4アクセス分析", "EC-CUBE × Shopify比較"],
)


def fmt_yen(val):
    """金額を日本円フォーマット（カンマ区切り）"""
    return f"¥{val:,.0f}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 売上ダッシュボード
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
if page == "売上ダッシュボード":
    st.title("売上ダッシュボード")

    sales = load_sales_by_period()

    # 期間フィルター
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("開始日", value=sales["期間"].min())
    with col2:
        end_date = st.date_input("終了日", value=sales["期間"].max())

    mask = (sales["期間"] >= pd.Timestamp(start_date)) & (sales["期間"] <= pd.Timestamp(end_date))
    filtered = sales[mask].copy()

    # KPIカード
    total_sales = filtered["購入合計"].sum()
    total_orders = filtered["購入件数"].sum()
    avg_order = total_sales / total_orders if total_orders > 0 else 0

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("総売上", fmt_yen(total_sales))
    k2.metric("総注文数", f"{total_orders:,.0f}件")
    k3.metric("平均注文額", fmt_yen(avg_order))
    k4.metric("データ期間", f"{(pd.Timestamp(end_date) - pd.Timestamp(start_date)).days}日")

    # ── 月別売上推移 ─────────────────────────────────
    st.subheader("月別売上推移")
    monthly = filtered.copy()
    monthly["年月"] = monthly["期間"].dt.to_period("M").astype(str)
    monthly_agg = monthly.groupby("年月").agg(
        売上=("購入合計", "sum"),
        注文数=("購入件数", "sum"),
    ).reset_index()

    fig = go.Figure()
    fig.add_trace(go.Bar(x=monthly_agg["年月"], y=monthly_agg["売上"], name="売上", marker_color="#4F46E5"))
    fig.add_trace(go.Scatter(x=monthly_agg["年月"], y=monthly_agg["注文数"], name="注文数", yaxis="y2", marker_color="#F59E0B", mode="lines+markers"))
    fig.update_layout(
        yaxis=dict(title="売上 (円)", tickformat=","),
        yaxis2=dict(title="注文数", overlaying="y", side="right"),
        height=450,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── 日別売上推移 ─────────────────────────────────
    st.subheader("日別売上推移")
    fig2 = px.line(filtered, x="期間", y="購入合計", labels={"購入合計": "売上 (円)", "期間": "日付"})
    fig2.update_layout(height=350)
    st.plotly_chart(fig2, use_container_width=True)

    # ── 曜日別分析 ────────────────────────────────────
    st.subheader("曜日別 平均売上")
    filtered["曜日"] = filtered["期間"].dt.dayofweek
    dow_map = {0: "月", 1: "火", 2: "水", 3: "木", 4: "金", 5: "土", 6: "日"}
    filtered["曜日名"] = filtered["曜日"].map(dow_map)
    dow_agg = filtered.groupby(["曜日", "曜日名"]).agg(平均売上=("購入合計", "mean"), 平均注文数=("購入件数", "mean")).reset_index().sort_values("曜日")
    fig3 = px.bar(dow_agg, x="曜日名", y="平均売上", text_auto=",.0f", labels={"平均売上": "平均売上 (円)"})
    fig3.update_layout(height=350)
    st.plotly_chart(fig3, use_container_width=True)

    # ── 性別内訳 ──────────────────────────────────────
    st.subheader("性別売上比率")
    member = load_sales_by_member()
    fig4 = px.pie(member, names="会員", values="購入合計", hole=0.4)
    fig4.update_layout(height=350)
    st.plotly_chart(fig4, use_container_width=True)

    # ── 前年同月比較 ──────────────────────────────────
    st.subheader("前年同月比較")
    monthly["年"] = monthly["期間"].dt.year
    monthly["月"] = monthly["期間"].dt.month
    yoy = monthly.groupby(["年", "月"]).agg(売上=("購入合計", "sum")).reset_index()
    yoy["月名"] = yoy["月"].apply(lambda m: f"{m}月")
    fig5 = px.bar(yoy, x="月名", y="売上", color="年", barmode="group", text_auto=",.0f")
    fig5.update_layout(height=400)
    st.plotly_chart(fig5, use_container_width=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 顧客分析
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
elif page == "顧客分析":
    st.title("顧客分析")

    # ── 年代別 ────────────────────────────────────────
    st.subheader("年代別 購入分析")
    age = load_sales_by_age()
    age_order = ["10代", "20代", "30代", "40代", "50代", "60代", "70代", "未回答"]
    age["年齢"] = pd.Categorical(age["年齢"], categories=age_order, ordered=True)
    age = age.sort_values("年齢")

    col1, col2 = st.columns(2)
    with col1:
        fig = px.bar(age, x="年齢", y="購入件数", text_auto=True, color="年齢")
        fig.update_layout(height=400, title="購入件数")
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        fig = px.bar(age, x="年齢", y="購入合計", text_auto=",.0f", color="年齢")
        fig.update_layout(height=400, title="購入金額")
        st.plotly_chart(fig, use_container_width=True)

    # ── 年代別 客単価 ─────────────────────────────────
    st.subheader("年代別 平均客単価")
    fig = px.bar(age, x="年齢", y="購入平均", text_auto=",.0f")
    fig.update_layout(height=350)
    st.plotly_chart(fig, use_container_width=True)

    # ── 職業別 ────────────────────────────────────────
    st.subheader("職業別 購入分析")
    occ = load_sales_by_occupation()
    occ = occ.sort_values("購入合計", ascending=False)
    fig = px.bar(occ, x="職業", y="購入合計", text_auto=",.0f")
    fig.update_layout(height=400)
    st.plotly_chart(fig, use_container_width=True)

    # ── 会員別 ────────────────────────────────────────
    st.subheader("会員種別 購入比率")
    member = load_sales_by_member()
    col1, col2 = st.columns(2)
    with col1:
        fig = px.pie(member, names="会員", values="購入件数", hole=0.4, title="件数比率")
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        fig = px.pie(member, names="会員", values="購入合計", hole=0.4, title="金額比率")
        st.plotly_chart(fig, use_container_width=True)

    # ── RFM分析 ───────────────────────────────────────
    st.subheader("RFM分析（会員マスターベース）")
    st.caption("Recency(最終購入からの日数) / Frequency(購入回数) / Monetary(購入金額)")

    customers = load_customers()
    rfm = customers[customers["購入回数"] > 0].copy()

    if len(rfm) > 0 and "最終購入日" in rfm.columns:
        now = pd.Timestamp("2026-02-19")
        rfm["Recency"] = (now - rfm["最終購入日"]).dt.days
        rfm["Frequency"] = rfm["購入回数"]
        rfm["Monetary"] = rfm["お買い上げ合計額"]
        rfm = rfm.dropna(subset=["Recency", "Frequency", "Monetary"])

        # RFMスコア（3段階）
        rfm["R_score"] = pd.qcut(rfm["Recency"], 3, labels=["高", "中", "低"], duplicates="drop")
        rfm["F_score"] = pd.qcut(rfm["Frequency"].rank(method="first"), 3, labels=["低", "中", "高"], duplicates="drop")
        rfm["M_score"] = pd.qcut(rfm["Monetary"].rank(method="first"), 3, labels=["低", "中", "高"], duplicates="drop")

        # セグメント
        def segment(row):
            r, f, m = str(row["R_score"]), str(row["F_score"]), str(row["M_score"])
            if r == "高" and f == "高":
                return "優良顧客"
            elif r == "高" and f == "低":
                return "新規顧客"
            elif r == "低" and f == "高":
                return "離反リスク"
            elif r == "低" and f == "低":
                return "休眠顧客"
            else:
                return "一般顧客"

        rfm["セグメント"] = rfm.apply(segment, axis=1)
        seg_count = rfm["セグメント"].value_counts().reset_index()
        seg_count.columns = ["セグメント", "人数"]

        col1, col2 = st.columns(2)
        with col1:
            fig = px.pie(seg_count, names="セグメント", values="人数", hole=0.4, title="顧客セグメント分布")
            st.plotly_chart(fig, use_container_width=True)
        with col2:
            seg_monetary = rfm.groupby("セグメント")["Monetary"].mean().reset_index()
            seg_monetary.columns = ["セグメント", "平均購入額"]
            fig = px.bar(seg_monetary, x="セグメント", y="平均購入額", text_auto=",.0f", title="セグメント別 平均購入額")
            st.plotly_chart(fig, use_container_width=True)

        # Scatter
        st.subheader("RFM散布図")
        fig = px.scatter(
            rfm.sample(min(5000, len(rfm))),
            x="Recency", y="Monetary", size="Frequency",
            color="セグメント", hover_data=["お名前(姓)"] if "お名前(姓)" in rfm.columns else None,
            labels={"Recency": "最終購入からの日数", "Monetary": "累計購入額"},
        )
        fig.update_layout(height=500)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("購入履歴のある会員データがありません")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 商品分析
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
elif page == "商品分析":
    st.title("商品分析（SKU別）")

    # ── データソース選択 & 期間設定 ────────────────────
    st.subheader("分析条件")
    col1, col2, col3 = st.columns(3)
    with col1:
        data_source = st.selectbox("データソース", ["EC-CUBE + Shopify（統合）", "EC-CUBE のみ", "Shopify のみ"])
    with col2:
        prod_start = st.date_input("開始日", value=pd.Timestamp("2023-08-01"), key="prod_start")
    with col3:
        prod_end = st.date_input("終了日", value=pd.Timestamp.today(), key="prod_end")

    # ── EC-CUBEデータ（Logizard明細） ─────────────────
    @st.cache_data
    def cached_logizard():
        df = load_logizard_orders()
        df["SKU"] = df["商品規格ID"].astype(str)
        df["金額"] = df["単価"] * df["個数"]
        df["ソース"] = "EC-CUBE"
        df["カラー"] = df["商品規格名1"].fillna("")
        df["サイズ"] = df["商品規格名2"].fillna("")
        return df[["注文日時", "SKU", "商品名", "単価", "個数", "金額", "カラー", "サイズ", "ソース"]]

    # ── Shopifyデータ ─────────────────────────────────
    @st.cache_data(ttl=300)
    def cached_shopify_lines():
        try:
            df = load_shopify_line_items()
        except Exception:
            return pd.DataFrame()
        if len(df) > 0:
            df = df[~df["キャンセル"]].copy()
            # バリアント「black / 1」をカラーとサイズに分割
            variant_split = df["バリアント"].str.split(r"\s*/\s*", n=1, expand=True)
            df["カラー"] = variant_split[0].fillna("") if 0 in variant_split.columns else ""
            df["サイズ"] = variant_split[1].fillna("") if 1 in variant_split.columns else ""
            return df[["注文日時", "SKU", "商品名", "単価", "数量", "金額", "カラー", "サイズ", "ソース"]]
        return pd.DataFrame()

    with st.spinner("商品データ取得中..."):
        ec_lines = cached_logizard()
        sp_lines = cached_shopify_lines()

    # Shopifyデータの「数量」を「個数」に統一
    if len(sp_lines) > 0:
        sp_lines = sp_lines.rename(columns={"数量": "個数"})

    # タイムゾーン統一（すべてtz-naiveに）
    if len(ec_lines) > 0 and ec_lines["注文日時"].dt.tz is not None:
        ec_lines["注文日時"] = ec_lines["注文日時"].dt.tz_localize(None)
    if len(sp_lines) > 0 and sp_lines["注文日時"].dt.tz is not None:
        sp_lines["注文日時"] = sp_lines["注文日時"].dt.tz_localize(None)

    # ソースに応じてデータ結合
    if data_source == "EC-CUBE + Shopify（統合）":
        all_lines = pd.concat([ec_lines, sp_lines], ignore_index=True) if len(sp_lines) > 0 else ec_lines
    elif data_source == "EC-CUBE のみ":
        all_lines = ec_lines
    else:
        all_lines = sp_lines if len(sp_lines) > 0 else pd.DataFrame()

    if len(all_lines) == 0:
        st.warning("データがありません")
    else:
        # 期間フィルター適用
        all_lines = all_lines[
            (all_lines["注文日時"] >= pd.Timestamp(prod_start))
            & (all_lines["注文日時"] <= pd.Timestamp(prod_end) + pd.Timedelta(days=1))
        ].copy()

        # ── SKU別集計 ─────────────────────────────────
        sku_agg = all_lines.groupby(["SKU", "商品名", "カラー", "サイズ"]).agg(
            販売数量=("個数", "sum"),
            売上金額=("金額", "sum"),
            注文件数=("金額", "count"),
            上代=("単価", "max"),
        ).reset_index()
        sku_agg = sku_agg.sort_values("売上金額", ascending=False)
        sku_agg["平均単価"] = (sku_agg["売上金額"] / sku_agg["販売数量"]).round(0)

        # KPI
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("SKU数", f"{len(sku_agg):,}")
        k2.metric("総売上", fmt_yen(sku_agg["売上金額"].sum()))
        k3.metric("総販売数", f"{sku_agg['販売数量'].sum():,.0f}点")
        k4.metric("平均単価", fmt_yen(sku_agg["売上金額"].sum() / sku_agg["販売数量"].sum() if sku_agg["販売数量"].sum() > 0 else 0))

        # ── SKU別売上ランキング ────────────────────────
        st.subheader("SKU別 売上ランキング")
        top_n = st.slider("表示件数", 10, 100, 30)
        top = sku_agg.head(top_n).copy()
        top["表示名"] = top["商品名"].str[:20] + " / " + top["カラー"].astype(str) + " / " + top["サイズ"].astype(str) + " (" + top["SKU"].astype(str) + ")"

        fig = px.bar(top, x="売上金額", y="表示名", orientation="h", text_auto=",.0f",
                     hover_data=["販売数量", "上代", "平均単価"])
        fig.update_layout(height=max(400, top_n * 22), yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig, use_container_width=True)

        # ── SKU別詳細テーブル ─────────────────────────
        st.subheader("SKU別 詳細データ")
        display_df = sku_agg[["SKU", "商品名", "カラー", "サイズ", "上代", "平均単価", "販売数量", "注文件数", "売上金額"]].copy()
        display_df["上代"] = display_df["上代"].apply(lambda x: f"¥{x:,.0f}")
        display_df["平均単価"] = display_df["平均単価"].apply(lambda x: f"¥{x:,.0f}")
        display_df["売上金額"] = display_df["売上金額"].apply(lambda x: f"¥{x:,.0f}")
        st.dataframe(display_df, use_container_width=True, height=500)

        # ── ABC分析 ───────────────────────────────────
        st.subheader("ABC分析（SKU売上金額ベース）")
        abc = sku_agg.copy()
        abc["累計売上"] = abc["売上金額"].cumsum()
        total = abc["売上金額"].sum()
        abc["累計比率"] = abc["累計売上"] / total * 100
        abc["ランク"] = abc["累計比率"].apply(lambda x: "A" if x <= 70 else ("B" if x <= 90 else "C"))

        rank_summary = abc.groupby("ランク").agg(
            SKU数=("SKU", "count"),
            売上合計=("売上金額", "sum"),
        ).reset_index()
        rank_summary["売上比率"] = (rank_summary["売上合計"] / total * 100).round(1)

        col1, col2 = st.columns(2)
        with col1:
            fig = px.pie(rank_summary, names="ランク", values="売上合計", hole=0.4,
                         color="ランク", color_discrete_map={"A": "#4F46E5", "B": "#F59E0B", "C": "#EF4444"},
                         title="ABC売上比率")
            st.plotly_chart(fig, use_container_width=True)
        with col2:
            st.dataframe(rank_summary, use_container_width=True)

        # パレート図
        fig = go.Figure()
        fig.add_trace(go.Bar(x=list(range(len(abc))), y=abc["売上金額"].values, name="売上"))
        fig.add_trace(go.Scatter(x=list(range(len(abc))), y=abc["累計比率"].values, name="累計比率%", yaxis="y2"))
        fig.update_layout(
            title="パレート図",
            yaxis=dict(title="売上 (円)"),
            yaxis2=dict(title="累計比率 (%)", overlaying="y", side="right", range=[0, 105]),
            height=400,
        )
        st.plotly_chart(fig, use_container_width=True)

        # ── 月別SKU売上推移（TOP10商品） ──────────────
        st.subheader("月別 売上推移（TOP 10 SKU）")
        top10_skus = sku_agg.head(10)["SKU"].tolist()
        monthly_sku = all_lines[all_lines["SKU"].isin(top10_skus)].copy()
        monthly_sku["年月"] = monthly_sku["注文日時"].dt.to_period("M").astype(str)
        monthly_sku_agg = monthly_sku.groupby(["年月", "SKU", "商品名"]).agg(売上=("金額", "sum")).reset_index()
        monthly_sku_agg["表示名"] = monthly_sku_agg["商品名"].str[:15] + " (" + monthly_sku_agg["SKU"].str[:15] + ")"
        fig = px.line(monthly_sku_agg, x="年月", y="売上", color="表示名")
        fig.update_layout(height=500, legend=dict(orientation="h", yanchor="top", y=-0.15))
        st.plotly_chart(fig, use_container_width=True)

        # ── 単価帯別分析 ──────────────────────────────
        st.subheader("価格帯別 販売分析")
        bins = [0, 3000, 5000, 8000, 10000, 15000, 20000, 30000, float("inf")]
        labels = ["〜3K", "3-5K", "5-8K", "8-10K", "10-15K", "15-20K", "20-30K", "30K〜"]
        sku_agg["価格帯"] = pd.cut(sku_agg["上代"], bins=bins, labels=labels, right=False)
        price_agg = sku_agg.groupby("価格帯").agg(
            SKU数=("SKU", "count"),
            販売数量=("販売数量", "sum"),
            売上金額=("売上金額", "sum"),
        ).reset_index()

        col1, col2 = st.columns(2)
        with col1:
            fig = px.bar(price_agg, x="価格帯", y="売上金額", text_auto=",.0f", title="価格帯別 売上")
            fig.update_layout(height=350)
            st.plotly_chart(fig, use_container_width=True)
        with col2:
            fig = px.bar(price_agg, x="価格帯", y="販売数量", text_auto=True, title="価格帯別 販売数量")
            fig.update_layout(height=350)
            st.plotly_chart(fig, use_container_width=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 受注詳細
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
elif page == "受注詳細":
    st.title("受注詳細・検索")

    @st.cache_data
    def cached_orders():
        return load_orders()

    orders = cached_orders()

    # フィルター
    col1, col2, col3 = st.columns(3)
    with col1:
        if "対応状況" in orders.columns:
            statuses = ["すべて"] + sorted(orders["対応状況"].dropna().unique().tolist())
            status_filter = st.selectbox("対応状況", statuses)
    with col2:
        if "支払い方法" in orders.columns:
            payments = ["すべて"] + sorted(orders["支払い方法"].dropna().unique().tolist())
            payment_filter = st.selectbox("支払い方法", payments)
    with col3:
        search_text = st.text_input("注文番号/名前で検索")

    filtered = orders.copy()
    if "対応状況" in orders.columns and status_filter != "すべて":
        filtered = filtered[filtered["対応状況"] == status_filter]
    if "支払い方法" in orders.columns and payment_filter != "すべて":
        filtered = filtered[filtered["支払い方法"] == payment_filter]
    if search_text:
        mask = filtered.astype(str).apply(lambda row: row.str.contains(search_text, case=False, na=False).any(), axis=1)
        filtered = filtered[mask]

    st.write(f"**{len(filtered):,}件** の受注データ")

    # 表示カラム
    display_cols = ["注文番号", "注文日時", "お名前(姓)", "お名前(名)", "合計", "お支払い合計", "支払い方法", "対応状況", "都道府県"]
    available_cols = [c for c in display_cols if c in filtered.columns]
    st.dataframe(
        filtered[available_cols].sort_values("注文日時", ascending=False).head(500),
        use_container_width=True,
        height=600,
    )

    # 対応状況の集計
    if "対応状況" in orders.columns:
        st.subheader("対応状況別 件数")
        status_counts = orders["対応状況"].value_counts().reset_index()
        status_counts.columns = ["対応状況", "件数"]
        fig = px.bar(status_counts, x="対応状況", y="件数", text_auto=True)
        fig.update_layout(height=350)
        st.plotly_chart(fig, use_container_width=True)

    # 都道府県別
    if "都道府県" in orders.columns:
        st.subheader("都道府県別 注文数")
        pref = orders["都道府県"].value_counts().head(20).reset_index()
        pref.columns = ["都道府県", "件数"]
        fig = px.bar(pref, x="都道府県", y="件数", text_auto=True)
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Shopify統合
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
elif page == "Shopify統合":
    st.title("Shopify リアルタイムデータ")
    st.caption("Shopify APIから最新データを取得して表示します")

    @st.cache_data(ttl=300)  # 5分キャッシュ
    def cached_shopify_orders():
        try:
            return load_shopify_orders()
        except Exception as e:
            st.error(f"Shopify API接続エラー: {e}")
            return pd.DataFrame()

    @st.cache_data(ttl=300)
    def cached_shopify_customers():
        try:
            return load_shopify_customers()
        except Exception as e:
            st.error(f"Shopify顧客API接続エラー: {e}")
            return pd.DataFrame()

    @st.cache_data(ttl=300)
    def cached_shopify_products():
        try:
            return load_shopify_products()
        except Exception as e:
            st.error(f"Shopify商品API接続エラー: {e}")
            return pd.DataFrame()

    with st.spinner("Shopifyからデータ取得中..."):
        sp_orders = cached_shopify_orders()
        sp_customers = cached_shopify_customers()
        sp_products = cached_shopify_products()

    # KPI
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("総注文数", f"{len(sp_orders):,}件")
    k2.metric("総売上", fmt_yen(sp_orders["合計"].sum()) if len(sp_orders) > 0 else "¥0")
    k3.metric("顧客数", f"{len(sp_customers):,}人")
    k4.metric("商品数 (バリアント)", f"{len(sp_products):,}")

    # ── 月別売上推移 ──────────────────────────────────
    if len(sp_orders) > 0:
        st.subheader("Shopify 月別売上推移")
        sp_orders["年月"] = sp_orders["注文日時"].dt.to_period("M").astype(str)
        sp_monthly = sp_orders.groupby("年月").agg(
            売上=("合計", "sum"),
            注文数=("注文番号", "count"),
        ).reset_index()

        fig = go.Figure()
        fig.add_trace(go.Bar(x=sp_monthly["年月"], y=sp_monthly["売上"], name="売上", marker_color="#10B981"))
        fig.add_trace(go.Scatter(x=sp_monthly["年月"], y=sp_monthly["注文数"], name="注文数", yaxis="y2", marker_color="#F59E0B", mode="lines+markers"))
        fig.update_layout(
            yaxis=dict(title="売上 (円)", tickformat=","),
            yaxis2=dict(title="注文数", overlaying="y", side="right"),
            height=450,
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        st.plotly_chart(fig, use_container_width=True)

        # ステータス別
        st.subheader("決済ステータス別")
        col1, col2 = st.columns(2)
        with col1:
            status_counts = sp_orders["ステータス"].value_counts().reset_index()
            status_counts.columns = ["ステータス", "件数"]
            fig = px.pie(status_counts, names="ステータス", values="件数", hole=0.4, title="決済ステータス")
            st.plotly_chart(fig, use_container_width=True)
        with col2:
            ff_counts = sp_orders["フルフィルメント"].value_counts().reset_index()
            ff_counts.columns = ["フルフィルメント", "件数"]
            fig = px.pie(ff_counts, names="フルフィルメント", values="件数", hole=0.4, title="配送ステータス")
            st.plotly_chart(fig, use_container_width=True)

        # 直近注文
        st.subheader("直近の注文")
        recent = sp_orders.sort_values("注文日時", ascending=False).head(50)
        st.dataframe(
            recent[["注文番号", "注文日時", "顧客名", "合計", "ステータス", "フルフィルメント", "支払い方法", "都道府県"]],
            use_container_width=True,
            height=500,
        )

    # ── 顧客TOP ──────────────────────────────────────
    if len(sp_customers) > 0:
        st.subheader("Shopify 顧客 購入額TOP 30")
        top_cust = sp_customers.nlargest(30, "購入合計")
        fig = px.bar(top_cust, x="購入合計", y="名前", orientation="h", text_auto=",.0f")
        fig.update_layout(height=600, yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig, use_container_width=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GA4アクセス分析
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
elif page == "GA4アクセス分析":
    st.title("GA4 アクセス分析")
    st.caption("Google Analytics 4 からリアルタイムデータを取得")

    # 期間選択
    col1, col2 = st.columns(2)
    with col1:
        ga_start = st.date_input("開始日", value=pd.Timestamp("2026-02-01"), key="ga_start")
    with col2:
        ga_end = st.date_input("終了日", value=pd.Timestamp.today(), key="ga_end")

    start_str = ga_start.strftime("%Y-%m-%d")
    end_str = ga_end.strftime("%Y-%m-%d")

    @st.cache_data(ttl=300)
    def cached_ga4_daily(s, e):
        return load_ga4_daily(s, e)

    @st.cache_data(ttl=300)
    def cached_ga4_channel(s, e):
        return load_ga4_channel(s, e)

    @st.cache_data(ttl=300)
    def cached_ga4_source_medium(s, e):
        return load_ga4_source_medium(s, e)

    @st.cache_data(ttl=300)
    def cached_ga4_device(s, e):
        return load_ga4_device(s, e)

    @st.cache_data(ttl=300)
    def cached_ga4_landing(s, e):
        return load_ga4_landing_page(s, e)

    with st.spinner("GA4からデータ取得中..."):
        daily = cached_ga4_daily(start_str, end_str)
        channel = cached_ga4_channel(start_str, end_str)
        device = cached_ga4_device(start_str, end_str)
        source_medium = cached_ga4_source_medium(start_str, end_str)
        landing = cached_ga4_landing(start_str, end_str)

    if len(daily) > 0:
        # KPI
        total_sessions = daily["sessions"].sum()
        total_users = daily["totalUsers"].sum()
        total_new = daily["newUsers"].sum()
        total_pv = daily["screenPageViews"].sum()
        total_purchases = daily["ecommercePurchases"].sum()
        total_revenue = daily["purchaseRevenue"].sum()
        cvr = (total_purchases / total_sessions * 100) if total_sessions > 0 else 0

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("セッション", f"{total_sessions:,.0f}")
        k2.metric("ユーザー", f"{total_users:,.0f}")
        k3.metric("PV", f"{total_pv:,.0f}")
        k4.metric("CVR", f"{cvr:.2f}%")

        k5, k6, k7, k8 = st.columns(4)
        k5.metric("新規ユーザー", f"{total_new:,.0f}")
        k6.metric("新規率", f"{total_new/total_users*100:.1f}%" if total_users > 0 else "0%")
        k7.metric("購入件数", f"{total_purchases:,.0f}")
        k8.metric("GA4売上", fmt_yen(total_revenue))

        # ── 日別推移 ──────────────────────────────────
        st.subheader("日別 セッション・ユーザー推移")
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=daily["date"], y=daily["sessions"], name="セッション", mode="lines", line=dict(color="#4F46E5")))
        fig.add_trace(go.Scatter(x=daily["date"], y=daily["totalUsers"], name="ユーザー", mode="lines", line=dict(color="#10B981")))
        fig.add_trace(go.Scatter(x=daily["date"], y=daily["newUsers"], name="新規ユーザー", mode="lines", line=dict(color="#F59E0B", dash="dot")))
        fig.update_layout(height=400, legend=dict(orientation="h", yanchor="bottom", y=1.02))
        st.plotly_chart(fig, use_container_width=True)

        # ── 日別PV・購入 ─────────────────────────────
        st.subheader("日別 PV・購入件数")
        fig = go.Figure()
        fig.add_trace(go.Bar(x=daily["date"], y=daily["screenPageViews"], name="PV", marker_color="#818CF8"))
        fig.add_trace(go.Scatter(x=daily["date"], y=daily["ecommercePurchases"], name="購入件数", yaxis="y2", mode="lines+markers", marker_color="#EF4444"))
        fig.update_layout(
            yaxis=dict(title="PV"),
            yaxis2=dict(title="購入件数", overlaying="y", side="right"),
            height=400,
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        st.plotly_chart(fig, use_container_width=True)

    # ── チャネル別 ────────────────────────────────────
    if len(channel) > 0:
        st.subheader("チャネル別 セッション")
        col1, col2 = st.columns(2)
        with col1:
            fig = px.pie(channel, names="sessionDefaultChannelGroup", values="sessions", hole=0.4, title="チャネル別セッション比率")
            st.plotly_chart(fig, use_container_width=True)
        with col2:
            fig = px.bar(channel, x="sessionDefaultChannelGroup", y="sessions", text_auto=True, title="チャネル別セッション数")
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)

    # ── デバイス別 ────────────────────────────────────
    if len(device) > 0:
        st.subheader("デバイス別")
        col1, col2 = st.columns(2)
        with col1:
            fig = px.pie(device, names="deviceCategory", values="sessions", hole=0.4, title="デバイス別セッション")
            st.plotly_chart(fig, use_container_width=True)
        with col2:
            fig = px.pie(device, names="deviceCategory", values="purchaseRevenue", hole=0.4, title="デバイス別売上")
            st.plotly_chart(fig, use_container_width=True)

    # ── 参照元/メディア ──────────────────────────────
    if len(source_medium) > 0:
        st.subheader("参照元/メディア TOP 20")
        top_sm = source_medium.head(20)
        fig = px.bar(top_sm, x="sessions", y="sessionSourceMedium", orientation="h", text_auto=True)
        fig.update_layout(height=500, yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig, use_container_width=True)

    # ── ランディングページ ────────────────────────────
    if len(landing) > 0:
        st.subheader("ランディングページ TOP 30")
        st.dataframe(
            landing.rename(columns={
                "landingPagePlusQueryString": "ページ",
                "sessions": "セッション",
                "totalUsers": "ユーザー",
                "ecommercePurchases": "購入",
                "purchaseRevenue": "売上",
            }),
            use_container_width=True,
            height=500,
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EC-CUBE × Shopify比較
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
elif page == "EC-CUBE × Shopify比較":
    st.title("EC-CUBE × Shopify 統合比較")
    st.caption("EC-CUBE時代（2023/8〜2026/2）とShopify移行後のデータを比較します")

    # EC-CUBEデータ
    eccube_sales = load_sales_by_period()

    # Shopifyデータ
    @st.cache_data(ttl=300)
    def cached_shopify_orders_compare():
        try:
            return load_shopify_orders()
        except Exception as e:
            st.error(f"Shopify API接続エラー: {e}")
            return pd.DataFrame()

    with st.spinner("Shopifyデータ取得中..."):
        sp_orders = cached_shopify_orders_compare()

    # ── KPI比較 ───────────────────────────────────────
    st.subheader("KPI比較")

    eccube_total_sales = eccube_sales["購入合計"].sum()
    eccube_total_orders = eccube_sales["購入件数"].sum()
    eccube_days = (eccube_sales["期間"].max() - eccube_sales["期間"].min()).days or 1

    sp_total_sales = sp_orders["合計"].sum() if len(sp_orders) > 0 else 0
    sp_total_orders = len(sp_orders)
    sp_days = (sp_orders["注文日時"].max() - sp_orders["注文日時"].min()).days if len(sp_orders) > 1 else 1

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### EC-CUBE")
        st.metric("総売上", fmt_yen(eccube_total_sales))
        st.metric("総注文数", f"{eccube_total_orders:,.0f}件")
        st.metric("平均日販", fmt_yen(eccube_total_sales / eccube_days))
        st.metric("平均注文額", fmt_yen(eccube_total_sales / eccube_total_orders if eccube_total_orders > 0 else 0))
        st.metric("データ期間", f"{eccube_days}日")
    with col2:
        st.markdown("### Shopify")
        st.metric("総売上", fmt_yen(sp_total_sales))
        st.metric("総注文数", f"{sp_total_orders:,}件")
        st.metric("平均日販", fmt_yen(sp_total_sales / sp_days))
        st.metric("平均注文額", fmt_yen(sp_total_sales / sp_total_orders if sp_total_orders > 0 else 0))
        st.metric("データ期間", f"{sp_days}日")

    # ── 月別売上の統合グラフ ──────────────────────────
    st.subheader("月別売上推移（統合）")

    # EC-CUBE月別
    ec_monthly = eccube_sales.copy()
    ec_monthly["年月"] = ec_monthly["期間"].dt.to_period("M").astype(str)
    ec_monthly_agg = ec_monthly.groupby("年月").agg(売上=("購入合計", "sum")).reset_index()
    ec_monthly_agg["ソース"] = "EC-CUBE"

    # Shopify月別
    if len(sp_orders) > 0:
        sp_orders_copy = sp_orders.copy()
        sp_orders_copy["年月"] = sp_orders_copy["注文日時"].dt.to_period("M").astype(str)
        sp_monthly_agg = sp_orders_copy.groupby("年月").agg(売上=("合計", "sum")).reset_index()
        sp_monthly_agg["ソース"] = "Shopify"
        combined_monthly = pd.concat([ec_monthly_agg, sp_monthly_agg], ignore_index=True)
    else:
        combined_monthly = ec_monthly_agg

    fig = px.bar(combined_monthly, x="年月", y="売上", color="ソース",
                 barmode="group", text_auto=",.0f",
                 color_discrete_map={"EC-CUBE": "#4F46E5", "Shopify": "#10B981"})
    fig.update_layout(height=500, yaxis=dict(tickformat=","))
    st.plotly_chart(fig, use_container_width=True)

    # ── 曜日別比較 ────────────────────────────────────
    st.subheader("曜日別 平均売上比較")
    dow_map = {0: "月", 1: "火", 2: "水", 3: "木", 4: "金", 5: "土", 6: "日"}

    ec_dow = eccube_sales.copy()
    ec_dow["曜日"] = ec_dow["期間"].dt.dayofweek
    ec_dow["曜日名"] = ec_dow["曜日"].map(dow_map)
    ec_dow_agg = ec_dow.groupby(["曜日", "曜日名"]).agg(平均売上=("購入合計", "mean")).reset_index().sort_values("曜日")
    ec_dow_agg["ソース"] = "EC-CUBE"

    if len(sp_orders) > 0:
        sp_dow = sp_orders.copy()
        sp_dow["曜日"] = sp_dow["注文日時"].dt.dayofweek
        sp_dow["曜日名"] = sp_dow["曜日"].map(dow_map)
        sp_dow_agg = sp_dow.groupby(["曜日", "曜日名"]).agg(平均売上=("合計", "mean")).reset_index().sort_values("曜日")
        sp_dow_agg["ソース"] = "Shopify"
        combined_dow = pd.concat([ec_dow_agg, sp_dow_agg], ignore_index=True)
    else:
        combined_dow = ec_dow_agg

    fig = px.bar(combined_dow, x="曜日名", y="平均売上", color="ソース", barmode="group",
                 color_discrete_map={"EC-CUBE": "#4F46E5", "Shopify": "#10B981"})
    fig.update_layout(height=400)
    st.plotly_chart(fig, use_container_width=True)

    # ── 都道府県比較 ──────────────────────────────────
    if len(sp_orders) > 0 and "都道府県" in sp_orders.columns:
        st.subheader("都道府県別 注文数 TOP 15（Shopify）")
        sp_pref = sp_orders["都道府県"].value_counts().head(15).reset_index()
        sp_pref.columns = ["都道府県", "件数"]
        fig = px.bar(sp_pref, x="都道府県", y="件数", text_auto=True, color_discrete_sequence=["#10B981"])
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)
