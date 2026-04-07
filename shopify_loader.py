"""Shopify APIデータ取得モジュール"""

import urllib.request
import json
import os
import time
import pandas as pd

API_VERSION = "2026-04"


def _get_config():
    """ShopifyのSHOPとTOKENを取得"""
    shop = os.getenv("SHOPIFY_SHOP", "")
    token = os.getenv("SHOPIFY_ACCESS_TOKEN", "")
    try:
        import streamlit as st
        shop = st.secrets.get("SHOPIFY_SHOP", shop)
        token = st.secrets.get("SHOPIFY_ACCESS_TOKEN", token)
    except Exception:
        pass
    return shop, token


def _api_request(url, token=None):
    """APIリクエスト（リトライ付き）"""
    if token is None:
        _, token = _get_config()
    req = urllib.request.Request(url, headers={"X-Shopify-Access-Token": token})
    for attempt in range(3):
        try:
            resp = urllib.request.urlopen(req, timeout=30)
            link_header = resp.headers.get("Link", "")
            data = json.loads(resp.read())
            return data, link_header
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))
    return {}, ""


def _api_get(endpoint, params=None):
    """Shopify Admin API GETリクエスト"""
    shop, token = _get_config()
    url = f"https://{shop}/admin/api/{API_VERSION}/{endpoint}"
    if params:
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        url += f"?{qs}"
    return _api_request(url, token)


def _parse_next_url(link_header):
    """LinkヘッダーからnextのURLを取得"""
    if not link_header:
        return None
    for part in link_header.split(","):
        if 'rel="next"' in part:
            url = part.split("<")[1].split(">")[0]
            return url
    return None


def _api_get_url(url):
    """絶対URLでGETリクエスト"""
    return _api_request(url)


def _fetch_all(endpoint, resource_key, params=None):
    """ページネーションで全件取得"""
    shop, token = _get_config()
    if not shop or not token:
        return []
    if params is None:
        params = {}
    params["limit"] = "250"
    all_items = []

    data, link_header = _api_get(endpoint, params)
    all_items.extend(data.get(resource_key, []))

    while True:
        next_url = _parse_next_url(link_header)
        if not next_url:
            break
        time.sleep(0.5)  # レート制限対策
        data, link_header = _api_get_url(next_url)
        all_items.extend(data.get(resource_key, []))

    return all_items


def load_shopify_orders():
    """Shopify全注文データを取得"""
    orders = _fetch_all("orders.json", "orders", {"status": "any"})
    if not orders:
        return pd.DataFrame()

    rows = []
    for o in orders:
        rows.append({
            "注文番号": o.get("name", ""),
            "注文ID": o.get("id"),
            "注文日時": o.get("created_at"),
            "更新日時": o.get("updated_at"),
            "ステータス": o.get("financial_status", ""),
            "フルフィルメント": o.get("fulfillment_status") or "未発送",
            "小計": float(o.get("subtotal_price", 0)),
            "税金": float(o.get("total_tax", 0)),
            "送料": sum(float(s.get("price", 0)) for s in o.get("shipping_lines", [])),
            "値引き": float(o.get("total_discounts", 0)),
            "合計": float(o.get("total_price", 0)),
            "通貨": o.get("currency", "JPY"),
            "支払い方法": ", ".join(o.get("payment_gateway_names", [])),
            "顧客ID": o.get("customer", {}).get("id") if o.get("customer") else None,
            "顧客名": f"{o.get('customer', {}).get('last_name', '')} {o.get('customer', {}).get('first_name', '')}".strip() if o.get("customer") else "",
            "メール": o.get("email", ""),
            "都道府県": o.get("shipping_address", {}).get("province", "") if o.get("shipping_address") else "",
            "商品数": sum(item.get("quantity", 0) for item in o.get("line_items", [])),
            "キャンセル": o.get("cancelled_at") is not None,
            "ソース": "Shopify",
        })

    df = pd.DataFrame(rows)
    df["注文日時"] = pd.to_datetime(df["注文日時"])
    df["更新日時"] = pd.to_datetime(df["更新日時"])
    return df


