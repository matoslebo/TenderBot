import streamlit as st
from app.llm.embeddings import embed_query
from app.search.qdrant_client import search as q_search
from app.rag.qa import simple_rag
from dotenv import load_dotenv
load_dotenv()

st.set_page_config(page_title="TenderSense MVP", layout="wide")
st.title("TenderSense – MVP")
tab1, tab2 = st.tabs(["🔎 Semantické vyhľadávanie", "RAG Q&A"])
with tab1:
    query = st.text_input("Zadaj dopyt (napr. 'kybernetický audit ISO 27001'):")
    top_k = st.slider("Počet výsledkov", 1, 10, 5)
    if st.button("Hľadať") and query:
        q_emb = embed_query(query)
        hits = q_search(q_emb, top_k=top_k)
        for h in hits:
            st.markdown(f"**{h.get('title','(bez názvu)')}**  \nSkóre: {h['score']:.3f}")
            if h.get("url"):
                st.markdown(f"[Otvoriť]({h['url']})")
            st.write(h.get("snippet",""))
with tab2:
    question = st.text_input("Otázka (napr. 'Aké sú požiadavky z NIS2?')")
    top_k_q = st.slider("Kontextových pasáží", 1, 8, 4, key="qtopk")
    if st.button("Spýtať sa") and question:
        res = simple_rag(question, top_k=top_k_q)
        st.subheader("Odpoveď")
        st.write(res["answer"])
        if res.get("references"):
            st.subheader("Referencie")
            for r in res["references"]:
                st.markdown(f"- {r}")
