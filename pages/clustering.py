import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import folium
from streamlit_folium import folium_static
from sklearn.cluster import KMeans

def afficher_clustering(df_trip_updates, stops):
    st.header("📈 Clustering des arrêts selon l'activité")

    df_freq = df_trip_updates.groupby("stop_id").size().reset_index(name="nb_passages")
    df_freq = df_freq.merge(stops[["stop_id", "stop_name", "stop_lat", "stop_lon"]], on="stop_id", how="left")

    if len(df_freq) >= 3:
        kmeans = KMeans(n_clusters=3, random_state=42)
        df_freq["cluster"] = kmeans.fit_predict(df_freq[["nb_passages"]])

        st.write("### Tableau des arrêts clusterisés")
        st.dataframe(df_freq[["stop_name", "nb_passages", "cluster"]].sort_values(by="nb_passages", ascending=False))

        st.write("### Nombre de passages par arrêt et par cluster")
        fig, ax = plt.subplots()
        for cluster_id in df_freq["cluster"].unique():
            data = df_freq[df_freq["cluster"] == cluster_id]
            ax.scatter(data.index, data["nb_passages"], label=f"Cluster {cluster_id}")
        ax.set_xlabel("Index de l'arrêt")
        ax.set_ylabel("Nombre de passages")
        ax.legend()
        st.pyplot(fig)

        st.write("### Carte interactive des clusters")
        st.markdown("""
        <div style='margin-bottom: 10px;'>
            <strong>Légende des couleurs :</strong><br>
            <span style='color: red;'>●</span> Arrêts très fréquentés (Cluster 0)<br>
            <span style='color: blue;'>●</span> Arrêts moyennement fréquentés (Cluster 1)<br>
            <span style='color: green;'>●</span> Arrêts peu fréquentés (Cluster 2)<br>
        </div>
        """, unsafe_allow_html=True)
        if not df_freq[['stop_lat', 'stop_lon']].isnull().any().any():
            m = folium.Map(location=[df_freq["stop_lat"].mean(), df_freq["stop_lon"].mean()], zoom_start=13)
            colors = ['red', 'blue', 'green', 'purple', 'orange']
            for _, row in df_freq.iterrows():
                folium.CircleMarker(
                    location=[row['stop_lat'], row['stop_lon']],
                    radius=5,
                    popup=f"{row['stop_name']} (Cluster {row['cluster']})",
                    color=colors[row['cluster'] % len(colors)],
                    fill=True,
                    fill_opacity=0.7
                ).add_to(m)
            folium_static(m)
    else:
        st.warning("Pas assez d'arrêts avec des données pour faire un clustering.")
