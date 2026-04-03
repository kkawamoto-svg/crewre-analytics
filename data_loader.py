"""EC-CUBE CSVデータ読み込み・前処理モジュール"""

import pandas as pd
import glob
import os

DATA_DIR = os.path.join(os.path.dirname(__file__), "data", "crewre_ECCUBEデータ")


def read_csv_auto(path, **kwargs):
    """Shift_JIS / UTF-8 を自動判定して読み込む"""
    for enc in ["utf-8", "cp932", "shift_jis"]:
        try:
            return pd.read_csv(path, encoding=enc, **kwargs)
        except (UnicodeDecodeError, UnicodeError):
            continue
    raise ValueError(f"読み込みできません: {path}")


# ── 売上集計 ──────────────────────────────────────────

def load_sales_by_period():
    """期間別集計（日別売上）"""
    path = os.path.join(DATA_DIR, "売上集計", "期間別集計", "20230801-20260228.csv")
    df = read_csv_auto(path)
    df.columns = ["期間", "購入件数", "男性", "女性", "男性_会員", "男性_非会員", "女性_会員", "女性_非会員", "購入合計", "購入平均"]
    # 「合計」行など非日付行を除外
    df = df[pd.to_datetime(df["期間"], errors="coerce").notna()].copy()
    df["期間"] = pd.to_datetime(df["期間"])
    for col in df.columns[1:]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    return df


def load_sales_by_product():
    """商品別集計"""
    path = os.path.join(DATA_DIR, "売上集計", "商品別集計", "20230801-20260219.csv")
    df = read_csv_auto(path)
    df.columns = ["SKUコード", "商品名", "購入件数", "数量", "単価", "金額"]
    for col in ["購入件数", "数量", "単価", "金額"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    return df


def load_sales_by_member():
    """会員別集計"""
    path = os.path.join(DATA_DIR, "売上集計", "会員別集計", "20230801-20260219.csv")
    df = read_csv_auto(path)
    df.columns = ["会員", "購入件数", "購入合計", "購入平均"]
    for col in ["購入件数", "購入合計", "購入平均"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    return df


def load_sales_by_age():
    """年代別集計"""
    path = os.path.join(DATA_DIR, "売上集計", "年代別集計", "20230801-20260219.csv")
    df = read_csv_auto(path)
    df.columns = ["年齢", "購入件数", "購入合計", "購入平均"]
    for col in ["購入件数", "購入合計", "購入平均"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    return df


def load_sales_by_occupation():
    """職業別集計"""
    path = os.path.join(DATA_DIR, "売上集計", "職業別集計", "20230801-20260219.csv")
    df = read_csv_auto(path)
    df.columns = ["職業", "購入件数", "購入合計", "購入平均"]
    for col in ["購入件数", "購入合計", "購入平均"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    return df


# ── 受注データ ────────────────────────────────────────

def load_orders():
    """EC-CUBE受注データ（注文単位）"""
    path = os.path.join(DATA_DIR, "受注管理", "受注管理", "order_260219_152647.csv")
    df = read_csv_auto(path)
    # 主要カラムだけ型変換
    if "注文日時" in df.columns:
        df["注文日時"] = pd.to_datetime(df["注文日時"], errors="coerce")
    if "更新日時" in df.columns:
        df["更新日時"] = pd.to_datetime(df["更新日時"], errors="coerce")
    for col in ["小計", "値引き", "送料", "手数料", "税金", "合計", "お支払い合計"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    return df


def load_logizard_orders():
    """Logizard受注データ（商品明細付き、全月分を結合）"""
    pattern = os.path.join(DATA_DIR, "受注管理", "受注管理", "logizard_*.csv")
    files = sorted(glob.glob(pattern))
    dfs = []
    for f in files:
        df = read_csv_auto(f)
        dfs.append(df)
    if not dfs:
        return pd.DataFrame()
    combined = pd.concat(dfs, ignore_index=True)
    if "注文日時" in combined.columns:
        combined["注文日時"] = pd.to_datetime(combined["注文日時"], errors="coerce")
    if "単価" in combined.columns:
        combined["単価"] = pd.to_numeric(combined["単価"], errors="coerce").fillna(0)
    if "個数" in combined.columns:
        combined["個数"] = pd.to_numeric(combined["個数"], errors="coerce").fillna(0)
    if "合計" in combined.columns:
        combined["合計"] = pd.to_numeric(combined["合計"], errors="coerce").fillna(0)
    return combined


# ── 会員データ ────────────────────────────────────────

def load_customers():
    """会員マスター"""
    path = os.path.join(DATA_DIR, "会員管理", "会員マスター", "customer_260219_152505.csv")
    df = read_csv_auto(path)
    if "誕生日" in df.columns:
        df["誕生日"] = pd.to_datetime(df["誕生日"], errors="coerce")
    if "登録日" in df.columns:
        df["登録日"] = pd.to_datetime(df["登録日"], errors="coerce")
    if "初回購入日" in df.columns:
        df["初回購入日"] = pd.to_datetime(df["初回購入日"], errors="coerce")
    if "最終購入日" in df.columns:
        df["最終購入日"] = pd.to_datetime(df["最終購入日"], errors="coerce")
    if "購入回数" in df.columns:
        df["購入回数"] = pd.to_numeric(df["購入回数"], errors="coerce").fillna(0)
    if "お買い上げ合計額" in df.columns:
        df["お買い上げ合計額"] = pd.to_numeric(df["お買い上げ合計額"], errors="coerce").fillna(0)
    return df


# ── 商品データ ────────────────────────────────────────

def load_products():
    """商品マスター"""
    path = os.path.join(DATA_DIR, "商品管理", "商品マスター", "商品CSV.csv")
    df = read_csv_auto(path)
    if "販売価格" in df.columns:
        df["販売価格"] = pd.to_numeric(df["販売価格"], errors="coerce").fillna(0)
    if "在庫数" in df.columns:
        df["在庫数"] = pd.to_numeric(df["在庫数"], errors="coerce").fillna(0)
    return df


def load_categories():
    """カテゴリマスター"""
    path = os.path.join(DATA_DIR, "商品管理", "カテゴリ登録", "category_260224_150355.csv")
    return read_csv_auto(path)
