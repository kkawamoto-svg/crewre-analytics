"""Shopify → Supabase 同期モジュール"""

import os
import time
from datetime import datetime, timezone

SUPABASE_URL = "https://qxlfggsepysvsgcgddqv.supabase.co"
SUPABASE_KEY = None  # 実行時に取得


def _get_supabase():
    """Supabaseクライアントを取得"""
    from supabase import create_client
    key = SUPABASE_KEY
    if not key:
        try:
            import streamlit as st
            key = st.secrets.get("SUPABASE_KEY", os.getenv("SUPABASE_KEY", ""))
        except Exception:
            key = os.getenv("SUPABASE_KEY", "")
    return create_client(SUPABASE_URL, key)


def get_last_sync_time():
    """最後に同期した注文の作成日時を取得"""
    sb = _get_supabase()
    result = sb.table("shopify_orders").select("created_at").order("created_at", desc=True).limit(1).execute()
    if result.data:
        return result.data[0]["created_at"]
    return None


def sync_orders_to_supabase(full=False):
    """ShopifyからSupabaseに注文データを同期（差分 or 全件）"""
    from shopify_loader import _fetch_all

    sb = _get_supabase()

    # 差分取得: 最後の同期日時以降の注文だけ取得
    params = {"status": "any"}
    if not full:
        last_sync = get_last_sync_time()
        if last_sync:
            params["created_at_min"] = last_sync
            print(f"差分同期: {last_sync} 以降の注文を取得")

    orders = _fetch_all("orders.json", "orders", params)
    print(f"Shopifyから {len(orders)} 件取得")

    if not orders:
        return 0

    # 注文データをバッチでupsert
    order_rows = []
    line_item_rows = []

    for o in orders:
        order_id = o.get("id")
        order_rows.append({
            "order_id": order_id,
            "order_number": o.get("name", ""),
            "created_at": o.get("created_at"),
            "updated_at": o.get("updated_at"),
            "status": o.get("financial_status", ""),
            "fulfillment": o.get("fulfillment_status") or "未発送",
            "subtotal": float(o.get("subtotal_price", 0)),
            "tax": float(o.get("total_tax", 0)),
            "shipping": sum(float(s.get("price", 0)) for s in o.get("shipping_lines", [])),
            "discount": float(o.get("total_discounts", 0)),
            "total": float(o.get("total_price", 0)),
            "payment": ", ".join(o.get("payment_gateway_names", [])),
            "customer_id": o.get("customer", {}).get("id") if o.get("customer") else None,
            "email": o.get("email", ""),
            "prefecture": o.get("shipping_address", {}).get("province", "") if o.get("shipping_address") else "",
            "item_count": sum(item.get("quantity", 0) for item in o.get("line_items", [])),
            "cancelled": o.get("cancelled_at") is not None,
        })

        for item in o.get("line_items", []):
            line_item_rows.append({
                "order_id": order_id,
                "order_date": o.get("created_at"),
                "order_number": o.get("name", ""),
                "sku": item.get("sku", ""),
                "product_name": item.get("title", ""),
                "variant": item.get("variant_title", ""),
                "price": float(item.get("price", 0)),
                "quantity": int(item.get("quantity", 0)),
                "amount": float(item.get("price", 0)) * int(item.get("quantity", 0)),
                "cancelled": o.get("cancelled_at") is not None,
            })

    # バッチupsert（500件ずつ）
    batch_size = 500
    for i in range(0, len(order_rows), batch_size):
        batch = order_rows[i:i + batch_size]
        sb.table("shopify_orders").upsert(batch, on_conflict="order_id").execute()
        time.sleep(0.2)

    # line_items: 既存のorder_idを削除してから挿入（重複防止）
    order_ids = list(set(r["order_id"] for r in line_item_rows))
    for i in range(0, len(order_ids), 100):
        batch_ids = order_ids[i:i + 100]
        sb.table("shopify_line_items").delete().in_("order_id", batch_ids).execute()
        time.sleep(0.1)

    for i in range(0, len(line_item_rows), batch_size):
        batch = line_item_rows[i:i + batch_size]
        sb.table("shopify_line_items").insert(batch).execute()
        time.sleep(0.2)

    print(f"同期完了: 注文 {len(order_rows)} 件, 明細 {len(line_item_rows)} 件")
    return len(order_rows)


def load_orders_from_supabase():
    """Supabaseから注文データを読み込み"""
    import pandas as pd
    sb = _get_supabase()

    all_data = []
    offset = 0
    while True:
        result = sb.table("shopify_orders").select("*").order("created_at", desc=True).range(offset, offset + 999).execute()
        if not result.data:
            break
        all_data.extend(result.data)
        if len(result.data) < 1000:
            break
        offset += 1000

    if not all_data:
        return pd.DataFrame()

    df = pd.DataFrame(all_data)
    df = df.rename(columns={
        "order_number": "注文番号",
        "created_at": "注文日時",
        "updated_at": "更新日時",
        "status": "ステータス",
        "fulfillment": "フルフィルメント",
        "subtotal": "小計",
        "tax": "税金",
        "shipping": "送料",
        "discount": "値引き",
        "total": "合計",
        "payment": "支払い方法",
        "prefecture": "都道府県",
        "item_count": "商品数",
        "cancelled": "キャンセル",
    })
    df["注文日時"] = pd.to_datetime(df["注文日時"])
    df["更新日時"] = pd.to_datetime(df["更新日時"])
    df["ソース"] = "Shopify"
    return df


def load_line_items_from_supabase():
    """Supabaseから商品明細データを読み込み"""
    import pandas as pd
    sb = _get_supabase()

    all_data = []
    offset = 0
    while True:
        result = sb.table("shopify_line_items").select("*").order("order_date", desc=True).range(offset, offset + 999).execute()
        if not result.data:
            break
        all_data.extend(result.data)
        if len(result.data) < 1000:
            break
        offset += 1000

    if not all_data:
        return pd.DataFrame()

    df = pd.DataFrame(all_data)
    df = df.rename(columns={
        "order_date": "注文日時",
        "order_number": "注文番号",
        "sku": "SKU",
        "product_name": "商品名",
        "variant": "バリアント",
        "price": "単価",
        "quantity": "数量",
        "amount": "金額",
        "cancelled": "キャンセル",
    })
    df["注文日時"] = pd.to_datetime(df["注文日時"])
    df["ソース"] = "Shopify"
    return df


if __name__ == "__main__":
    import sys
    SUPABASE_KEY = sys.argv[1] if len(sys.argv) > 1 else os.getenv("SUPABASE_KEY", "")
    full = "--full" in sys.argv
    print("=== Shopify → Supabase 同期 ===")
    sync_orders_to_supabase(full=full)
