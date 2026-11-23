import sys
from pathlib import Path

# Make `from ui...` imports work when launched as `streamlit run src/ui/app.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

from ui.styles.theme import apply_theme  # noqa: E402

st.set_page_config(
    page_title="Resume Screener",
    page_icon=":material/description:",
    layout="wide",
    initial_sidebar_state="expanded",
)

apply_theme()

navigation = st.navigation(
    [
        st.Page("pages/dashboard.py", title="Dashboard", icon=":material/dashboard:", default=True),
        st.Page(
            "pages/candidate_search.py", title="Candidate search", icon=":material/search:"
        ),
        st.Page("pages/resume_list.py", title="Candidates", icon=":material/groups:"),
        st.Page(
            "pages/candidate_profile.py",
            title="Candidate profile",
            icon=":material/person:",
        ),
        st.Page(
            "pages/resume_upload.py", title="Upload resumes", icon=":material/upload_file:"
        ),
    ]
)
navigation.run()
