import streamlit as st
import pandas as pd
import requests


def afficher_indicateurs(df_trip_updates):
    st.subheader("Indicateurs de performance")

    df_trip_updates["arrival_delay"] = pd.to_numeric(df_trip_updates["arrival_delay"], errors='coerce')
    retard_moyen = df_trip_updates["arrival_delay"].mean()
    retard_max = df_trip_updates["arrival_delay"].max()

    col1, col2 = st.columns(2)
    col1.metric("Retard moyen (sec)", f"{round(retard_moyen, 1)}")
    col2.metric("Retard max (sec)", f"{int(retard_max)}")

    st.subheader("🌤️ Météo actuelle à Poitiers")

    meteo = get_weather_data_open_meteo()
    if "error" in meteo:
        st.error(f"Erreur météo : {meteo['error']}")
    else:
        col3, col4 = st.columns(2)
        col3.metric("Température (°C)", meteo["temperature"])
        col4.metric("Vent (km/h)", meteo["wind_speed"])


def get_weather_data_open_meteo(lat=46.58, lon=0.34):
    url = f"https://api.open-meteo.com/v1/meteofrance?latitude={lat}&longitude={lon}&current_weather=true"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        weather = data["current_weather"]
        return {
            "temperature": weather["temperature"],
            "wind_speed": weather["windspeed"],
            "condition_code": weather["weathercode"]  # optionnel
        }
    except Exception as e:
        return {"error": str(e)}
