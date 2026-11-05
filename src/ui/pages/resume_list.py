
import streamlit as st

from ui.services.api_client import resume_api


def format_file_size(size: int) -> str:
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"

    return f"{size / (1024 * 1024):.2f} MB"


def format_timestamp(value: str | None) -> str:
    if not value:
        return "—"

    return value.replace("T", " ").replace("Z", " UTC")[:23]


st.set_page_config(
    page_title="Resume Library",
    page_icon="📚",
    layout="wide",
)

st.title("Resume Library")
st.caption("View uploaded resumes and monitor their processing status.")

header_col, refresh_col = st.columns([5, 1])

with refresh_col:
    refresh = st.button("↻ Refresh", use_container_width=True)

try:
    resumes = resume_api.list_resumes()
except Exception as error:
    st.error(f"Unable to load resumes: {error}")
    st.stop()

if not resumes:
    st.info("No resumes found. Upload resumes to get started.")
    st.stop()

# Summary metrics
statuses = [resume.get("status", "unknown") for resume in resumes]

total = len(resumes)
completed = sum(status in {"completed", "embedded"} for status in statuses)
failed = sum(status.endswith("_failed") for status in statuses)
pending = total - completed - failed

col1, col2, col3, col4 = st.columns(4)

col1.metric("Total resumes", total)
col2.metric("Completed", completed)
col3.metric("Processing", pending)
col4.metric("Failed", failed)

st.divider()

# Filters
filter_col, search_col = st.columns([1, 2])

with filter_col:
    selected_status = st.selectbox(
        "Filter by status",
        options=["All"] + sorted(set(statuses)),
    )

with search_col:
    search_term = st.text_input(
        "Search resumes",
        placeholder="Search by filename...",
    )

filtered_resumes = resumes

if selected_status != "All":
    filtered_resumes = [
        resume for resume in filtered_resumes
        if resume.get("status") == selected_status
    ]

if search_term:
    filtered_resumes = [
        resume for resume in filtered_resumes
        if search_term.lower() in resume.get("filename", "").lower()
    ]

st.subheader(f"Resumes ({len(filtered_resumes)})")

if filtered_resumes:
    table_data = [
        {
            "Filename": resume.get("filename", "Unknown"),
            "Status": resume.get("status", "unknown"),
            "Size": format_file_size(resume.get("file_size", 0)),
            "Uploaded": format_timestamp(resume.get("created_at")),
            "Last updated": format_timestamp(resume.get("updated_at")),
        }
        for resume in filtered_resumes
    ]

    st.dataframe(
        table_data,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Filename": st.column_config.TextColumn("Filename"),
            "Status": st.column_config.TextColumn("Processing status"),
            "Size": st.column_config.TextColumn("File size"),
            "Retries": st.column_config.NumberColumn("Retries"),
            "Uploaded": st.column_config.TextColumn("Uploaded"),
            "Last updated": st.column_config.TextColumn("Last updated"),
            "Error": st.column_config.TextColumn("Error"),
        },
    )
else:
    st.info("No resumes match your filters.")

# Resume details
st.divider()
st.subheader("Resume details")

resume_options = {
    f"{resume.get('filename', 'Unknown')} ({resume.get('id', '')[:8]})": resume
    for resume in filtered_resumes
}

if resume_options:
    selected_resume_name = st.selectbox(
        "Select a resume",
        options=list(resume_options.keys()),
    )

    selected_resume = resume_options[selected_resume_name]

    col1, col2 = st.columns(2)

    with col1:
        st.write("**Resume ID**")
        st.code(selected_resume.get("id", ""))

        st.write("**Object name**")
        st.write(selected_resume.get("object_name", "—"))

    with col2:
        st.write("**Content type**")
        st.write(selected_resume.get("content_type", "—"))

        st.write("**Processing error**")
        if selected_resume.get("error_message"):
            st.error(selected_resume["error_message"])
        else:
            st.write("No errors reported.")

    with st.expander("Extraction result"):
        extraction_result = selected_resume.get("extraction_result")

        if extraction_result:
            st.json(extraction_result)
        else:
            st.info("Extraction result is not available yet.")
