import streamlit as st

from ui.services.api_client import resume_api

st.title("Dashboard")
st.caption("Overview of your candidate database.")

try:
    stats = resume_api.get_stats()
except Exception as error:
    st.error(f"Unable to load statistics: {error}")
    st.stop()

if not stats.get("total"):
    st.info("No resumes yet. Upload some to get started.")
    st.page_link("pages/resume_upload.py", label="Upload resumes", icon=":material/upload_file:")
    st.stop()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total resumes", stats["total"])
c2.metric("Completed", stats["completed"])
c3.metric("Processing", stats["processing"])
c4.metric("Failed", stats["failed"])

left, right = st.columns(2)
with left:
    st.subheader("Candidates by category")
    by_category = stats.get("by_category") or {}
    if by_category:
        st.bar_chart(by_category, horizontal=True, width="stretch")
    else:
        st.caption("No categorized candidates yet.")
with right:
    st.subheader("Status breakdown")
    by_status = stats.get("by_status") or {}
    if by_status:
        st.dataframe(
            [{"status": k.replace("_", " "), "count": v} for k, v in sorted(by_status.items())],
            hide_index=True,
            width="stretch",
        )

st.subheader("Quick links")
l1, l2, l3 = st.columns(3)
l1.page_link("pages/candidate_search.py", label="Candidate search", icon=":material/search:")
l2.page_link("pages/resume_list.py", label="Candidates", icon=":material/groups:")
l3.page_link("pages/resume_upload.py", label="Upload resumes", icon=":material/upload_file:")
