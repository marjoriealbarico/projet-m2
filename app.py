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
from pages.itineraires import afficher_itineraires

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
    afficher_itineraires(df_trip_updates, stops, routes)

# Onglet 3 : Lignes et horaires
with onglets[3]:
    afficher_lignes(df_trip_updates)
