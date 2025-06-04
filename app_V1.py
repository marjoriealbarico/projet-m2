import streamlit as st
import pandas as pd
import joblib
import requests
import psycopg2
from datetime import datetime, timedelta

# --- Chargement du modèle et colonnes ---
@st.cache_resource
def load_model():
    model = joblib.load("modele_retard.pkl")
    colonnes = joblib.load("colonnes_modele.pkl")
    return model, colonnes

model, colonnes_modele = load_model()

# --- Connexion à la base de données ---
@st.cache_resource
def get_conn():
    return psycopg2.connect(
        host="localhost",
        dbname="gfts_db",
        user="postgres",
        password="testdata",
        port=5432
    )

conn = get_conn()

# --- Chargement des fichiers GTFS ---
@st.cache_data
def charger_gtfs():
    try:
        routes = pd.read_csv("routes.txt", dtype=str)
        trips = pd.read_csv("trips.txt", dtype=str)
        stops = pd.read_csv("stops.txt", dtype=str)
        stop_times = pd.read_csv("stop_times.txt", dtype=str)
        return routes, trips, stops, stop_times
    except Exception as e:
        st.error(f"Erreur lors du chargement des fichiers GTFS : {e}")
        return None, None, None, None

routes, trips, stops, stop_times = charger_gtfs()

def get_arrets_avec_horaires(trip_id):
    stop_info = (
        stop_times[stop_times["trip_id"] == trip_id]
        .merge(stops, on="stop_id")
        .sort_values("stop_sequence")
    )
    stop_info["arrival_time"] = pd.to_datetime(stop_info["arrival_time"], format="%H:%M:%S", errors="coerce").dt.time
    return stop_info[["stop_name", "arrival_time", "stop_lat", "stop_lon"]]

# --- Météo (avec cache) ---
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

# --- Fonction manquante ajoutée ici ---
def predict_retard(ligne, direction, stop_name, stop_lat, stop_lon, meteo):
    now = datetime.now()
    jour = now.strftime('%A')
    heure = now.hour

    donnee = pd.DataFrame([{
        "trip_headsign": direction,
        "stop_name": stop_name,
        "route_short_name": ligne,
        "jour_semaine": jour,
        "heure": heure,
        "stop_lat": stop_lat,
        "stop_lon": stop_lon,
        **meteo,
        "datetime": now
    }])

    X = pd.get_dummies(donnee)
    for col in colonnes_modele:
        if col not in X:
            X[col] = 0
    X = X[colonnes_modele]

    return model.predict(X)[0]

