import json

import streamlit as st

from ui.services.api_client import resume_api
from ui.styles.helpers import chip, chips, experience_text, status_chip

LINK_LABELS = {"linkedin": "LinkedIn", "github": "GitHub", "website": "Website"}

st.title("Candidate profile")

default_id = st.session_state.get("selected_resume_id", "")
resume_id = st.text_input("Resume ID", value=default_id).strip()

if not resume_id:
    st.info("Select a candidate from search or the library, or paste a resume ID.")
    st.page_link("pages/resume_list.py", label="Go to candidates", icon=":material/groups:")
    st.stop()

st.session_state["selected_resume_id"] = resume_id

try:
    resume = resume_api.get_resume(resume_id)
except Exception as error:
    st.error(f"Unable to load resume: {error}")
    st.stop()

profile = resume.get("profile") or {}
extraction = resume.get("extraction_result") or {}
research = resume.get("research")

name = profile.get("full_name") or extraction.get("full_name") or resume.get("filename")
st.header(name)
meta = [
    profile.get("primary_role"),
    profile.get("category"),
    profile.get("seniority"),
    experience_text(profile.get("total_experience_years"), profile.get("experience_source")),
    profile.get("location"),
]
st.caption(" · ".join(str(m) for m in meta if m))

contact = [
    f"Email: {profile['email']}" if profile.get("email") else None,
    f"Phone: {profile['phone']}" if profile.get("phone") else None,
]
if any(contact):
    st.write(" | ".join(c for c in contact if c))

links = [
    chip(LINK_LABELS.get(link.get("source_type"), "Link"), "blue", link.get("url"))
    for link in profile.get("links") or []
    if link.get("url")
]
if links:
    st.markdown(chips(links), unsafe_allow_html=True)

st.markdown(f"Status: {status_chip(resume.get('status'))}", unsafe_allow_html=True)
if resume.get("error_message"):
    st.error(resume["error_message"])

skills = profile.get("skills") or []
if skills:
    st.markdown("**Skills**")
    st.markdown(chips([chip(s) for s in skills]), unsafe_allow_html=True)
if profile.get("domains"):
    st.markdown("**Domains**")
    st.markdown(chips([chip(d, "blue") for d in profile["domains"]]), unsafe_allow_html=True)
if profile.get("summary"):
    st.markdown("**Summary**")
    st.write(profile["summary"])

# Actions
a1, a2, a3 = st.columns(3)
with a1:
    try:
        pdf = resume_api.get_resume_file(resume_id)
        st.download_button(
            "Download PDF",
            data=pdf,
            file_name=resume.get("filename") or "resume.pdf",
            mime="application/pdf",
            icon=":material/download:",
            width="stretch",
        )
    except Exception as error:
        st.button("Download PDF", disabled=True, width="stretch", help=str(error))
with a2:
    if st.button("Reprocess", icon=":material/refresh:", width="stretch"):
        try:
            resume_api.reprocess_resume(resume_id)
            st.success("Resume queued for reprocessing.")
        except Exception as error:
            st.error(f"Reprocess failed: {error}")
with a3:
    if st.button("Re-run profile research", icon=":material/travel_explore:", width="stretch"):
        try:
            with st.spinner("Researching public profiles..."):
                resume_api.run_research(resume_id)
            st.rerun()
        except Exception as error:
            st.error(f"Research failed: {error}")

st.divider()
left, right = st.columns(2)
with left:
    st.subheader("Work experience")
    jobs = extraction.get("work_experience") or []
    if not jobs:
        st.caption("No work experience extracted.")
    for job in jobs:
        with st.container(border=True):
            st.markdown(f"**{job.get('designation') or 'Role'}** at {job.get('company') or 'n/a'}")
            st.caption(f"{job.get('start_date') or '?'} - {job.get('end_date') or '?'}")
            for item in job.get("responsibilities") or []:
                st.markdown(f"- {item}")
with right:
    st.subheader("Education")
    edu = extraction.get("education") or []
    if not edu:
        st.caption("No education extracted.")
    for entry in edu:
        with st.container(border=True):
            degree = " in ".join(
                p for p in [entry.get("degree"), entry.get("field_of_study")] if p
            )
            st.markdown(f"**{degree or 'Education'}**")
            st.caption(
                " · ".join(
                    str(p) for p in [entry.get("institution"), entry.get("graduation_year")] if p
                )
            )

st.divider()
st.subheader("Public profiles")
if not research:
    st.info("No profile research yet. Use Re-run profile research.")
else:
    st.markdown(f"Research status: {status_chip(research.get('status'))}", unsafe_allow_html=True)
    if research.get("error_message"):
        st.error(research["error_message"])
    report = research.get("report") or {}
    if report.get("summary"):
        st.write(report["summary"])
    for idx, source in enumerate(report.get("sources") or []):
        high = source.get("highlights") or {}
        with st.container(border=True):
            label = LINK_LABELS.get(source.get("source_type"), str(source.get("source_type")))
            st.markdown(
                f"**{label}** {status_chip(source.get('status'))}", unsafe_allow_html=True
            )
            if source.get("url"):
                st.markdown(f"[{source['url']}]({source['url']})")
            if source.get("error"):
                st.caption(f"Reason: {source['error']}")
            kind = source.get("source_type")
            if kind == "github":
                if high.get("bio"):
                    st.write(high["bio"])
                st.caption(
                    f"{high.get('public_repositories', 0)} repos · "
                    f"{high.get('followers', 0)} followers"
                )
                langs = high.get("top_languages") or []
                if langs:
                    st.markdown(
                        chips([chip(str(x if isinstance(x, str) else x)) for x in langs]),
                        unsafe_allow_html=True,
                    )
                for repo in high.get("top_repositories") or []:
                    repo_name = repo.get("name", "repo")
                    line = f"[{repo_name}]({repo['url']})" if repo.get("url") else repo_name
                    extra = " · ".join(
                        str(p)
                        for p in [repo.get("language"), f"{repo.get('stars', 0)} stars"]
                        if p
                    )
                    st.markdown(f"- {line} ({extra}) {repo.get('description') or ''}")
            elif kind == "website":
                if high.get("title"):
                    st.markdown(f"**{high['title']}**")
                if high.get("description"):
                    st.write(high["description"])
                if high.get("excerpt"):
                    st.caption(high["excerpt"])
            elif high.get("excerpt"):
                with st.expander("Excerpt", expanded=False):
                    st.text(high["excerpt"])

st.markdown("**Add LinkedIn profile text**")
st.caption(
    "LinkedIn is not scraped automatically. Open the profile yourself and paste the text here."
)
with st.form("manual_research"):
    manual_url = st.text_input("LinkedIn URL (optional)")
    manual_text = st.text_area("Profile text", height=160)
    if st.form_submit_button("Submit profile text"):
        if not manual_text.strip():
            st.warning("Paste some profile text first.")
        else:
            try:
                resume_api.submit_manual_research(
                    resume_id, text=manual_text.strip(), url=manual_url.strip() or None
                )
                st.rerun()
            except Exception as error:
                st.error(f"Submission failed: {error}")

with st.expander("Raw extraction JSON"):
    st.code(json.dumps(extraction, indent=2, default=str), language="json")
