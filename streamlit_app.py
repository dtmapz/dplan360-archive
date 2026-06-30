import streamlit as st
from utils.ui import inject_base_style

st.set_page_config(page_title="D-PLAN360 ARCHIVE", layout="wide")
inject_base_style()

st.logo("assets/logo.png", size="large")

home_page = st.Page("pages/1_Home.py", title="HOME", icon="🔍", default=True)
milestone_page = st.Page("pages/2_Milestone.py", title="MILESTONE", icon="🗺️")

pg = st.navigation([home_page, milestone_page])
pg.run()