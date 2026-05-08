import os
import streamlit as st


DEFAULT_DAILY_REPORT_PASSWORD = "86899157"


def get_daily_report_password() -> str:
    """Return the configured password without exposing it in the UI."""
    env_value = os.getenv("DAILY_REPORT_PASSWORD", "").strip()
    if env_value:
        return env_value

    try:
        secret_value = str(st.secrets.get("daily_report_password", "")).strip()
        if secret_value:
            return secret_value
    except Exception:
        pass

    return DEFAULT_DAILY_REPORT_PASSWORD


def check_daily_report_password(candidate: str) -> bool:
    return str(candidate or "").strip() == get_daily_report_password()
