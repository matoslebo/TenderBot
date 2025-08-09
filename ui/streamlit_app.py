import os
import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://api:8000")

st.set_page_config(page_title="TenderBot", layout="wide")
st.title("TenderBot Demo")

tabs = st.tabs(["Search", "Q&A", "Alerts (demo)"])

with tabs[0]:
    q = st.text_input("Query", "software")
    k = st.slider("Top K", 1, 10, 5)
    if st.button("Search"):
        r = requests.get(f"{API_URL}/search", params={"q": q, "k": k}, timeout=60)
        data = r.json()
        for hit in data.get("results", []):
            st.markdown(f"**{hit.get('title')}**  ")
            st.write(hit.get("description"))
            cols = st.columns(3)
            cols[0].write(f"Score: {round(hit.get('score', 0), 3)}")
            cols[1].write(f"Deadline: {hit.get('deadline')}")
            cols[2].write(f"[Open]({hit.get('url')})")

with tabs[1]:
    q = st.text_input("Question", "What is the deadline for software services tender?")
    if st.button("Ask"):
        r = requests.post(f"{API_URL}/qa", json={"question": q}, timeout=60)
        data = r.json()
        st.write(data.get("answer"))

with tabs[2]:
    st.info("Alerts not wired to email in demo. Idea: Prefect schedule searches and notify on matches.")
