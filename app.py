import streamlit as st
import requests
from google.transit import gtfs_realtime_pb2
from datetime import datetime
import pandas as pd
import folium
from streamlit_folium import folium_static
import matplotlib.pyplot as plt
import math
from pages.indicateurs import afficher_indicateurs
from pages.arrets import afficher_carte_des_arrets
from pages.lignes import afficher_lignes


# CONFIG
URL_GTFS_RT = "https://data.grandpoitiers.fr/data-fair/api/v1/datasets/2gwvlq16siyb7d9m3rqt1pb1/metadata-attachments/poitiers.pbf"
GTFS_STATIC_PATH = "donnees_statiques"

@st.cache_data
def charger_flux_gtfs_rt(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.content
    except Exception as e:
        st.error(f"Erreur lors du chargement du flux GTFS-RT : {e}")
        return None

def convertir_timestamp(ts):
    try:
        return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
    except:
        return None

# Chargement du flux GTFS-RT
data = charger_flux_gtfs_rt(URL_GTFS_RT)
if not data:
    st.stop()

# Parsing du flux GTFS-RT
feed = gtfs_realtime_pb2.FeedMessage()
feed.ParseFromString(data)

# Extraction des mises à jour de trajets (trip updates)
trip_updates = []
for entity in feed.entity:
    if entity.HasField("trip_update"):
        trip_id = entity.trip_update.trip.trip_id
        for stu in entity.trip_update.stop_time_update:
            trip_updates.append({
                "trip_id": trip_id,
                "stop_id": stu.stop_id,
                "arrival_time": convertir_timestamp(stu.arrival.time) if stu.HasField('arrival') else None,
                "departure_time": convertir_timestamp(stu.departure.time) if stu.HasField('departure') else None,
                "arrival_delay": stu.arrival.delay if stu.HasField('arrival') else None,
                "departure_delay": stu.departure.delay if stu.HasField('departure') else None
            })

df_trip_updates = pd.DataFrame(trip_updates)

# Chargement des fichiers GTFS statiques
trips = pd.read_csv(f"{GTFS_STATIC_PATH}/trips.txt")
trips.columns = trips.columns.str.strip().str.lower()
trips["trip_id"] = trips["trip_id"].astype(str)

stops = pd.read_csv(f"{GTFS_STATIC_PATH}/stops.txt")
stops.columns = stops.columns.str.strip().str.lower()

routes = pd.read_csv(f"{GTFS_STATIC_PATH}/routes.txt")
routes.columns = routes.columns.str.strip().str.lower()

# Gestion de l'accessibilité PMR
if "wheelchair_boarding" in stops.columns:
    def label_accessibilite(x):
        if x == 1:
            return "Oui"
        elif x == 0:
            return "Non"
        else:
            return "Non précisé"
    stops["accessible_pmr"] = stops["wheelchair_boarding"].apply(label_accessibilite)
else:
    stops["accessible_pmr"] = "Non précisé"

# Filtre accessibilité si coché
accessibilite = st.checkbox("🔓 Mode accessibilité (PMR) uniquement")
if accessibilite:
    stops = stops[stops["accessible_pmr"] == "Oui"]

# Jointure des données temps réel et statiques
df_trip_updates["trip_id"] = df_trip_updates["trip_id"].astype(str)
df_trip_updates["stop_id"] = df_trip_updates["stop_id"].astype(str)
stops["stop_id"] = stops["stop_id"].astype(str)

df_trip_updates = df_trip_updates.merge(trips[["trip_id", "route_id", "trip_headsign"]], how="left", on="trip_id")
df_trip_updates = df_trip_updates.merge(stops[['stop_id', 'stop_name', 'stop_lat', 'stop_lon', 'accessible_pmr']], how='left', on='stop_id')
df_trip_updates = df_trip_updates.merge(routes[["route_id", "route_short_name", "route_color"]], how="left", on="route_id")

# === Onglets Streamlit ===
onglets = st.tabs(["📊 Accueil", "🗺️ Carte des arrêts", "🧭 Itinéraires", "🚌 Lignes et horaires"])

# Onglet 0 : Accueil
with onglets[0]:
    afficher_indicateurs(df_trip_updates)

# Onglet 1 : Carte des arrêts
with onglets[1]:
    afficher_carte_des_arrets(df_trip_updates)

# Onglet 2 : Itinéraires
with onglets[2]:
    # --- Itinéraires directs et correspondance simple ---
    st.subheader("🧝 Itinéraire d'un arrêt à un autre")

    # Sélection des filtres et arrêts
    selected_route_id = st.selectbox("Filtrer par ligne (facultatif)", options=[""] + routes["route_id"].unique().tolist(), index=0)
    available_stops = sorted(df_trip_updates[df_trip_updates["stop_id"].isin(stops["stop_id"])]["stop_name"].dropna().unique().tolist())
    depart = st.selectbox("Départ", options=available_stops)
    arrivee = st.selectbox("Arrivée", options=available_stops)

    # Planification horaire
    planifier = st.checkbox("🗕️ Planifier un horaire de départ")
    heure_min, heure_max = None, None
    if planifier:
        heure_min = st.time_input("Heure souhaitée - début de la plage", value=datetime.now().time())
        heure_max = st.time_input("Heure souhaitée - fin de la plage", value=(datetime.now() + pd.Timedelta(minutes=30)).time())

    voir_prochain = st.button("🔄 Voir prochain passage")

    # Filtrage par ligne si sélectionnée
    df_filtered = df_trip_updates.copy()
    if selected_route_id:
        df_filtered = df_filtered[df_filtered["route_id"] == selected_route_id]

    # --- Itinéraires directs et correspondance simple ---
    possible_trips = df_filtered[df_filtered["stop_name"].isin([depart, arrivee])]
    trip_ids_common = possible_trips["trip_id"].value_counts()[lambda x: x > 1].index.tolist()

    itineraire_directs = []
    for trip_id in trip_ids_common:
        trip_df = df_filtered[df_filtered["trip_id"] == trip_id].reset_index(drop=True)
        try:
            idx_depart = trip_df[trip_df["stop_name"] == depart].index[0]
            idx_arrivee = trip_df[trip_df["stop_name"] == arrivee].index[0]
        except IndexError:
            continue
        if idx_depart < idx_arrivee:
            t1_str = trip_df.loc[idx_depart, "departure_time"]
            try:
                t1_dt = datetime.strptime(t1_str, "%Y-%m-%d %H:%M:%S")
                if t1_dt < datetime.now():
                    continue
                if planifier:
                    t1_time = t1_dt.time()
                    if not (heure_min <= t1_time <= heure_max):
                        continue
            except:
                continue
            segment = trip_df.loc[idx_depart:idx_arrivee]
            itineraire_directs.append({
                "trip_id": trip_id,
                "route_color": f"#{trip_df['route_color'].iloc[0]}",
                "route_name": trip_df["route_short_name"].iloc[0],
                "direction": trip_df["trip_headsign"].iloc[0] if "trip_headsign" in trip_df.columns else "Non précisée",
                "segment": segment
            })

    # Affichage final des itinéraires trouvés
    if itineraire_directs:
        trip_choices = [f"Ligne {it['route_name']} - Direction {it['direction']} (Trip ID: {it['trip_id']})" for it in itineraire_directs]
        idx_selection = st.selectbox("Choisissez un trajet direct", trip_choices)
        it_sel = itineraire_directs[trip_choices.index(idx_selection)]

        def afficher_itineraire_detail(itineraire, depart, arrivee, voir_prochain, title=None):
            if title:
                st.subheader(title)
            trip_id = itineraire["trip_id"].iloc[0]
            route_color = f"#{itineraire['route_color'].iloc[0]}"
            route_name = itineraire["route_short_name"].iloc[0]
            direction = itineraire["trip_headsign"].iloc[0] if "trip_headsign" in itineraire.columns else "Non précisée"
            ligne_html = f"""
            <div style="font-size: 18px; margin-top: 10px;">
                🎨 Ligne à prendre :
                <span style="background-color:{route_color}; color:white; padding:4px 10px; border-radius:6px; margin-left:8px;">
                    {route_name}
                </span><br>
                🧭 Direction : <strong>{direction}</strong><br>
                🚍 Départ : <strong>{depart}</strong>
            </div>
            """
            st.markdown(ligne_html, unsafe_allow_html=True)
            st.success(f"Itinéraire trouvé sur le trajet {trip_id} avec {len(itineraire)} arrêts.")
            st.dataframe(itineraire[["trip_id", "stop_name", "departure_time", "arrival_delay", "accessible_pmr"]])
            lat1, lon1 = itineraire["stop_lat"].iloc[0], itineraire["stop_lon"].iloc[0]
            lat2, lon2 = itineraire["stop_lat"].iloc[-1], itineraire["stop_lon"].iloc[-1]
            R = 6371
            dlat = math.radians(lat2 - lat1)
            dlon = math.radians(lon2 - lon1)
            a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
            distance_km = R * c
            try:
                t_start = datetime.strptime(itineraire["departure_time"].iloc[0], "%Y-%m-%d %H:%M:%S")
                t_end = datetime.strptime(itineraire["departure_time"].iloc[-1], "%Y-%m-%d %H:%M:%S")
                now = datetime.now()
                minutes_to_depart = max((t_start - now).seconds // 60, 0)
                total_minutes_remaining = max((t_end - now).seconds // 60, 0)
                st.info(f"⏱️ Temps total estimé jusqu'à l'arrivée : {total_minutes_remaining} minutes")
                st.info(f"🕑 Heure estimée d'arrivée : {t_end.strftime('%H:%M:%S')}")
                if voir_prochain:
                    retard = itineraire["arrival_delay"].iloc[0] or 0
                    passage_reel = t_start + pd.to_timedelta(retard, unit='s')
                    st.success(f"🕓 Prochain passage estimé : {passage_reel.strftime('%H:%M:%S')}")
                if minutes_to_depart <= 5:
                    st.warning(f"🚨 Le bus part dans moins de {minutes_to_depart} minute(s) ! Dépêchez-vous.")
                else:
                    st.success(f"🕒 Vous avez environ {minutes_to_depart} minute(s) avant le départ.")
            except Exception:
                st.warning("⏱️ Impossible de calculer la durée avec les horaires.")
            walk_speed = 4.5
            bike_speed = 15
            walk_time = round((distance_km / walk_speed) * 60)
            bike_time = round((distance_km / bike_speed) * 60)
            st.info(f"🚶 À pied : ~{walk_time} minutes")
            st.info(f"🚴 À vélo : ~{bike_time} minutes")
            st.subheader("🗺️ Carte de l'itinéraire")
            carte_itineraire = folium.Map(location=[itineraire["stop_lat"].mean(), itineraire["stop_lon"].mean()], zoom_start=13)
            folium.PolyLine(locations=list(zip(itineraire["stop_lat"], itineraire["stop_lon"])), color=route_color, weight=5, opacity=0.8).add_to(carte_itineraire)
            for _, row in itineraire.iterrows():
                color_marker = "blue"
                if row["stop_name"] == depart:
                    color_marker = "green"
                elif row["stop_name"] == arrivee:
                    color_marker = "red"
                folium.Marker(location=[row["stop_lat"], row["stop_lon"]], popup=f"{row['stop_name']}<br>Départ : {row['departure_time']}<br>Accessibilité PMR : {row['accessible_pmr']}", icon=folium.Icon(color=color_marker, icon="bus", prefix="fa")).add_to(carte_itineraire)
            folium_static(carte_itineraire)

        afficher_itineraire_detail(it_sel["segment"], depart, arrivee, voir_prochain)

# Onglet 3 : Lignes et horaires
with onglets[3]:
    afficher_lignes(df_trip_updates)