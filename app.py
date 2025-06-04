import streamlit as st
import requests
from google.transit import gtfs_realtime_pb2
from datetime import datetime
import pandas as pd
import folium
from streamlit_folium import folium_static
import matplotlib.pyplot as plt
from sqlalchemy import create_engine
import psycopg2
from sklearn.cluster import KMeans

# Import des pages
from pages.indicateurs import afficher_indicateurs
from pages.arrets import afficher_carte_des_arrets
from pages.lignes import afficher_lignes
from pages.itineraires import afficher_itineraires
from pages.clustering import afficher_clustering

# CONFIG
URL_GTFS_RT = "https://data.grandpoitiers.fr/data-fair/api/v1/datasets/2gwvlq16siyb7d9m3rqt1pb1/metadata-attachments/poitiers.pbf"

# Connexion à la base de données PostgreSQL
user = "marjoriealbarico"
password = "postgres"
host = "localhost"
port = "5432"
database = "poitiers"
connection_string = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}"
engine = create_engine(connection_string)

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

# Chargement des données consolidées GTFS depuis PostgreSQL
gtfs_full_schedule = pd.read_sql("SELECT * FROM horaires_gtfs_complet", con=engine)

# Recréer stops, trips et routes à partir du DataFrame complet
stops = gtfs_full_schedule[["stop_id", "stop_name", "stop_lat", "stop_lon", "wheelchair_boarding"]].drop_duplicates()
trips = gtfs_full_schedule[["trip_id", "route_id", "trip_headsign", "direction_id"]].drop_duplicates()
routes = gtfs_full_schedule[["route_id", "route_short_name", "route_color"]].drop_duplicates()

# Accessibilité PMR
def label_accessibilite(x):
    if x == 1:
        return "Oui"
    elif x == 0:
        return "Non"
    else:
        return "Non précisé"

stops["accessible_pmr"] = stops["wheelchair_boarding"].apply(label_accessibilite)
accessibilite = st.checkbox("🔓 Mode accessibilité (PMR) uniquement")
if accessibilite:
    stops = stops[stops["accessible_pmr"] == "Oui"]

# Jointure GTFS-RT + GTFS statique
df_trip_updates["trip_id"] = df_trip_updates["trip_id"].astype(str)
df_trip_updates["stop_id"] = df_trip_updates["stop_id"].astype(str)
stops["stop_id"] = stops["stop_id"].astype(str)

df_trip_updates = df_trip_updates.merge(trips[["trip_id", "route_id", "trip_headsign"]], how="left", on="trip_id")
df_trip_updates = df_trip_updates.merge(stops[["stop_id", "stop_name", "stop_lat", "stop_lon", "accessible_pmr"]], how="left", on="stop_id")
df_trip_updates = df_trip_updates.merge(routes[["route_id", "route_short_name", "route_color"]], how="left", on="route_id")

# === Onglets Streamlit ===
onglets = st.tabs(["📊 Accueil", "🗺️ Carte des arrêts", "📍 Itinéraires", "🚌 Lignes et horaires", "📈 Clustering des arrêts"])

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
df_lignes = df_trip_updates.merge(trips[["trip_id", "direction_id"]], how="left", on="trip_id")
with onglets[3]:
    afficher_lignes(df_lignes, URL_GTFS_RT)

# Onglet 4 : Clustering des arrêts
with onglets[4]:
    afficher_clustering(df_trip_updates, stops)