# --- Prédiction pour un itinéraire complet ---
def tableau_itineraire_complet(trip_id, ligne, direction):
    meteo = get_meteo()
    now = datetime.now()
    jour = now.strftime('%A')

    stop_info = get_arrets_avec_horaires(trip_id)
    tableau = []

    for _, row in stop_info.iterrows():
        stop_name = row["stop_name"]
        stop_lat = float(row["stop_lat"])
        stop_lon = float(row["stop_lon"])
        arrival_time = row["arrival_time"]

        if arrival_time is None:
            continue

        donnee = pd.DataFrame([{
            "trip_headsign": direction,
            "stop_name": stop_name,
            "route_short_name": ligne,
            "jour_semaine": jour,
            "heure": arrival_time.hour,
            "stop_lat": stop_lat,
            "stop_lon": stop_lon,
            **meteo,
            "datetime": datetime.combine(now.date(), arrival_time)
        }])

        X = pd.get_dummies(donnee)
        for col in colonnes_modele:
            if col not in X:
                X[col] = 0
        X = X[colonnes_modele]

        retard_sec = model.predict(X)[0]
        retard_minutes = int(retard_sec // 60)
        retard_secondes = int(retard_sec % 60)
        heure_estimee = (datetime.combine(now.date(), arrival_time) + timedelta(seconds=retard_sec)).time()

        tableau.append({
            "Arrêt": stop_name,
            "Heure théorique": arrival_time.strftime("%Hh%M"),
            "Retard estimé": f"{retard_minutes} min {retard_secondes} sec",
            "Heure estimée": heure_estimee.strftime("%Hh%M")
        })

    return pd.DataFrame(tableau)

# --- Récupération prochaine heure théorique ---
def get_prochaine_arrivee(conn, ligne, direction, arret, heure_actuelle):
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT arrival_time
                FROM horaires_gtfs_complet
                WHERE route_short_name = %s
                AND trip_headsign = %s
                AND stop_name = %s
                AND arrival_time >= %s
                ORDER BY arrival_time ASC
                LIMIT 1
            """, (ligne, direction, arret, heure_actuelle))
            result = cur.fetchone()
            return result[0] if result else None
    except Exception as e:
        st.error(f"Erreur SQL : {e}")
        return None

# --- Affichage principal ---
st.title("🚍 Prédiction de retard de bus")

# --- Sélections utilisateur ---
if routes is not None:
    lignes = [""] + sorted(routes["route_short_name"].unique())
    ligne_choisie = st.selectbox("Ligne de bus", lignes)

    if ligne_choisie:
        route_id = routes[routes["route_short_name"] == ligne_choisie]["route_id"].values[0]
        trips_ligne = trips[trips["route_id"] == route_id]

        directions = [""] + sorted(trips_ligne["trip_headsign"].unique())
        direction_choisie = st.selectbox("Direction", directions)

        if direction_choisie:
            trip_id = trips_ligne[trips_ligne["trip_headsign"] == direction_choisie].iloc[0]["trip_id"]
            stop_ids = stop_times[stop_times["trip_id"] == trip_id].sort_values("stop_sequence")["stop_id"]
            stops_filtered = stops[stops["stop_id"].isin(stop_ids)]

            arrets = [""] + sorted(stops_filtered["stop_name"].unique())
            arret_choisi = st.selectbox("Arrêt", arrets)

            if arret_choisi:
                lat, lon = stops_filtered[stops_filtered["stop_name"] == arret_choisi][["stop_lat", "stop_lon"]].iloc[0].astype(float)

                heure_now = datetime.now().strftime("%H:%M:%S")
                heure_theorique = get_prochaine_arrivee(conn, ligne_choisie, direction_choisie, arret_choisi, heure_now)

                if heure_theorique:
                    st.success(f"🕓 Heure théorique d'arrivée : **{heure_theorique.strftime('%Hh%M')}**")

                    meteo = get_meteo()
                    with st.spinner("⏳ Prédiction en cours..."):
                        retard_sec = predict_retard(ligne_choisie, direction_choisie, arret_choisi, lat, lon, meteo)

                    minutes = int(retard_sec // 60)
                    secondes = int(retard_sec % 60)
                    st.success(f"🕒 Retard estimé : **{minutes} min {secondes} sec**")

                    heure_estimee = (datetime.combine(datetime.today(), heure_theorique) + timedelta(seconds=retard_sec)).time()
                    st.info(f"🕕 Heure estimée d'arrivée réelle : **{heure_estimee.strftime('%Hh%M')}**")

                    # Affichage météo
                    st.subheader("🌦️ Météo actuelle")
                    col1, col2 = st.columns([1, 3])
                    with col1:
                        st.image(f"http://openweathermap.org/img/wn/{meteo['weather_icon']}@2x.png", width=80)
                    with col2:
                        st.markdown(f"**{meteo['weather_main']}** – {meteo['weather_description'].capitalize()}")
                        st.markdown(f"🌡️ Température : {meteo['temperature']} °C")
                        st.markdown(f"💧 Humidité : {meteo['humidity']} %")
                        st.markdown(f"💨 Vent : {meteo['wind_speed']} m/s")
                else:
                    st.warning("❗ Aucune heure théorique disponible à venir pour cet arrêt.")

# --- Affichage de l'itinéraire complet ---
if ligne_choisie and direction_choisie:
    st.subheader("🛣️ Détail complet de l'itinéraire avec prédictions")

    trips_direction = trips[(trips["route_id"] == route_id) & (trips["trip_headsign"] == direction_choisie)]
    if not trips_direction.empty:
        trip_id_exemple = trips_direction.iloc[0]["trip_id"]

        with st.spinner("📊 Génération du tableau des retards..."):
            df_itineraire = tableau_itineraire_complet(trip_id_exemple, ligne_choisie, direction_choisie)

        st.dataframe(df_itineraire, use_container_width=True)
