import streamlit as st

from ui.services.api_client import resume_api

st.set_page_config(
    page_title="Candidate Search",
    page_icon="🔎",
    layout="wide",
)

st.title("Candidate Search")
st.caption("Find and evaluate candidates against your hiring requirements.")

# Search form
with st.form("candidate_search_form"):
    query = st.text_area(
        "Job description or search query",
        placeholder=(
            "Example: Accountant profile for mid to senior role. "
            "Looking for candidates with financial reporting, GST, "
            "taxation, and audit experience..."
        ),
        height=180,
    )

    col1, col2 = st.columns([1, 3])

    with col1:
        limit = st.number_input(
            "Maximum results",
            min_value=1,
            max_value=100,
            value=50,
            step=5,
        )

    with col2:
        st.caption(
            "Enter a complete job description or a natural-language "
            "description of the candidate you're looking for."
        )

    submitted = st.form_submit_button(
        "Search candidates",
        type="primary",
        use_container_width=True,
    )

# Execute search
if submitted:
    if not query.strip():
        st.warning("Please enter a job description or search query.")
    else:
        try:
            with st.spinner("Searching and evaluating candidates..."):
                result = resume_api.search_candidates(
                    query=query.strip(),
                    limit=int(limit),
                )

            st.session_state["candidate_search_result"] = result
            st.session_state["candidate_search_query"] = query.strip()

        except Exception as error:
            st.error(f"Candidate search failed: {error}")

# Display results
result = st.session_state.get("candidate_search_result")

if result:
    candidates = result.get("candidates", [])
    search_query = st.session_state.get("candidate_search_query", "")

    st.divider()

    st.subheader("Search results")
    st.caption(f"Query: {search_query}")

    col1, col2 = st.columns(2)

    with col1:
        st.metric("Candidates returned", result.get("total", len(candidates)))

    with col2:
        st.metric("Results displayed", len(candidates))

    if not candidates:
        st.info(
            "No matching candidates found. Try broadening your search "
            "or adjusting the job description."
        )
        st.stop()

    # Sort by AI match score, highest first.
    candidates = sorted(
        candidates,
        key=lambda candidate: candidate.get("match_score") or 0,
        reverse=True,
    )

    for index, candidate in enumerate(candidates, start=1):
        filename = candidate.get("filename", "Unknown resume")
        match_score = candidate.get("match_score")
        semantic_score = candidate.get("semantic_score")

        with st.container(border=True):
            header_col, score_col = st.columns([4, 1])

            with header_col:
                st.markdown(f"### {index}. {filename}")
                st.caption(f"Resume ID: {candidate.get('resume_id', '—')}")

            with score_col:
                if match_score is not None:
                    st.metric("Match score", f"{match_score}/100")
                else:
                    st.metric("Match score", "N/A")

            if semantic_score is not None:
                st.caption(f"Semantic retrieval score: {semantic_score:.4f}")

            summary = candidate.get("summary")
            if summary:
                st.write(summary)

            # Relevant experience
            experience = candidate.get("relevant_experience")
            if experience:
                st.markdown("**Relevant experience**")
                st.write(experience)

            # Skills assessment
            skills = candidate.get("skills", [])

            if skills:
                st.markdown("**Skills assessment**")

                for skill in skills:
                    status = (skill.get("status") or "unknown").lower()

                    if status == "met":
                        icon = "🟢"
                    elif status == "partial":
                        icon = "🟡"
                    elif status == "missing":
                        icon = "🔴"
                    else:
                        icon = "⚪"

                    st.markdown(
                        f"{icon} **{skill.get('requirement', 'Requirement')}** — {status.title()}"
                    )

                    evidence = skill.get("candidate_evidence")
                    if evidence:
                        st.caption(evidence)

            # Strengths and gaps
            strengths_col, gaps_col = st.columns(2)

            with strengths_col:
                st.markdown("**Strengths**")
                strengths = candidate.get("strengths", [])

                if strengths:
                    for strength in strengths:
                        st.markdown(f"- {strength}")
                else:
                    st.caption("No strengths provided.")

            with gaps_col:
                st.markdown("**Gaps**")
                gaps = candidate.get("gaps", [])

                if gaps:
                    for gap in gaps:
                        st.markdown(f"- {gap}")
                else:
                    st.caption("No gaps identified.")

            # Evidence
            evidence = candidate.get("evidence", [])

            if evidence:
                with st.expander("Evaluation evidence"):
                    for item in evidence:
                        st.markdown(f"- {item}")

            # Matched resume chunks
            matched_chunks = candidate.get("matched_chunks", [])

            if matched_chunks:
                with st.expander(f"Matching resume excerpts ({len(matched_chunks)})"):
                    for chunk in matched_chunks:
                        st.markdown(
                            f"**Chunk {chunk.get('chunk_index', 0)}** "
                            f"· Similarity: {chunk.get('score', 0):.4f}"
                        )
                        st.write(chunk.get("text", ""))
                        st.divider()
