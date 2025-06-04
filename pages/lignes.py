import streamlit as st
import pandas as pd
import folium
from streamlit_folium import folium_static
from google.transit import gtfs_realtime_pb2
import requests
from datetime import datetime, timedelta
import pickle
import numpy as np
from scipy.interpolate import interp1d
import joblib
import warnings
from pandas.errors import PerformanceWarning
warnings.simplefilter(action="ignore", category=PerformanceWarning)

# === Chargement des modèles d'affluence et retard ===
@st.cache_resource
def charger_modeles():
    with open("modeles/affluence_model.pkl", "rb") as f_model:
        modele_affluence = pickle.load(f_model)
    with open("modeles/route_encoder.pkl", "rb") as f_route:
        le_route = pickle.load(f_route)
    with open("modeles/stop_encoder.pkl", "rb") as f_stop:
        le_stop = pickle.load(f_stop)

    modele_retard = joblib.load("modeles/modele_retard.pkl")
    colonnes_modele = pickle.load(open("modeles/colonnes_modele.pkl", "rb"))

    return modele_affluence, le_route, le_stop, modele_retard, colonnes_modele

modele_affluence, le_route, le_stop, modele_retard, colonnes_modele = charger_modeles()

# === Météo (similaire à appV1) ===
@st.cache_data(ttl=300)
def get_meteo():
    API_KEY = "8e5b0ceec624f5c9b6616e5e498367d4"
    LAT, LON = 46.5802, 0.3404
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={LAT}&lon={LON}&units=metric&lang=fr&appid={API_KEY}"
    response = requests.get(url)
    data = response.json()
    return {
        "temperature": data["main"]["temp"],
        "humidity": data["main"]["humidity"],
        "wind_speed": data["wind"]["speed"],
        "weather_main": data["weather"][0]["main"],
        "weather_description": data["weather"][0]["description"],
        "weather_icon": data["weather"][0]["icon"],
        "visibility": data.get("visibility"),
        "clouds": data.get("clouds", {}).get("all"),
        "precipitation": data.get("rain", {}).get('1h', 0.0)
    }

def tag_affluence(val):
    if val == 2:
        return "Élevée 🚨"
    elif val == 1:
        return "Modérée 🔸"
    return "Faible 🟢"

def predire_affluence(df, modele, le_route, le_stop):
    df = df.copy()
    df["departure_hour"] = pd.to_datetime(df["departure_time"], errors="coerce").dt.hour.fillna(0).astype(int)
    df["route_id_enc"] = df["route_id"].map(lambda x: le_route.transform([x])[0] if x in le_route.classes_ else -1)
    df["stop_id_enc"] = df["stop_id"].map(lambda x: le_stop.transform([x])[0] if x in le_stop.classes_ else -1)
    df = df[(df["route_id_enc"] >= 0) & (df["stop_id_enc"] >= 0)]
    if df.empty:
        df["affluence"] = []
        return df
    X = df[["route_id_enc", "stop_id_enc", "departure_hour"]]
    df["affluence"] = modele.predict(X)
    df["niveau_affluence"] = df["affluence"].apply(tag_affluence)
    return df

