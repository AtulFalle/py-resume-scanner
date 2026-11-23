import streamlit as st

_CSS = """
<style>
.block-container { padding-top: 2rem; padding-bottom: 3rem; }
.rs-chips { display: flex; flex-wrap: wrap; gap: 0.35rem; margin: 0.2rem 0 0.4rem 0; }
.rs-chip {
    display: inline-block; padding: 0.1rem 0.6rem; border-radius: 999px;
    font-size: 0.78rem; line-height: 1.5; white-space: nowrap;
    border: 1px solid rgba(128, 128, 128, 0.35); background: rgba(128, 128, 128, 0.12);
    color: inherit; text-decoration: none !important;
}
a.rs-chip:hover { background: rgba(128, 128, 128, 0.25); }
.rs-green { background: rgba(34, 170, 90, 0.16); border-color: rgba(34, 170, 90, 0.5); }
.rs-amber { background: rgba(240, 160, 20, 0.18); border-color: rgba(240, 160, 20, 0.55); }
.rs-red { background: rgba(230, 60, 60, 0.16); border-color: rgba(230, 60, 60, 0.5); }
.rs-blue { background: rgba(50, 120, 230, 0.16); border-color: rgba(50, 120, 230, 0.5); }
.rs-score { font-weight: 600; font-size: 0.95rem; padding: 0.15rem 0.8rem; }
.rs-bar {
    width: 100%; height: 8px; border-radius: 999px; overflow: hidden;
    background: rgba(128, 128, 128, 0.22); margin: 0.3rem 0 0.6rem 0;
}
.rs-bar > span { display: block; height: 100%; border-radius: 999px; }
.rs-bar-green > span { background: rgb(34, 170, 90); }
.rs-bar-amber > span { background: rgb(240, 160, 20); }
.rs-bar-red > span { background: rgb(230, 60, 60); }
.rs-muted { opacity: 0.7; font-size: 0.85rem; }
.rs-title { font-size: 1.2rem; font-weight: 600; margin: 0; }
div[data-testid="stMetric"] {
    border: 1px solid rgba(128, 128, 128, 0.3); border-radius: 0.6rem; padding: 0.6rem 0.9rem;
}
</style>
"""


def apply_theme() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)
