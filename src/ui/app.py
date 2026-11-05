import streamlit as st

st.set_page_config(
    page_title="Resume Screener",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.sidebar.title("Resume Screener")

st.sidebar.page_link(
    "app.py",
    label="Dashboard",
    icon="🏠",
)

st.sidebar.page_link(
    "pages/resume_upload.py",
    label="Resume Ingestion",
    icon="📄",
)
st.sidebar.page_link(
    "pages/resume_list.py",
    label="candidate List",
    icon="📄",
)

st.sidebar.page_link(
    "pages/candidate_search.py",
    label="candidate Search",
    icon="📄",
)

st.title("Resume Screener")

st.markdown(
    """
    Welcome to your resume screening workspace.

    Upload resumes, monitor processing, and search for candidates
    based on job descriptions.
    """
)

st.info("Select Resume Ingestion from the sidebar to get started.")