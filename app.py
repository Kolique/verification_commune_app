import streamlit as st
import pandas as pd
from opencage.geocoder import OpenCageGeocode
# Nous avons besoin de geopy.distance pour calculer la distance entre les points
from geopy.distance import great_circle
import time # Gardons time au cas où pour des délais entre les requêtes si nécessaire

# --- Configuration de l'application Streamlit ---
st.set_page_config(
    page_title="Vérificateur de Correspondance Coordonnées-Commune (Distance)",
    page_icon="🗺️",
    layout="wide"
)

st.title("🗺️ Vérificateur de Correspondance Coordonnées-Commune (Basé sur la Distance)")
st.markdown("""
Cette application vous permet d'identifier les points GPS qui sont **significativement éloignés** de leur commune attendue.
Nous allons calculer la distance entre votre point GPS et le centre géocodé de la commune que vous avez fournie.
""")

st.warning("⚠️ **Important :** Ce service utilise OpenCage Geocoding API. Il offre de bonnes performances, mais n'oubliez pas que les plans gratuits ont des limites de requêtes (généralement 2500 requêtes par jour). Au-delà, le service peut devenir payant ou bloqué jusqu'au jour suivant. Une requête est faite pour chaque commune unique pour obtenir son centre.")

# --- Initialisation du géocodeur OpenCage ---
# C'EST ICI QUE VOUS METTREZ VOTRE CLÉ API
# Pour un déploiement sécurisé sur Streamlit Cloud, utilisez st.secrets (voir doc Streamlit).
# Exemple: API_KEY = st.secrets["OPENCAGE_API_KEY"]
# Pour un test local, vous pouvez décommenter la ligne ci-dessous et mettre votre clé directement,
# mais NE PAS FAIRE CELA POUR UN DÉPLOIEMENT PUBLIC.
try:
    API_KEY = st.secrets["OPENCAGE_API_KEY"]
except:
    st.error("Clé API OpenCage introuvable. Veuillez configurer `OPENCAGE_API_KEY` dans `st.secrets` ou la définir directement dans le code pour le test.")
    st.stop() # Arrête l'exécution de l'application si la clé n'est pas trouvée

geocoder = OpenCageGeocode(API_KEY)

# Dictionnaire pour stocker les centroïdes de communes déjà géocodées
# Cela évitera de faire plusieurs requêtes pour la même commune
commune_centroids = {}

# Fonction pour obtenir les coordonnées du centre d'une commune (géocodage direct)
@st.cache_data(show_spinner=False) # Cache pour éviter de refaire des requêtes pour la même commune
def get_commune_centroid(commune_name):
    """
    Obtient les coordonnées (latitude, longitude) du centre d'une commune via OpenCage.
    Met en cache les résultats pour éviter des requêtes répétées.
    """
    if commune_name in commune_centroids:
        return commune_centroids[commune_name]

    try:
        # Utilise le géocodeur OpenCage pour le géocodage direct
        results = geocoder.geocode(f"{commune_name}, France", language='fr') # Ajoutez "France" pour améliorer la précision
        if results and len(results) > 0:
            coords = (results[0]['geometry']['lat'], results[0]['geometry']['lng'])
            commune_centroids[commune_name] = coords
            return coords
        return None
    except Exception as e:
        st.warning(f"Impossible de géocoder le centre de '{commune_name}'. Erreur: {e}")
        return None

# --- Section de téléchargement de fichier ---
st.header("1. Téléchargez votre fichier CSV")
uploaded_file = st.file_uploader("Choisissez un fichier CSV", type="csv")

