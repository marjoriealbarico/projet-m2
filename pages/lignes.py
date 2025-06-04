import streamlit as st
import pandas as pd
import folium
from streamlit_folium import folium_static
from google.transit import gtfs_realtime_pb2
import requests
from datetime import datetime
import pickle
import numpy as np

# === Chargement du modèle d'affluence et encodeurs ===
@st.cache_resource
def charger_modele_et_encodeurs():
    with open("modeles/affluence_model.pkl", "rb") as f_model:
        modele = pickle.load(f_model)
    with open("modeles/route_encoder.pkl", "rb") as f_route:
        le_route = pickle.load(f_route)
    with open("modeles/stop_encoder.pkl", "rb") as f_stop:
        le_stop = pickle.load(f_stop)
    return modele, le_route, le_stop

modele_affluence, le_route, le_stop = charger_modele_et_encodeurs()

# === Utilitaires ===
def convertir_timestamp(ts):
    try:
        return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
    except:
        return "N/A"

def tag_affluence(val):
    if val == 2:
        return "Élevée 🚨"
    elif val == 1:
        return "Modérée 🔸"
    return "Faible 🟢"

def predire_affluence(df, modele, le_route, le_stop):
    df = df.copy()
    df["departure_hour"] = pd.to_datetime(df["departure_time"], errors="coerce").dt.hour.fillna(0).astype(int)

    try:
        df["route_id_enc"] = le_route.transform(df["route_id"].astype(str))
        df["stop_id_enc"] = le_stop.transform(df["stop_id"].astype(str))
    except ValueError:
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

# === Affichage principal ===
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

        #trip_ref = trip_counts.idxmax()
        #arrets = trips_ligne[trips_ligne["trip_id"] == trip_ref].dropna(subset=["stop_lat", "stop_lon"]).sort_values("departure_time")

        arrets = trips_ligne.dropna(subset=["stop_lat", "stop_lon"]).sort_values("departure_time")
        arrets = predire_affluence(arrets, modele_affluence, le_route, le_stop)

        # Agrégation par arrêt : affluence moyenne ou la plus fréquente
        agg_affluence = (
            arrets.groupby(["stop_id", "stop_name", "stop_lat", "stop_lon", "accessible_pmr"])["affluence"]
            .agg(lambda x: round(x.mean()))
            .reset_index()
        )

        agg_affluence["niveau_affluence"] = agg_affluence["affluence"].apply(tag_affluence)


        if arrets.empty:
            st.warning("Pas de coordonnées disponibles pour tracer la ligne.")
            return

        # === Prédiction d’affluence ===
        arrets = predire_affluence(arrets, modele_affluence, le_route, le_stop)

        st.markdown("### 🧾 Liste des arrêts avec affluence prévue")
        st.dataframe(
            arrets.dropna(subset=["departure_time"])[
                ["stop_name", "departure_time", "accessible_pmr", "niveau_affluence"]
            ].drop_duplicates()
        )

        with st.expander("🗺️ Carte de la ligne", expanded=True):
            m = folium.Map(location=[arrets["stop_lat"].mean(), arrets["stop_lon"].mean()], zoom_start=13)
            folium.PolyLine(
                locations=list(zip(arrets["stop_lat"], arrets["stop_lon"])),
                color=couleur,
                weight=5,
                opacity=0.8
            ).add_to(m)

            for _, row in arrets.iterrows():
                folium.Marker(
                    location=[row["stop_lat"], row["stop_lon"]],
                    popup=f"{row['stop_name']}<br>Affluence : {row['niveau_affluence']}<br>PMR : {row['accessible_pmr']}",
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
