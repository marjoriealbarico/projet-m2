import streamlit as st
import pandas as pd
import folium
from streamlit_folium import folium_static

def afficher_lignes(df_trip_updates):
    st.subheader("🚌 Lignes disponibles")
    lignes = df_trip_updates[["route_short_name", "route_color", "trip_headsign", "route_id"]].drop_duplicates()
    lignes = lignes.sort_values(by="route_short_name")

    selected_ligne = st.selectbox("🔍 Choisissez une ligne", ["Toutes"] + lignes["route_short_name"].dropna().unique().tolist())
    
    if selected_ligne == "Toutes":
        for _, ligne in lignes.iterrows():
            _afficher_bandeau_ligne(ligne)
        return

    # Détails de la ligne sélectionnée
    ligne_data = lignes[lignes["route_short_name"] == selected_ligne].iloc[0]
    route_id = ligne_data["route_id"]
    couleur = f"#{ligne_data['route_color']}" if pd.notna(ligne_data["route_color"]) else "#000000"
    direction = ligne_data["trip_headsign"]
    _afficher_bandeau_ligne(ligne_data)

    if st.button("📍 Afficher le plan de la ligne sélectionnée"):
        # Filtrage des trajets de cette ligne
        trips_ligne = df_trip_updates[df_trip_updates["route_id"] == route_id]

        # Choisir le trip avec le plus d'arrêts
        trip_counts = trips_ligne.groupby("trip_id").size()
        if trip_counts.empty:
            st.warning("Aucun trajet trouvé pour cette ligne.")
            return

        trip_ref = trip_counts.idxmax()
        arrets = trips_ligne[trips_ligne["trip_id"] == trip_ref].dropna(subset=["stop_lat", "stop_lon"]).sort_values("departure_time")

        if arrets.empty:
            st.warning("Pas de coordonnées disponibles pour tracer la ligne.")
            return

        st.markdown("### 🧾 Liste des arrêts")
        st.dataframe(arrets[["stop_name", "departure_time", "accessible_pmr"]].drop_duplicates())

        with st.expander("🗺️ Carte de la ligne", expanded=True):
            m = folium.Map(location=[arrets["stop_lat"].mean(), arrets["stop_lon"].mean()], zoom_start=13)

            # Tracé de la ligne
            folium.PolyLine(
                locations=list(zip(arrets["stop_lat"], arrets["stop_lon"])),
                color=couleur,
                weight=5,
                opacity=0.8
            ).add_to(m)

            # Marqueurs
            for _, row in arrets.iterrows():
                folium.Marker(
                    location=[row["stop_lat"], row["stop_lon"]],
                    popup=f"{row['stop_name']}<br>PMR : {row['accessible_pmr']}",
                    icon=folium.Icon(color="blue", icon="bus", prefix="fa")
                ).add_to(m)

            folium_static(m)

def _afficher_bandeau_ligne(ligne):
    couleur = f"#{ligne['route_color']}" if pd.notna(ligne['route_color']) else "#000000"
    nom_ligne = ligne["route_short_name"]
    direction = ligne["trip_headsign"]
    html = f"""
    <div style="margin-bottom:10px; padding:10px; border:1px solid #ddd; border-radius:8px;">
        <span style="background-color:{couleur}; color:white; padding:5px 10px; border-radius:5px; font-weight:bold;">
            {nom_ligne}
        </span> ➜ <strong>{direction}</strong>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)
