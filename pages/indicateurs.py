import streamlit as st
import pandas as pd

def afficher_indicateurs(df_trip_updates):
    st.subheader("Indicateurs de performance")

    df_trip_updates["arrival_delay"] = pd.to_numeric(df_trip_updates["arrival_delay"], errors='coerce')
    retard_moyen = df_trip_updates["arrival_delay"].mean()
    retard_max = df_trip_updates["arrival_delay"].max()

    col1, col2 = st.columns(2)
    col1.metric("Retard moyen (sec)", f"{round(retard_moyen, 1)}")
    col2.metric("Retard max (sec)", f"{int(retard_max)}")