def load_shopify_line_items():
    """Shopify注文の商品明細（SKU単位）を取得"""
    orders = _fetch_all("orders.json", "orders", {"status": "any"})
    if not orders:
        return pd.DataFrame()

    rows = []
    for o in orders:
        order_date = o.get("created_at")
        cancelled = o.get("cancelled_at") is not None
        for item in o.get("line_items", []):
            rows.append({
                "注文日時": order_date,
                "注文番号": o.get("name", ""),
                "SKU": item.get("sku", ""),
                "商品名": item.get("title", ""),
                "バリアント": item.get("variant_title", ""),
                "単価": float(item.get("price", 0)),
                "数量": int(item.get("quantity", 0)),
                "金額": float(item.get("price", 0)) * int(item.get("quantity", 0)),
                "キャンセル": cancelled,
                "ソース": "Shopify",
            })

    df = pd.DataFrame(rows)
    if len(df) > 0:
        df["注文日時"] = pd.to_datetime(df["注文日時"])
    return df


def load_shopify_customers():
    """Shopify全顧客データを取得"""
    customers = _fetch_all("customers.json", "customers")
    if not customers:
        return pd.DataFrame()

    rows = []
    for c in customers:
        rows.append({
            "顧客ID": c.get("id"),
            "名前": f"{c.get('last_name', '')} {c.get('first_name', '')}".strip(),
            "メール": c.get("email", ""),
            "注文数": c.get("orders_count", 0),
            "購入合計": float(c.get("total_spent", 0)),
            "登録日": c.get("created_at"),
            "更新日": c.get("updated_at"),
            "都道府県": c.get("default_address", {}).get("province", "") if c.get("default_address") else "",
            "タグ": c.get("tags", ""),
            "ソース": "Shopify",
        })

    df = pd.DataFrame(rows)
    df["登録日"] = pd.to_datetime(df["登録日"])
    df["更新日"] = pd.to_datetime(df["更新日"])
    return df


def load_shopify_products():
    """Shopify全商品データを取得"""
    products = _fetch_all("products.json", "products")
    if not products:
        return pd.DataFrame()

    rows = []
    for p in products:
        for v in p.get("variants", []):
            rows.append({
                "商品ID": p.get("id"),
                "商品名": p.get("title", ""),
                "商品タイプ": p.get("product_type", ""),
                "ベンダー": p.get("vendor", ""),
                "タグ": p.get("tags", ""),
                "ステータス": p.get("status", ""),
                "バリアントID": v.get("id"),
                "バリアント名": v.get("title", ""),
                "SKU": v.get("sku", ""),
                "価格": float(v.get("price", 0)),
                "在庫数": v.get("inventory_quantity", 0),
                "作成日": p.get("created_at"),
                "ソース": "Shopify",
            })

    df = pd.DataFrame(rows)
    df["作成日"] = pd.to_datetime(df["作成日"])
    return df


def load_shopify_inventory():
    """Shopify APIから全商品のバリアント別在庫データを取得してDataFrameで返す"""
    products = _fetch_all("products.json", "products")
    if not products:
        return pd.DataFrame()

    rows = []
    for p in products:
        product_name = p.get("title", "")
        product_type = p.get("product_type", "")
        status = p.get("status", "")
        for v in p.get("variants", []):
            variant_title = v.get("title", "")
            # バリアントを / で分割してカラーとサイズを取得
            parts = variant_title.split(" / ", 1)
            color = parts[0].strip() if len(parts) >= 1 else ""
            size = parts[1].strip() if len(parts) >= 2 else ""
            # バリアントが "Default Title" の場合は空にする
            if variant_title in ("Default Title", "デフォルトタイトル"):
                color = ""
                size = ""
            try:
                price = float(v.get("price", 0))
            except (ValueError, TypeError):
                price = 0.0
            # 税込価格（日本は消費税10%）
            price_with_tax = round(price * 1.1)
            inventory_qty = int(v.get("inventory_quantity", 0) or 0)
            rows.append({
                "商品名": product_name,
                "SKU": v.get("sku", ""),
                "バリアント": variant_title,
                "カラー": color,
                "サイズ": size,
                "価格(税込)": price_with_tax,
                "在庫数": inventory_qty,
                "商品タイプ": product_type,
                "ステータス": status,
            })

    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    return df
