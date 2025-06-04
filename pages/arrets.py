import streamlit as st
import folium
from streamlit_folium import folium_static

def afficher_carte_des_arrets(df_trip_updates):
    st.subheader("Carte des arrêts")
    station_recherche = st.text_input("🔎 Rechercher une station (optionnel)").strip().lower()
    m = folium.Map(location=[46.58, 0.34], zoom_start=12)
    grouped = df_trip_updates.dropna(subset=["stop_lat", "stop_lon"]).groupby("stop_name")

    for stop_name, group in grouped:
        if station_recherche and station_recherche not in stop_name.lower():
            continue
        lat = group["stop_lat"].iloc[0]
        lon = group["stop_lon"].iloc[0]
        acces = group["accessible_pmr"].iloc[0]
        #lignes = group[["route_short_name", "route_color"]].dropna().drop_duplicates()
        lignes = group[["route_short_name", "route_color", "trip_headsign", "trip_id"]].dropna().drop_duplicates(subset=["trip_id"])


        html = f"<b>{stop_name}</b><br>Accessibilité PMR : <b>{acces}</b><br><b>Itinéraires :</b><ul>"
        for _, ligne in lignes.iterrows():
            couleur = f"#{ligne['route_color']}"
            trip_stops = df_trip_updates[df_trip_updates["trip_id"] == ligne["trip_id"]].sort_values("departure_time")
            if not trip_stops.empty:
                origine = trip_stops.iloc[0]["stop_name"]
                html += f"<li><span style='background-color:{couleur};color:white;padding:2px 8px;border-radius:4px;'>Ligne {ligne['route_short_name']}</span> {origine} → {ligne['trip_headsign']}</li>"
        html += "</ul>"


        folium.Marker(
            location=[lat, lon],
            popup=folium.Popup(html, max_width=300),
            icon=folium.Icon(color="blue", icon="info-sign")
        ).add_to(m)

    folium_static(m)
