"""GA4 OAuth認証 - Streamlit Cloud対応"""

import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

SCOPES = ["https://www.googleapis.com/auth/analytics.readonly"]


def get_credentials():
    """認証済みのCredentialsを返す（Streamlit Secrets or ローカルファイル）"""
    creds = None

    # Streamlit Cloud: secretsからトークン情報を読む
    try:
        import streamlit as st
        if "ga4_token" in st.secrets:
            token_info = dict(st.secrets["ga4_token"])
            creds = Credentials.from_authorized_user_info(token_info, SCOPES)
    except Exception:
        pass

    # ローカル: ファイルから読む
    if creds is None:
        token_path = os.path.join(os.path.dirname(__file__), "data", "ga4_token.json")
        if not os.path.exists(token_path):
            token_path = os.path.join(os.path.dirname(__file__), "..", "data", "ga4_token.json")
        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())

    return creds