def predire_retard(df, modele_retard, colonnes_modele, meteo):
    if not hasattr(modele_retard, "predict"):
        st.error("❌ Le modèle de prédiction du retard chargé n'est pas valide (objet de type numpy.ndarray ou autre sans .predict()). Vérifie le fichier 'modele_retard.pkl'.")
        df["Retard estimé"] = "N/A"
        df["Heure estimée"] = "N/A"
        return df

    now = datetime.now()
    jour = now.strftime('%A')

    def prediction(row):
        try:
            heure = pd.to_datetime(row["departure_time"], errors="coerce").hour
        except:
            heure = 0

        donnee = pd.DataFrame([{
            "trip_headsign": row["trip_headsign"],
            "stop_name": row["stop_name"],
            "route_short_name": row["route_short_name"],
            "jour_semaine": jour,
            "heure": heure,
            "stop_lat": row["stop_lat"],
            "stop_lon": row["stop_lon"],
            **meteo,
            "datetime": now
        }])

        X = pd.get_dummies(donnee)
        for col in colonnes_modele:
            if col not in X:
                X[col] = 0
        X = X[colonnes_modele]

        try:
            retard_sec = modele_retard.predict(X)[0]
        except Exception as e:
            st.error(f"Erreur lors de la prédiction : {e}")
            return pd.Series([None, None, None])

        retard_min = int(retard_sec // 60)
        retard_s = int(retard_sec % 60)

        try:
            heure_estimee = (
                datetime.combine(now.date(), pd.to_datetime(row["departure_time"]).time()) + 
                timedelta(seconds=retard_sec)
            ).time()
        except:
            heure_estimee = None

        return pd.Series([retard_min, retard_s, heure_estimee])

    df[["retard_min", "retard_sec", "heure_estimee"]] = df.apply(prediction, axis=1)
    df["Retard estimé"] = df["retard_min"].astype(str) + " min " + df["retard_sec"].astype(str) + " sec"
    df["Heure estimée"] = df["heure_estimee"].astype(str).str.slice(0, 5).str.replace(":", "h")
    return df


def afficher_lignes(df_trip_updates, url_gtfs_rt):
    st.subheader("🚌 Lignes disponibles")
    afficher_alertes(url_gtfs_rt)

    lignes_info = []

    for (route_id, direction_id), group in df_trip_updates.groupby(["route_id", "direction_id"]):
        route_name = group["route_short_name"].iloc[0]
        color = group["route_color"].iloc[0]

        trip_counts = group.groupby("trip_id").size()
        if trip_counts.empty:
            continue
        largest_trip_id = trip_counts.idxmax()
        trip_stops = group[group["trip_id"] == largest_trip_id].dropna(subset=["stop_name", "departure_time"])
        trip_stops = trip_stops.sort_values("departure_time")

        if not trip_stops.empty:
            first_stop = trip_stops["stop_name"].iloc[0]
            last_stop = trip_stops["stop_name"].iloc[-1]
            label = f"Ligne {route_name} : {first_stop} - {last_stop}"
            lignes_info.append({
                "label": label,
                "route_id": route_id,
                "route_short_name": route_name,
                "route_color": color,
                "trip_headsign": group["trip_headsign"].iloc[0],
                "direction_id": direction_id
            })

    lignes_df = pd.DataFrame(lignes_info).sort_values("route_short_name")
    labels = ["Toutes"] + lignes_df["label"].tolist()
    selected_label = st.selectbox("🔍 Choisissez une ligne", labels)

    if selected_label == "Toutes":
        for _, ligne in lignes_df.iterrows():
            _afficher_bandeau_ligne(ligne)
        return

    ligne_data = lignes_df[lignes_df["label"] == selected_label].iloc[0]
    route_id = ligne_data["route_id"]
    direction_id = ligne_data["direction_id"]
    couleur = f"#{ligne_data['route_color']}" if pd.notna(ligne_data["route_color"]) else "#000000"
    _afficher_bandeau_ligne(ligne_data)

    if st.button("📍 Afficher le plan de la ligne sélectionnée"):
        trips_ligne = df_trip_updates[
            (df_trip_updates["route_id"] == route_id) & 
            (df_trip_updates["direction_id"] == direction_id)
        ]

        trip_counts = trips_ligne.groupby("trip_id").size()
        if trip_counts.empty:
            st.warning("Aucun trajet trouvé pour cette ligne.")
            return

        arrets = trips_ligne.dropna(subset=["stop_lat", "stop_lon"]).sort_values("departure_time")
        arrets = predire_affluence(arrets, modele_affluence, le_route, le_stop)
        meteo = get_meteo()
        arrets = predire_retard(arrets, modele_retard, colonnes_modele, meteo)

        st.markdown("### 🧾 Liste des arrêts avec affluence et retard prévus")
        st.dataframe(
            arrets.dropna(subset=["departure_time"])[
                ["stop_name", "departure_time", "accessible_pmr", "niveau_affluence", "Retard estimé", "Heure estimée"]
            ].drop_duplicates(),
            use_container_width=True
        )

        with st.expander("🗺️ Carte de la ligne", expanded=True):
            m = folium.Map(location=[arrets["stop_lat"].mean(), arrets["stop_lon"].mean()], zoom_start=13)

            for trip_id in arrets["trip_id"].unique():
                segment = arrets[arrets["trip_id"] == trip_id].sort_values("departure_time")
                latlons = list(zip(segment["stop_lat"], segment["stop_lon"]))
                for i in range(len(latlons) - 1):
                    folium.PolyLine(latlons[i:i+2], color=couleur, weight=4).add_to(m)

            for _, row in arrets.iterrows():
                folium.Marker(
                    location=[row["stop_lat"], row["stop_lon"]],
                    popup=f"{row['stop_name']}<br>Affluence : {row['niveau_affluence']}<br>PMR : {row['accessible_pmr']}<br>Retard : {row['Retard estimé']}",
                    icon=folium.Icon(color="blue", icon="bus", prefix="fa")
                ).add_to(m)

            folium_static(m)

def _afficher_bandeau_ligne(ligne):
    couleur = f"#{ligne['route_color']}" if pd.notna(ligne['route_color']) else "#000000"
    nom_ligne = ligne["label"]
    html = f"""
    <div style="margin-bottom:10px; padding:10px; border:1px solid #ddd; border-radius:8px;">
        <span style="background-color:{couleur}; color:white; padding:5px 10px; border-radius:5px; font-weight:bold;">
            {nom_ligne}
        </span>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

def convertir_timestamp(ts):
    try:
        return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
    except:
        return "N/A"

def afficher_alertes(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(response.content)

        alertes = []
        for entity in feed.entity:
            if entity.HasField("alert"):
                alert = entity.alert
                header = alert.header_text.translation[0].text if alert.header_text.translation else "Alerte"
                description = alert.description_text.translation[0].text if alert.description_text.translation else ""
                start_time = convertir_timestamp(alert.active_period[0].start) if alert.active_period else "N/A"
                end_time = convertir_timestamp(alert.active_period[0].end) if alert.active_period else "N/A"
                alertes.append({
                    "Titre": header,
                    "Description": description,
                    "Début": start_time,
                    "Fin": end_time
                })

        if alertes:
            st.warning("⚠️ Alertes de service en cours")
            for alerte in alertes:
                with st.expander(f"🚧 {alerte['Titre']}"):
                    st.markdown(f"**Période :** {alerte['Début']} → {alerte['Fin']}")
                    st.markdown(alerte['Description'])
        else:
            st.info("✅ Aucun incident de transport signalé actuellement.")
    except Exception as e:
        st.error(f"Erreur lors du chargement des alertes : {e}")
