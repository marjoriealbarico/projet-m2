# library imports
import os
import pandas as pd
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt

# 1. Définition du répertoire de travail
repertoire = r"C:\mastere\M2\projet_etude\data\gtfs"
# 2. Chargement des données
df_stops = pd.read_csv(os.path.join(repertoire, 'stops.txt'), sep=',')
df_routes = pd.read_csv(os.path.join(repertoire, 'routes.txt'), sep=',')
df_trips = pd.read_csv(os.path.join(repertoire, 'trips.txt'), sep=',')
df_stop_times = pd.read_csv(os.path.join(repertoire, 'stop_times.txt'), sep=',')
df_shapes = pd.read_csv(os.path.join(repertoire, 'shapes.txt'), sep=',')
df_calendar = pd.read_csv(os.path.join(repertoire, 'calendar.txt'), sep=',')
df_agency = pd.read_csv(os.path.join(repertoire, 'agency.txt'), sep=',')
df_calendar_dates = pd.read_csv(os.path.join(repertoire, 'calendar_dates.txt'), sep=',')



# Étape 1 : Fusion stop_times + trips
df_merged = df_stop_times.merge(df_trips[['trip_id', 'route_id', 'service_id']], on='trip_id', how='left')

# Étape 2 : Ajout de la route
df_merged = df_merged.merge(df_routes[['route_id', 'route_short_name', 'route_long_name']], on='route_id', how='left')

# Étape 3 : Ajout des arrêts
df_merged = df_merged.merge(df_stops[['stop_id', 'stop_name', 'stop_lat', 'stop_lon']], on='stop_id', how='left')

# Étape 4 : Nettoyage de l’heure
df_merged['arrival_time'] = pd.to_datetime(df_merged['arrival_time'], errors='coerce', format='%H:%M:%S')

# Supprimer les lignes sans heure valide
df_merged = df_merged.dropna(subset=['arrival_time'])
