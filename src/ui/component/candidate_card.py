import html

import streamlit as st

from ui.styles.helpers import chip, chips, experience_text, score_bar, score_tone

LINK_LABELS = {"linkedin": "LinkedIn", "github": "GitHub", "website": "Website"}
SKILL_TONES = {"met": "green", "partial": "amber", "missing": "red"}


def render_candidate_card(candidate: dict, rank: int) -> None:
    rid = str(candidate.get("resume_id", rank))
    key = f"{rank}_{rid}"
    name = candidate.get("full_name") or candidate.get("filename") or "Unnamed candidate"
    score = int(candidate.get("match_score") or 0)

    with st.container(border=True):
        head, badge = st.columns([5, 1])
        with head:
            st.markdown(
                f'<p class="rs-title">#{rank} {html.escape(name)}</p>', unsafe_allow_html=True
            )
            parts = [
                candidate.get("primary_role"),
                candidate.get("category"),
                candidate.get("seniority"),
                experience_text(
                    candidate.get("total_experience_years"), candidate.get("experience_source")
                ),
                candidate.get("location"),
            ]
            st.caption(" · ".join(str(p) for p in parts if p))
            links = [
                chip(LINK_LABELS.get(link.get("source_type"), "Link"), "blue", link.get("url"))
                for link in candidate.get("links") or []
                if link.get("url")
            ]
            if links:
                st.markdown(chips(links), unsafe_allow_html=True)
        with badge:
            st.markdown(
                f'<div style="text-align:right">'
                f"{chip(f'{score}/100', score_tone(score), extra='rs-score')}</div>",
                unsafe_allow_html=True,
            )
        st.markdown(score_bar(score), unsafe_allow_html=True)

        if candidate.get("profession_match") is False:
            st.warning(
                "This candidate's profession does not match the role.",
                icon=":material/warning:",
            )

        if candidate.get("summary"):
            st.write(candidate["summary"])

        skills = sorted(
            candidate.get("skills") or [], key=lambda s: not s.get("required", False)
        )
        if skills:
            st.markdown("**Skills assessment**")
            for skill in skills:
                status = str(skill.get("status", "")).lower()
                label = skill.get("requirement", "")
                if skill.get("required"):
                    label += " (required)"
                line = st.columns([2, 5])
                line[0].markdown(
                    chips([chip(f"{label}: {status}", SKILL_TONES.get(status, "neutral"))]),
                    unsafe_allow_html=True,
                )
                if skill.get("candidate_evidence"):
                    line[1].caption(skill["candidate_evidence"])

        if candidate.get("relevant_experience"):
            st.markdown("**Relevant experience**")
            st.write(candidate["relevant_experience"])

        left, right = st.columns(2)
        with left:
            st.markdown("**Strengths**")
            for item in candidate.get("strengths") or ["None listed"]:
                st.markdown(f"- {item}")
        with right:
            st.markdown("**Gaps**")
            for item in candidate.get("gaps") or ["None listed"]:
                st.markdown(f"- {item}")

        if candidate.get("evidence"):
            with st.expander("Evidence"):
                for item in candidate["evidence"]:
                    st.markdown(f"- {item}")

        chunks = candidate.get("matched_chunks") or []
        if chunks:
            with st.expander(f"Matched resume excerpts ({len(chunks)})"):
                for chunk in chunks:
                    similarity = float(chunk.get("score") or 0) * 100
                    st.caption(
                        f"Excerpt {chunk.get('chunk_index')} · similarity {similarity:.0f}%"
                    )
                    st.text(chunk.get("text", ""))

        if st.button("Open profile", key=f"open_profile_{key}", icon=":material/person:"):
            st.session_state["selected_resume_id"] = rid
            st.switch_page("pages/candidate_profile.py")
