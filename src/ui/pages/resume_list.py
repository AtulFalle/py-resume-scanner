import streamlit as st

from ui.services.api_client import resume_api

PAGE_SIZE = 25
STATUSES = [
    "uploaded",
    "queued",
    "extracting",
    "embedding_queued",
    "embedding",
    "embedded",
    "queue_failed",
    "failed",
    "embedding_failed",
]

st.title("Candidates")
st.caption("Browse uploaded resumes and monitor their processing status.")

try:
    stats = resume_api.get_stats()
except Exception as error:
    st.error(f"Unable to load statistics: {error}")
    stats = None

if stats:
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total", stats["total"])
    m2.metric("Completed", stats["completed"])
    m3.metric("Processing", stats["processing"])
    m4.metric("Failed", stats["failed"])
    category_options = sorted((stats.get("by_category") or {}).keys())
else:
    category_options = []

f1, f2, f3 = st.columns(3)
status = f1.selectbox("Status", ["All", *STATUSES], key="lib_status")
category = f2.selectbox("Category", ["All", *category_options], key="lib_category")
text = f3.text_input("Search name, filename or role", key="lib_q")

a1, a2, _ = st.columns([1, 1, 3])
if a1.button("Retry failed resumes", icon=":material/refresh:"):
    try:
        res = resume_api.reprocess_failed()
        st.success(f"Requeued {res.get('requeued', 0)} resume(s).")
    except Exception as error:
        st.error(f"Retry failed: {error}")
auto = a2.toggle("Auto-refresh (5 s)", key="lib_auto")


@st.fragment(run_every=5 if auto else None)
def table_section() -> None:
    page_count_key = "lib_page"
    page = int(st.session_state.get(page_count_key, 1))
    try:
        data = resume_api.list_resumes(
            offset=(page - 1) * PAGE_SIZE,
            limit=PAGE_SIZE,
            status=None if status == "All" else status,
            category=None if category == "All" else category,
            q=text.strip() or None,
        )
    except Exception as error:
        st.error(f"Unable to load resumes: {error}")
        return

    total = data.get("total", 0)
    items = data.get("items") or []
    pages = max(1, -(-total // PAGE_SIZE))
    if page > pages:
        st.session_state[page_count_key] = 1
        st.rerun(scope="fragment")

    if not items:
        st.info("No resumes match the current filters.")
        return

    rows = [
        {
            "Name": item.get("full_name") or item.get("filename"),
            "Role": item.get("primary_role") or "",
            "Category": item.get("category") or "",
            "Years": item.get("total_experience_years"),
            "Status": (
                "completed" if item.get("status") == "embedded" else item.get("status", "")
            ),
            "Retries": item.get("retry_count", 0),
            "Error": item.get("error_message") or "",
            "Uploaded": str(item.get("created_at", "")).replace("T", " ")[:16],
        }
        for item in items
    ]
    event = st.dataframe(
        rows,
        hide_index=True,
        width="stretch",
        on_select="rerun",
        selection_mode="single-row",
        key="lib_table",
    )
    selected = event.selection.rows if event and event.selection else []

    p1, p2 = st.columns([1, 3])
    p1.number_input("Page", min_value=1, max_value=pages, key=page_count_key)
    p2.caption(f"{total} resumes · page {page} of {pages}")

    if selected:
        item = items[selected[0]]
        if st.button(
            f"Open profile: {rows[selected[0]]['Name']}",
            type="primary",
            icon=":material/person:",
        ):
            st.session_state["selected_resume_id"] = str(item["id"])
            st.switch_page("pages/candidate_profile.py")
    else:
        st.caption("Select a row to open the candidate profile.")


table_section()
