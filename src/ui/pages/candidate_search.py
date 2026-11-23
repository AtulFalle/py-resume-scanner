import streamlit as st

from ui.component.candidate_card import render_candidate_card
from ui.services.api_client import resume_api
from ui.styles.helpers import chip, chips


@st.cache_data(ttl=300, show_spinner=False)
def load_categories() -> list[str]:
    return resume_api.list_categories()


st.title("Candidate search")
st.caption("Describe the role you are hiring for. Candidates are retrieved and scored by an LLM.")

try:
    categories = load_categories()
except Exception as error:
    categories = []
    st.error(f"Unable to load categories: {error}")

with st.form("search_form"):
    query = st.text_area(
        "Job description or search query",
        height=140,
        placeholder="Senior Python backend engineer with FastAPI and PostgreSQL, 5+ years",
    )
    with st.expander("Advanced filters"):
        skills_text = st.text_input(
            "Required skills (comma-separated)",
            help="Leave empty to detect skills from the query.",
        )
        selected_categories = st.multiselect("Categories", categories)
        col1, col2 = st.columns(2)
        min_years = col1.number_input(
            "Minimum years of experience",
            min_value=0.0,
            max_value=60.0,
            value=0.0,
            step=0.5,
            help="0 = detect from the query.",
        )
        min_score = col2.slider("Minimum match score", 0, 100, 60)
        limit = st.number_input("Candidates to evaluate", min_value=1, max_value=25, value=10)
        include_unknown = st.checkbox("Include candidates with unknown experience", value=True)
    submitted = st.form_submit_button("Search", type="primary", icon=":material/search:")

if submitted:
    if len(query.strip()) < 3:
        st.warning("Enter at least 3 characters.")
    else:
        skills = [s.strip() for s in skills_text.split(",") if s.strip()]
        try:
            with st.spinner("Searching and evaluating candidates. This can take a few minutes..."):
                st.session_state["search_result"] = resume_api.search_candidates(
                    query=query.strip(),
                    limit=int(limit),
                    min_score=int(min_score),
                    required_skills=skills or None,
                    categories=selected_categories or None,
                    min_years=float(min_years) if min_years > 0 else None,
                    include_unknown_experience=include_unknown,
                )
        except Exception as error:
            st.session_state.pop("search_result", None)
            st.error(f"Search failed: {error}")

result = st.session_state.get("search_result")
if result:
    req = result.get("requirements") or {}
    items = []
    if req.get("role"):
        items.append(chip(f"Role: {req['role']}", "blue"))
    for cat in req.get("categories") or []:
        items.append(chip(cat, "blue"))
    for skill in req.get("required_skills") or []:
        items.append(chip(skill, "green"))
    for skill in req.get("preferred_skills") or []:
        items.append(chip(f"{skill} (preferred)"))
    if req.get("min_years") is not None:
        items.append(chip(f"{req['min_years']:g}+ yrs"))
    if req.get("max_years") is not None:
        items.append(chip(f"up to {req['max_years']:g} yrs"))
    if req.get("location"):
        items.append(chip(req["location"]))
    if items:
        st.markdown("**Interpreted as**")
        st.markdown(chips(items), unsafe_allow_html=True)

    stats = result.get("stats") or {}
    passed = stats.get("passed_filters")
    st.caption(
        f"Passed filters: {passed if passed is not None else 'n/a'} · "
        f"Retrieved: {stats.get('retrieved', 0)} · Evaluated: {stats.get('evaluated', 0)} · "
        f"Hidden below score {stats.get('min_score', 0)}: {stats.get('below_threshold', 0)}"
    )
    if result.get("message"):
        st.info(result["message"])

    for rank, candidate in enumerate(result.get("candidates") or [], start=1):
        render_candidate_card(candidate, rank)
