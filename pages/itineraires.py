import streamlit as st
import pandas as pd
import folium
from streamlit_folium import folium_static
from datetime import datetime
import math

def afficher_itineraires(df_trip_updates, stops, routes):
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

        walk_time = round((distance_km / 4.5) * 60)
        bike_time = round((distance_km / 15) * 60)
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
            folium.Marker(
                location=[row["stop_lat"], row["stop_lon"]],
                popup=f"{row['stop_name']}<br>Départ : {row['departure_time']}<br>Accessibilité PMR : {row['accessible_pmr']}",
                icon=folium.Icon(color=color_marker, icon="bus", prefix="fa")
            ).add_to(carte_itineraire)
        folium_static(carte_itineraire)

    st.subheader("🧭 Itinéraire d'un arrêt à un autre")

    selected_route_id = st.selectbox("Filtrer par ligne (facultatif)", options=[""] + routes["route_id"].unique().tolist(), index=0)
    available_stops = sorted(df_trip_updates[df_trip_updates["stop_id"].isin(stops["stop_id"])]["stop_name"].dropna().unique().tolist())
    depart = st.selectbox("Départ", options=available_stops)
    arrivee = st.selectbox("Arrivée", options=available_stops)
    planifier = st.checkbox("📅 Planifier un horaire de départ")
    heure_min, heure_max = None, None
    if planifier:
        heure_min = st.time_input("Heure souhaitée - début", value=datetime.now().time())
        heure_max = st.time_input("Heure souhaitée - fin", value=(datetime.now() + pd.Timedelta(minutes=30)).time())
    voir_prochain = st.button("🔄 Voir prochain passage")

    df_filtered = df_trip_updates.copy()
    if selected_route_id:
        df_filtered = df_filtered[df_filtered["route_id"] == selected_route_id]

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

    itineraire_correspondances = []
    if not itineraire_directs:
        trips_depart = df_filtered[df_filtered["stop_name"] == depart]["trip_id"].unique()
        trips_arrivee = df_filtered[df_filtered["stop_name"] == arrivee]["trip_id"].unique()
        df_trips_depart = df_filtered[df_filtered["trip_id"].isin(trips_depart)]
        df_trips_arrivee = df_filtered[df_filtered["trip_id"].isin(trips_arrivee)]
        correspondances = set(df_trips_depart["stop_id"]).intersection(set(df_trips_arrivee["stop_id"]))

        for corr_stop in correspondances:
            for trip_dep in trips_depart:
                trip_dep_stops = df_trips_depart[df_trips_depart["trip_id"] == trip_dep].reset_index(drop=True)
                try:
                    idx_depart = trip_dep_stops[trip_dep_stops["stop_name"] == depart].index[0]
                    idx_corr = trip_dep_stops[trip_dep_stops["stop_id"] == corr_stop].index[0]
                    if idx_corr <= idx_depart:
                        continue
                except:
                    continue

                for trip_arr in trips_arrivee:
                    trip_arr_stops = df_trips_arrivee[df_trips_arrivee["trip_id"] == trip_arr].reset_index(drop=True)
                    try:
                        idx_arrivee = trip_arr_stops[trip_arr_stops["stop_name"] == arrivee].index[0]
                        idx_corr_arr = trip_arr_stops[trip_arr_stops["stop_id"] == corr_stop].index[0]
                        if idx_corr_arr >= idx_arrivee:
                            continue
                    except:
                        continue

                    try:
                        t_depart = datetime.strptime(trip_dep_stops.loc[idx_depart, "departure_time"], "%Y-%m-%d %H:%M:%S")
                        t_corr = datetime.strptime(trip_dep_stops.loc[idx_corr, "departure_time"], "%Y-%m-%d %H:%M:%S")
                        t_corr_arr = datetime.strptime(trip_arr_stops.loc[idx_corr_arr, "departure_time"], "%Y-%m-%d %H:%M:%S")
                        t_arrivee = datetime.strptime(trip_arr_stops.loc[idx_arrivee, "departure_time"], "%Y-%m-%d %H:%M:%S")
                        if t_depart < datetime.now():
                            continue
                        if planifier and not (heure_min <= t_depart.time() <= heure_max):
                            continue
                        if (t_corr_arr - t_corr).total_seconds() < 120:
                            continue
                    except:
                        continue

                    segment1 = trip_dep_stops.loc[idx_depart:idx_corr]
                    segment2 = trip_arr_stops.loc[idx_corr_arr:idx_arrivee]
                    itineraire_correspondances.append({
                        "correspondance_stop": trip_dep_stops.loc[idx_corr, "stop_name"],
                        "trip_dep_id": trip_dep,
                        "route_dep_color": f"#{trip_dep_stops['route_color'].iloc[0]}",
                        "route_dep_name": trip_dep_stops["route_short_name"].iloc[0],
                        "direction_dep": trip_dep_stops["trip_headsign"].iloc[0],
                        "segment1": segment1,
                        "trip_arr_id": trip_arr,
                        "route_arr_color": f"#{trip_arr_stops['route_color'].iloc[0]}",
                        "route_arr_name": trip_arr_stops["route_short_name"].iloc[0],
                        "direction_arr": trip_arr_stops["trip_headsign"].iloc[0],
                        "segment2": segment2,
                        "total_stops": len(segment1) + len(segment2)
                    })

        itineraire_correspondances = sorted(itineraire_correspondances, key=lambda x: x["total_stops"])

    if itineraire_directs or itineraire_correspondances:
        choix = []
        if itineraire_directs:
            choix.append("Itinéraire direct")
        if itineraire_correspondances:
            choix.append("Itinéraire avec correspondance")

        selection = st.selectbox("Choisissez un type d'itinéraire", choix)

        if selection == "Itinéraire direct":
            trip_choices = [f"Ligne {it['route_name']} - Direction {it['direction']} (Trip ID: {it['trip_id']})" for it in itineraire_directs]
            idx_selection = st.selectbox("Choisissez un trajet direct", trip_choices)
            it_sel = itineraire_directs[trip_choices.index(idx_selection)]
            afficher_itineraire_detail(it_sel["segment"], depart, arrivee, voir_prochain)

        elif selection == "Itinéraire avec correspondance":
            correspondance_choices = [
                f"Changer à {it['correspondance_stop']} : Ligne {it['route_dep_name']} → Ligne {it['route_arr_name']} "
                f"(Total arrêts : {it['total_stops']})"
                for it in itineraire_correspondances
            ]
            idx_corr = st.selectbox("Choisissez un itinéraire avec correspondance", correspondance_choices)
            it_corr = itineraire_correspondances[correspondance_choices.index(idx_corr)]
            afficher_itineraire_detail(it_corr["segment1"], depart, it_corr['correspondance_stop'], voir_prochain, title="Segment 1 - Premier bus")
            st.markdown(f"**Correspondance à l'arrêt : {it_corr['correspondance_stop']}**")
            afficher_itineraire_detail(it_corr["segment2"], it_corr['correspondance_stop'], arrivee, voir_prochain, title="Segment 2 - Deuxième bus")
    else:
        st.error("Aucun trajet à venir ne correspond à vos critères horaires entre ces deux arrêts.")
