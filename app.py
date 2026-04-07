"""crewre EC分析ダッシュボード"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import sys
import os
from datetime import date, timedelta

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
from shopify_loader import load_shopify_inventory
from supabase_sync import (
    load_orders_from_supabase,
    load_line_items_from_supabase,
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
    ["売上概要", "在庫・欠品管理", "商品分析（SKU別）", "販促ダッシュボード", "GA4アクセス分析"],
)


def fmt_yen(val):
    """金額を日本円フォーマット（カンマ区切り）"""
    return f"¥{val:,.0f}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ページ1: 売上概要
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
if page == "売上概要":
    st.title("売上概要")

    # EC-CUBEデータ
    ec_sales = load_sales_by_period()

    # Shopifyデータ（Supabaseから）をEC-CUBE形式に変換して統合
    @st.cache_data(ttl=600)
    def get_shopify_daily_sales():
        try:
            sp = load_orders_from_supabase()
            if len(sp) == 0:
                return pd.DataFrame()
            sp = sp[~sp["キャンセル"]].copy()
            if sp["注文日時"].dt.tz is not None:
                sp["注文日時"] = sp["注文日時"].dt.tz_localize(None)
            sp["期間"] = sp["注文日時"].dt.date
            daily = sp.groupby("期間").agg(
                購入件数=("合計", "count"),
                購入合計=("合計", "sum"),
            ).reset_index()
            daily["期間"] = pd.to_datetime(daily["期間"])
            for col in ["男性", "女性", "男性_会員", "男性_非会員", "女性_会員", "女性_非会員", "購入平均"]:
                daily[col] = 0
            daily["購入平均"] = (daily["購入合計"] / daily["購入件数"]).fillna(0)
            return daily
        except Exception:
            return pd.DataFrame()

    sp_daily = get_shopify_daily_sales()

    # EC-CUBE + Shopifyを統合（Shopify移行後データは既に統合済み）
    if len(sp_daily) > 0:
        sales = pd.concat([ec_sales, sp_daily], ignore_index=True)
        sales = sales.groupby("期間").agg({
            "購入件数": "sum", "購入合計": "sum",
            "男性": "sum", "女性": "sum",
            "男性_会員": "sum", "男性_非会員": "sum",
            "女性_会員": "sum", "女性_非会員": "sum",
            "購入平均": "mean",
        }).reset_index().sort_values("期間")
    else:
        sales = ec_sales

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

    # ── 月別予算達成率 ────────────────────────────────
    st.subheader("月別予算達成率")
    st.info("予算設定後に表示")

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
# ページ2: 在庫・欠品管理
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
elif page == "在庫・欠品管理":
    st.title("在庫・欠品管理")

    @st.cache_data(ttl=600)
    def cached_inventory():
        try:
            return load_shopify_inventory()
        except Exception as e:
            st.error(f"在庫データ取得エラー: {e}")
            return pd.DataFrame()

    @st.cache_data(ttl=600)
    def cached_line_items_inv():
        try:
            df = load_line_items_from_supabase()
            return df
        except Exception as e:
            st.error(f"売上データ取得エラー: {e}")
            return pd.DataFrame()

    @st.cache_data
    def load_wishlist():
        path = os.path.join(os.path.dirname(__file__), "data", "top-products.csv")
        if os.path.exists(path):
            return pd.read_csv(path)
        return pd.DataFrame()

    with st.spinner("在庫データ取得中..."):
        inv = cached_inventory()
        line_items = cached_line_items_inv()
        wishlist = load_wishlist()

    if len(inv) == 0:
        st.warning("在庫データが取得できませんでした")
        st.stop()

    # お気に入り数を在庫データに結合
    if len(wishlist) > 0:
        wishlist = wishlist.rename(columns={"Product": "商品名", "Total": "お気に入り数"})
        inv = inv.merge(wishlist[["商品名", "お気に入り数"]], on="商品名", how="left")
        inv["お気に入り数"] = inv["お気に入り数"].fillna(0).astype(int)
    else:
        inv["お気に入り数"] = 0

    # ── KPI ──────────────────────────────────────────
    active_inv = inv[inv["ステータス"] == "active"].copy() if "ステータス" in inv.columns else inv.copy()
    total_stock = active_inv["在庫数"].sum()
    total_stock_value = (active_inv["価格(税込)"] * active_inv["在庫数"]).sum()
    active_skus = (active_inv["在庫数"] > 0).sum()

    k1, k2, k3 = st.columns(3)
    k1.metric("総在庫数", f"{total_stock:,.0f}点")
    k2.metric("在庫金額（上代ベース）", fmt_yen(total_stock_value))
    k3.metric("在庫あり SKU数", f"{active_skus:,}")

    # ── フィルター ────────────────────────────────────
    st.subheader("SKU別在庫テーブル")
    col1, col2, col3 = st.columns(3)
    with col1:
        search_name = st.text_input("商品名で検索", "")
    with col2:
        show_zero = st.checkbox("在庫0のみ表示", value=False)
    with col3:
        show_in_stock = st.checkbox("在庫ありのみ表示", value=False)

    disp_inv = active_inv.copy()
    if search_name:
        disp_inv = disp_inv[disp_inv["商品名"].str.contains(search_name, case=False, na=False)]
    if show_zero:
        disp_inv = disp_inv[disp_inv["在庫数"] == 0]
    elif show_in_stock:
        disp_inv = disp_inv[disp_inv["在庫数"] > 0]

    disp_inv["在庫金額"] = disp_inv["価格(税込)"] * disp_inv["在庫数"]
    disp_table = disp_inv[["商品名", "カラー", "サイズ", "SKU", "価格(税込)", "在庫数", "在庫金額", "お気に入り数"]].copy()
    disp_table["価格(税込)"] = disp_table["価格(税込)"].apply(lambda x: f"¥{x:,.0f}")
    disp_table["在庫金額"] = disp_table["在庫金額"].apply(lambda x: f"¥{x:,.0f}")
    st.dataframe(disp_table, use_container_width=True, height=400)

    # ── 在庫金額 TOP20（商品別） ───────────────────────
    st.subheader("在庫金額 TOP20（商品別）")
    inv_with_value = active_inv.copy()
    inv_with_value["在庫金額"] = inv_with_value["価格(税込)"] * inv_with_value["在庫数"]
    top20_products = (
        inv_with_value.groupby("商品名")["在庫金額"]
        .sum()
        .sort_values(ascending=False)
        .head(20)
        .reset_index()
    )
    fig = px.bar(
        top20_products,
        x="在庫金額",
        y="商品名",
        orientation="h",
        text_auto=",.0f",
        labels={"在庫金額": "在庫金額 (円)"},
    )
    fig.update_layout(height=600, yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig, use_container_width=True)

    # ── 欠品アラート ──────────────────────────────────
    st.subheader("欠品アラート（60日以内に売り切れ予測）")

    if len(line_items) > 0:
        # 日販計算（過去14日）
        try:
            li = line_items[~line_items["キャンセル"]].copy() if "キャンセル" in line_items.columns else line_items.copy()
            if li["注文日時"].dt.tz is not None:
                li["注文日時"] = li["注文日時"].dt.tz_localize(None)
            today = pd.Timestamp.today().normalize()
            since_14 = today - pd.Timedelta(days=14)
            li_14 = li[li["注文日時"] >= since_14]
            if len(li_14) > 0:
                daily_sales = li_14.groupby("SKU").agg(
                    日販合計=("数量", "sum"),
                ).reset_index()
                daily_sales["日販"] = daily_sales["日販合計"] / 14

                # 在庫と結合
                inv_alert = active_inv[active_inv["在庫数"] > 0].copy()
                inv_alert = inv_alert.merge(daily_sales[["SKU", "日販"]], on="SKU", how="left")
                inv_alert["日販"] = inv_alert["日販"].fillna(0)

                # 売り切れ予測日数
                inv_alert["売り切れ予測日数"] = inv_alert.apply(
                    lambda r: r["在庫数"] / r["日販"] if r["日販"] > 0 else 9999,
                    axis=1,
                )
                inv_alert["売り切れ予測日"] = inv_alert.apply(
                    lambda r: (today + pd.Timedelta(days=int(r["売り切れ予測日数"]))).date() if r["売り切れ予測日数"] < 9999 else None,
                    axis=1,
                )

                # 60日以内に売り切れるSKU
                alert_df = inv_alert[inv_alert["売り切れ予測日数"] <= 60].copy()
                alert_df = alert_df.sort_values("売り切れ予測日数")

                if len(alert_df) > 0:
                    st.warning(f"{len(alert_df)} SKUが60日以内に売り切れ予測です")
                    alert_disp = alert_df[["商品名", "カラー", "サイズ", "SKU", "在庫数", "お気に入り数", "日販", "売り切れ予測日数", "売り切れ予測日"]].copy()
                    alert_disp["日販"] = alert_disp["日販"].round(1)
                    alert_disp["売り切れ予測日数"] = alert_disp["売り切れ予測日数"].round(0).astype(int)
                    # 定番商品（販売期間が長い＝多く出ているSKU）は注意喚起
                    high_velocity = alert_disp[alert_disp["日販"] >= 1.0]
                    if len(high_velocity) > 0:
                        st.error(f"特に注意: 日販1点以上の定番商品 {len(high_velocity)} SKUが欠品リスクあり")
                    st.dataframe(alert_disp, use_container_width=True, height=400)
                else:
                    st.success("60日以内に売り切れ予測のSKUはありません")
            else:
                st.info("過去14日の売上データがありません")
        except Exception as e:
            st.error(f"欠品アラート計算エラー: {e}")
    else:
        st.info("売上データが取得できないため、欠品アラートを表示できません")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ページ3: 商品分析（SKU別）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
elif page == "商品分析（SKU別）":
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

    # ── Shopifyデータ（Supabaseから高速読み込み） ──────
    @st.cache_data(ttl=600)
    def cached_shopify_lines():
        try:
            df = load_line_items_from_supabase()
        except Exception:
            return pd.DataFrame()
        if len(df) > 0:
            df = df[~df["キャンセル"]].copy()
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
# ページ4: 販促ダッシュボード
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
elif page == "販促ダッシュボード":
    st.title("販促ダッシュボード")
    st.caption("在庫状況と販売速度から販促優先度を可視化します")

    @st.cache_data(ttl=600)
    def cached_inventory_promo():
        try:
            return load_shopify_inventory()
        except Exception as e:
            st.error(f"在庫データ取得エラー: {e}")
            return pd.DataFrame()

    @st.cache_data(ttl=600)
    def cached_line_items_promo():
        try:
            df = load_line_items_from_supabase()
            return df
        except Exception as e:
            st.error(f"売上データ取得エラー: {e}")
            return pd.DataFrame()

    @st.cache_data
    def load_wishlist_promo():
        path = os.path.join(os.path.dirname(__file__), "data", "top-products.csv")
        if os.path.exists(path):
            return pd.read_csv(path)
        return pd.DataFrame()

    with st.spinner("データ取得中..."):
        inv = cached_inventory_promo()
        line_items = cached_line_items_promo()
        wishlist = load_wishlist_promo()

    if len(inv) == 0:
        st.warning("在庫データが取得できませんでした")
        st.stop()

    # お気に入り数を結合
    if len(wishlist) > 0:
        wl = wishlist.rename(columns={"Product": "商品名", "Total": "お気に入り数"})
        inv = inv.merge(wl[["商品名", "お気に入り数"]], on="商品名", how="left")
        inv["お気に入り数"] = inv["お気に入り数"].fillna(0).astype(int)
    else:
        inv["お気に入り数"] = 0

    # 在庫データ（activeのみ）
    active_inv = inv[inv["ステータス"] == "active"].copy() if "ステータス" in inv.columns else inv.copy()
    active_inv["在庫金額"] = active_inv["価格(税込)"] * active_inv["在庫数"]

    # 日販計算（過去14日）
    daily_sales_sku = pd.DataFrame(columns=["SKU", "日販"])
    today = pd.Timestamp.today().normalize()
    since_14 = today - pd.Timedelta(days=14)

    if len(line_items) > 0:
        try:
            li = line_items[~line_items["キャンセル"]].copy() if "キャンセル" in line_items.columns else line_items.copy()
            if li["注文日時"].dt.tz is not None:
                li["注文日時"] = li["注文日時"].dt.tz_localize(None)
            li_14 = li[li["注文日時"] >= since_14]
            if len(li_14) > 0:
                ds = li_14.groupby("SKU").agg(日販合計=("数量", "sum")).reset_index()
                ds["日販"] = ds["日販合計"] / 14
                daily_sales_sku = ds[["SKU", "日販"]]
        except Exception as e:
            st.error(f"日販計算エラー: {e}")

    # 在庫データと日販を結合
    promo_df = active_inv.merge(daily_sales_sku, on="SKU", how="left")
    promo_df["日販"] = promo_df["日販"].fillna(0)

    # 売り切れ予測日数
    promo_df["売り切れ予測日数"] = promo_df.apply(
        lambda r: r["在庫数"] / r["日販"] if r["日販"] > 0 and r["在庫数"] > 0 else (0 if r["在庫数"] == 0 else 9999),
        axis=1,
    )
    promo_df["売り切れ予測日"] = promo_df.apply(
        lambda r: (today + pd.Timedelta(days=int(min(r["売り切れ予測日数"], 3650)))).date() if r["売り切れ予測日数"] < 9999 else None,
        axis=1,
    )

    # 推定下代（下代データがないため 在庫金額×推定原価率40%で仮計算）
    ESTIMATED_COST_RATIO = 0.40
    promo_df["下代合計（推定）"] = promo_df["在庫金額"] * ESTIMATED_COST_RATIO

    # ゾーン分類
    # - 販促強化: 日販少 & 在庫多
    # - 安定露出: 日販多 & 在庫多
    # - 欠品・追加検討: 日販多 & 在庫少
    median_sales = promo_df["日販"].median()
    median_stock = promo_df["在庫数"].median()

    def classify_zone(row):
        if row["在庫数"] == 0:
            return "在庫なし"
        high_sales = row["日販"] >= median_sales
        high_stock = row["在庫数"] >= median_stock
        if high_sales and high_stock:
            return "安定露出"
        elif not high_sales and high_stock:
            return "販促強化"
        elif high_sales and not high_stock:
            return "欠品・追加検討"
        else:
            return "低優先"

    promo_df["ゾーン"] = promo_df.apply(classify_zone, axis=1)

    # ── KPI ──────────────────────────────────────────
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("分析SKU数", f"{len(promo_df):,}")
    k2.metric("総在庫金額（上代）", fmt_yen(promo_df["在庫金額"].sum()))
    k3.metric("総下代合計（推定）", fmt_yen(promo_df["下代合計（推定）"].sum()))
    k4.metric("販促強化対象SKU", f"{(promo_df['ゾーン'] == '販促強化').sum():,}")

    # ── 散布図 ───────────────────────────────────────
    st.subheader("在庫×日販 散布図（ゾーン分析）")
    st.caption("X=平均日販(過去14日), Y=残在庫数, バブルサイズ=在庫金額")

    zone_colors = {
        "安定露出": "#10B981",
        "販促強化": "#EF4444",
        "欠品・追加検討": "#F59E0B",
        "低優先": "#94A3B8",
        "在庫なし": "#CBD5E1",
    }

    scatter_df = promo_df[promo_df["在庫数"] > 0].copy()
    scatter_df["表示名"] = scatter_df["商品名"].str[:20] + " / " + scatter_df["カラー"] + " / " + scatter_df["サイズ"]
    # バブルサイズの正規化（最小10、最大50）
    if scatter_df["在庫金額"].max() > 0:
        scatter_df["バブルサイズ"] = (scatter_df["在庫金額"] / scatter_df["在庫金額"].max() * 40 + 10).clip(10, 50)
    else:
        scatter_df["バブルサイズ"] = 15

    fig = px.scatter(
        scatter_df,
        x="日販",
        y="在庫数",
        size="バブルサイズ",
        color="ゾーン",
        color_discrete_map=zone_colors,
        hover_name="表示名",
        hover_data={
            "SKU": True,
            "在庫金額": ":.0f",
            "日販": ":.2f",
            "在庫数": True,
            "バブルサイズ": False,
        },
        labels={"日販": "平均日販（過去14日）", "在庫数": "残在庫数"},
        title="販促優先度マップ",
    )

    # 基準線（中央値）を追加
    fig.add_hline(y=median_stock, line_dash="dash", line_color="gray", annotation_text=f"在庫中央値 ({median_stock:.0f}点)")
    fig.add_vline(x=median_sales, line_dash="dash", line_color="gray", annotation_text=f"日販中央値 ({median_sales:.2f})")

    # ゾーンラベル
    fig.add_annotation(x=0, y=scatter_df["在庫数"].max() * 0.95 if len(scatter_df) > 0 else 100,
                       text="販促強化", showarrow=False, font=dict(color="#EF4444", size=14))
    fig.add_annotation(x=scatter_df["日販"].max() * 0.8 if len(scatter_df) > 0 else 1,
                       y=scatter_df["在庫数"].max() * 0.95 if len(scatter_df) > 0 else 100,
                       text="安定露出", showarrow=False, font=dict(color="#10B981", size=14))
    fig.add_annotation(x=scatter_df["日販"].max() * 0.8 if len(scatter_df) > 0 else 1,
                       y=0,
                       text="欠品・追加検討", showarrow=False, font=dict(color="#F59E0B", size=14))

    fig.update_layout(height=600)
    st.plotly_chart(fig, use_container_width=True)

    # ── 販促優先度テーブル ────────────────────────────
    st.subheader("販促優先度テーブル（残在庫多 & 日販少 順）")
    st.caption("残在庫が多く日販が少ない順（= 販促が最も必要なSKU）")

    priority_df = promo_df[promo_df["在庫数"] > 0].copy()
    priority_df = priority_df.sort_values(["在庫金額"], ascending=False)
    priority_df["在庫×日販スコア"] = priority_df.apply(
        lambda r: r["在庫数"] / (r["日販"] + 0.01),
        axis=1,
    )
    priority_df = priority_df.sort_values("在庫×日販スコア", ascending=False)

    disp_priority = priority_df[[
        "商品名", "カラー", "サイズ", "SKU", "在庫数", "お気に入り数", "在庫金額",
        "下代合計（推定）", "日販", "売り切れ予測日数", "売り切れ予測日", "ゾーン"
    ]].copy()
    disp_priority["在庫金額"] = disp_priority["在庫金額"].apply(lambda x: f"¥{x:,.0f}")
    disp_priority["下代合計（推定）"] = disp_priority["下代合計（推定）"].apply(lambda x: f"¥{x:,.0f}")
    disp_priority["日販"] = disp_priority["日販"].round(2)
    disp_priority["売り切れ予測日数"] = disp_priority["売り切れ予測日数"].apply(
        lambda x: f"{int(x)}日" if x < 9999 else "—"
    )

    st.dataframe(disp_priority, use_container_width=True, height=500)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ページ5: GA4アクセス分析
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

    @st.cache_data(ttl=21600)
    def cached_ga4_daily(s, e):
        return load_ga4_daily(s, e)

    @st.cache_data(ttl=21600)
    def cached_ga4_channel(s, e):
        return load_ga4_channel(s, e)

    @st.cache_data(ttl=21600)
    def cached_ga4_source_medium(s, e):
        return load_ga4_source_medium(s, e)

    @st.cache_data(ttl=21600)
    def cached_ga4_device(s, e):
        return load_ga4_device(s, e)

    @st.cache_data(ttl=21600)
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
