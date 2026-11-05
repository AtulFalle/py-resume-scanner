
import streamlit as st
from ui.services.api_client import resume_api

MAX_FILE_SIZE_MB = 10
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

st.set_page_config(
    page_title="Resume Ingestion",
    page_icon="📄",
    layout="wide",
)

st.title("Resume Ingestion")
st.caption("Upload and manage resumes in your candidate database.")

# Initialize session state
if "uploaded_resumes" not in st.session_state:
    st.session_state.uploaded_resumes = []

if "uploader_version" not in st.session_state:
    st.session_state.uploader_version = 0

# Upload section
st.subheader("Upload resumes")

st.markdown(
    f"Upload multiple PDF resumes. Maximum file size: **{MAX_FILE_SIZE_MB} MB per file.**"
)

uploaded_files = st.file_uploader(
    "Drag and drop PDF resumes here",
    type=["pdf"],
    accept_multiple_files=True,
    key=f"resume_uploader_{st.session_state.uploader_version}",
    help="Only PDF files are supported.",
)

if uploaded_files:
    valid_files = []
    invalid_files = []

    for file in uploaded_files:
        if file.size == 0:
            invalid_files.append((file.name, "Empty file"))
        elif file.size > MAX_FILE_SIZE_BYTES:
            invalid_files.append((file.name, "File exceeds 10 MB"))
        else:
            valid_files.append(file)

    total_size = sum(file.size for file in valid_files)

    # Summary metrics
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Selected files", len(uploaded_files))

    with col2:
        st.metric("Valid resumes", len(valid_files))

    with col3:
        st.metric("Total size", f"{total_size / (1024 * 1024):.2f} MB")

    # Selected files
    st.divider()
    st.markdown("#### Selected files")

    for file in valid_files:
        col1, col2, col3 = st.columns([5, 2, 1])

        with col1:
            st.write(f"📄 {file.name}")

        with col2:
            st.caption(f"{file.size / 1024:.1f} KB")

        with col3:
            st.success("Valid")

    # Invalid files
    if invalid_files:
        st.markdown("#### Files requiring attention")

        for filename, reason in invalid_files:
            st.error(f"**{filename}** — {reason}")

    # Actions
    col1, col2 = st.columns([3, 1])

    with col1:
        upload_clicked = st.button(
            "Upload resumes",
            type="primary",
            use_container_width=True,
            disabled=not valid_files,
        )

    with col2:
        clear_clicked = st.button(
            "Clear selection",
            use_container_width=True,
        )

    if clear_clicked:
        st.session_state.uploader_version += 1
        st.rerun()

    if upload_clicked:
        progress = st.progress(0)
        uploaded_count = 0
        failed_count = 0

        for index, file in enumerate(valid_files):
            try:
                result = resume_api.upload_resume(
                    filename=file.name,
                    content=file.getvalue(),
                    content_type=file.type or "application/pdf",
                )

                st.session_state.uploaded_resumes.append(
                    {
                        "id": result["id"],
                        "filename": result["name"],
                        "url": result["url"],
                        "size": file.size,
                        "upload_status": "Uploaded",
                        "processing_status": result["status"],
                    }
                )

                uploaded_count += 1

            except Exception as error:
                failed_count += 1
                st.error(f"{file.name}: {error}")

            progress.progress((index + 1) / len(valid_files))

        if uploaded_count:
            st.success(f"{uploaded_count} resume(s) uploaded successfully.")

        if failed_count:
            st.warning(f"{failed_count} resume(s) failed to upload.")

        st.session_state.uploader_version += 1
        st.rerun()

# Upload history
st.divider()
st.subheader("Upload history")

resumes = st.session_state.uploaded_resumes

if not resumes:
    st.info("No resumes uploaded yet.")
else:
    total_uploaded = len(resumes)
    queued = sum(
        resume["processing_status"] == "Queued"
        for resume in resumes
    )

    col1, col2 = st.columns(2)

    with col1:
        st.metric("Uploaded resumes", total_uploaded)

    with col2:
        st.metric("Awaiting processing", queued)

    for resume in reversed(resumes):
        with st.container(border=True):
            col1, col2, col3 = st.columns([4, 2, 2])

            with col1:
                st.markdown(f"**📄 {resume['filename']}**")
                st.caption(f"{resume['size'] / 1024:.1f} KB")

            with col2:
                st.success(resume["upload_status"])

            with col3:
                st.info(resume["processing_status"])