if uploaded_file is not None:
    st.success("Fichier CSV téléchargé avec succès !")
    # Lecture du fichier CSV
    try:
        df = pd.read_csv(uploaded_file, delimiter=';')
        st.subheader("Aperçu de votre fichier (les 5 premières lignes) :")
        st.dataframe(df.head())

        # Vérification des colonnes requises
        required_columns = ['latitude', 'longitude', 'commune']
        if not all(col in df.columns for col in required_columns):
            st.error(f"Le fichier CSV doit contenir les colonnes suivantes : `{', '.join(required_columns)}`")
            st.info("Vérifiez l'orthographe exacte des en-têtes de colonnes (minuscules) ou le séparateur de votre fichier (doit être ';').")
        else:
            st.header("2. Lancement de la vérification basée sur la distance")
            st.info("Pré-traitement des communes uniques pour obtenir leurs centres...")

            # Récupérer tous les noms de communes uniques pour les géocoder
            unique_communes = df['commune'].unique()
            geocoded_unique_communes_count = 0
            with st.spinner(f"Géocodage des {len(unique_communes)} communes uniques..."):
                for i, commune in enumerate(unique_communes):
                    get_commune_centroid(str(commune)) # Assurez-vous que c'est une chaîne
                    geocoded_unique_communes_count = len(commune_centroids)
                    # Mettre un petit délai pour les API gratuites (Nominatim par exemple)
                    # Pour OpenCage, c'est moins critique car ils gèrent mieux les QPS,
                    # mais peut être utile si vous avez un très grand nombre de requêtes uniques.
                    # time.sleep(0.05)
                st.success(f"Centroïdes pour {geocoded_unique_communes_count} communes uniques récupérés.")


            st.info("Traitement de chaque point GPS pour calculer la distance au centre de sa commune attendue. Cela peut prendre un certain temps pour 6000 lignes. 🚀")

            # Slider pour le seuil de distance
            DISTANCE_THRESHOLD_KM = st.slider(
                "Seuil de distance (km) : Un point est erroné si > à ce seuil du centre de sa commune attendue",
                min_value=0.1, max_value=50.0, value=2.0, step=0.1,
                help="Ajustez ce seuil pour définir ce que vous considérez comme une 'erreur'. Les points situés à une distance supérieure seront marqués."
            )

            # Initialisation des listes pour stocker les résultats
            results = []
            progress_bar = st.progress(0)
            total_rows = len(df)

            # Application de la fonction de vérification à chaque ligne
            for index, row in df.iterrows():
                lat = row['latitude']
                lon = row['longitude']
                commune_attendue = str(row['commune']) # Assurez-vous que la commune est une chaîne de caractères

                # Obtenir les coordonnées du centre de la commune (déjà cachées si unique)
                centroid_coords = get_commune_centroid(commune_attendue)

                distance = None
                is_out_of_threshold = False
                error_message = None

                if centroid_coords:
                    try:
                        point_coords = (lat, lon)
                        distance = great_circle(point_coords, centroid_coords).km
                        if distance > DISTANCE_THRESHOLD_KM:
                            is_out_of_threshold = True
                            error_message = f"Distance ({distance:.2f} km) supérieure au seuil ({DISTANCE_THRESHOLD_KM} km)."
                        else:
                             error_message = f"Distance ({distance:.2f} km) inférieure ou égale au seuil ({DISTANCE_THRESHOLD_KM} km)."

                    except Exception as e:
                        error_message = f"Erreur de calcul de distance : {e}"
                        is_out_of_threshold = True # Marquer comme erreur si calcul impossible
                else:
                    error_message = f"Impossible de trouver le centre de la commune '{commune_attendue}'."
                    is_out_of_threshold = True # Marquer comme erreur si le centre n'est pas trouvé


                results.append({
                    'latitude': lat,
                    'longitude': lon,
                    'commune_attendue': commune_attendue,
                    'commune_centre_lat': centroid_coords[0] if centroid_coords else None,
                    'commune_centre_lon': centroid_coords[1] if centroid_coords else None,
                    'distance_au_centre_km': distance,
                    'est_hors_seuil': is_out_of_threshold,
                    'message_detail': error_message
                })
                # Mise à jour de la barre de progression
                progress_bar.progress((index + 1) / total_rows)
            
            results_df = pd.DataFrame(results)

            st.subheader("3. Résultats de la vérification")

            # Affichage des lignes avec des non-correspondances (maintenant 'est_hors_seuil' True)
            false_matches_df = results_df[results_df['est_hors_seuil'] == True]

            if not false_matches_df.empty:
                st.error(f"🚨 **{len(false_matches_df)} point(s) identifié(s) comme potentiellement erroné(s)** (distance > {DISTANCE_THRESHOLD_KM} km ou problème de géocodage) :")
                st.dataframe(false_matches_df[[
                    'latitude', 'longitude', 'commune_attendue', 'distance_au_centre_km', 'message_detail'
                ]])

                # Option de téléchargement des erreurs
                st.download_button(
                    label="Télécharger les points erronés (distance) en CSV",
                    data=false_matches_df.to_csv(index=False, sep=';', encoding='utf-8').encode('utf-8'),
                    file_name="points_errones_distance.csv",
                    mime="text/csv",
                    help="Cliquez pour télécharger un fichier CSV contenant toutes les lignes où le point GPS est trop éloigné du centre de la commune attendue ou dont le centre n'a pas pu être géocodé."
                )
            else:
                st.success(f"🎉 Tous les points sont à moins de {DISTANCE_THRESHOLD_KM} km du centre de leur commune attendue ou n'ont pas rencontré de problème de géocodage. Aucune anomalie majeure détectée.")

            # Option d'afficher toutes les vérifications (pour le debug/visualisation complète)
            if st.checkbox("Afficher toutes les vérifications (y compris ceux dans le seuil)"):
                st.subheader("Toutes les vérifications :")
                st.dataframe(results_df)

    except Exception as e:
        st.error(f"Une erreur est survenue lors de la lecture ou du traitement de votre fichier CSV : {e}")
        st.info("Veuillez vous assurer que votre fichier est bien un CSV valide et contient les colonnes 'latitude', 'longitude' et 'commune'. Assurez-vous également que les colonnes sont séparées par des points-virgules ';'.")

st.markdown("---")
st.markdown("Développé avec ❤️ par votre Partenaire de code.")
