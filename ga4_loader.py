"""GA4データ取得モジュール"""

import pandas as pd
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    RunReportRequest, DateRange, Dimension, Metric, OrderBy,
)
from ga4_auth import get_credentials

PROPERTY_ID = "402817978"


def _run_report(dimensions, metrics, start_date="2023-08-01", end_date="today", order_by=None, limit=0):
    """GA4レポートを実行してDataFrameで返す"""
    creds = get_credentials()
    client = BetaAnalyticsDataClient(credentials=creds)

    dim_objs = [Dimension(name=d) for d in dimensions]
    met_objs = [Metric(name=m) for m in metrics]

    kwargs = dict(
        property=f"properties/{PROPERTY_ID}",
        dimensions=dim_objs,
        metrics=met_objs,
        date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
    )
    if order_by:
        kwargs["order_bys"] = order_by
    if limit:
        kwargs["limit"] = limit

    request = RunReportRequest(**kwargs)
    response = client.run_report(request)

    rows = []
    for row in response.rows:
        r = {}
        for i, dim in enumerate(dimensions):
            r[dim] = row.dimension_values[i].value
        for i, met in enumerate(metrics):
            r[met] = row.metric_values[i].value
        rows.append(r)

    df = pd.DataFrame(rows)
    # 数値カラムを変換
    for m in metrics:
        if m in df.columns:
            df[m] = pd.to_numeric(df[m], errors="coerce").fillna(0)
    return df


def load_ga4_daily(start_date="2023-08-01", end_date="today"):
    """日別のセッション・ユーザー・PV・コンバージョンデータ"""
    df = _run_report(
        dimensions=["date"],
        metrics=["sessions", "totalUsers", "newUsers", "screenPageViews",
                 "ecommercePurchases", "purchaseRevenue", "conversions"],
        start_date=start_date,
        end_date=end_date,
    )
    if len(df) > 0:
        df["date"] = pd.to_datetime(df["date"], format="%Y%m%d")
        df = df.sort_values("date")
    return df


def load_ga4_channel(start_date="2023-08-01", end_date="today"):
    """チャネル別（流入元別）データ"""
    df = _run_report(
        dimensions=["sessionDefaultChannelGroup"],
        metrics=["sessions", "totalUsers", "ecommercePurchases", "purchaseRevenue"],
        start_date=start_date,
        end_date=end_date,
    )
    return df.sort_values("sessions", ascending=False) if len(df) > 0 else df


def load_ga4_source_medium(start_date="2023-08-01", end_date="today"):
    """参照元/メディア別データ"""
    df = _run_report(
        dimensions=["sessionSourceMedium"],
        metrics=["sessions", "totalUsers", "ecommercePurchases", "purchaseRevenue"],
        start_date=start_date,
        end_date=end_date,
    )
    return df.sort_values("sessions", ascending=False) if len(df) > 0 else df


def load_ga4_device(start_date="2023-08-01", end_date="today"):
    """デバイス別データ"""
    df = _run_report(
        dimensions=["deviceCategory"],
        metrics=["sessions", "totalUsers", "ecommercePurchases", "purchaseRevenue"],
        start_date=start_date,
        end_date=end_date,
    )
    return df


def load_ga4_landing_page(start_date="2023-08-01", end_date="today", limit=30):
    """ランディングページTOP"""
    df = _run_report(
        dimensions=["landingPagePlusQueryString"],
        metrics=["sessions", "totalUsers", "ecommercePurchases", "purchaseRevenue"],
        start_date=start_date,
        end_date=end_date,
        order_by=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="sessions"), desc=True)],
        limit=limit,
    )
    return df
