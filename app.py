import streamlit as st
import pandas as pd
# Importation de OpenCageGeocode à la place de Nominatim
from opencage.geocoder import OpenCageGeocode
# Plus besoin de RateLimiter avec un service qui gère mieux les requêtes
# from geopy.extra.rate_limiter import RateLimiter 
import time

# --- Configuration de l'application Streamlit ---
st.set_page_config(
    page_title="Vérificateur de Correspondance Coordonnées-Commune (Rapide)",
    page_icon="⚡",
    layout="wide"
)

st.title("⚡ Vérificateur de Correspondance Coordonnées-Commune (Rapide)")
st.markdown("""
Cette application vous permet de vérifier la correspondance entre les coordonnées géographiques (latitude, longitude)
et la commune associée dans votre fichier CSV, **avec une vitesse améliorée grâce à OpenCage Geocoding API**.
""")

st.warning("⚠️ **Important :** Ce service utilise OpenCage Geocoding API. Il offre des performances bien supérieures à Nominatim, mais n'oubliez pas que les plans gratuits ont des limites de requêtes (généralement 2500 requêtes par jour). Au-delà, le service peut devenir payant ou bloqué jusqu'au jour suivant.")

# --- Initialisation du géocodeur OpenCage ---
# C'EST ICI QUE NOUS UTILISONS TA CLÉ API
# Pour le test et le code, la clé est ici. Pour le déploiement sur Streamlit Cloud,
# nous utiliserons une méthode plus sécurisée (voir instructions après le code).
API_KEY = st.secrets["OPENCAGE_API_KEY"]
geocoder = OpenCageGeocode(API_KEY)

# --- Fonction de vérification des coordonnées (adaptée pour OpenCage) ---
@st.cache_data
def verify_coordinates_opencage(latitude, longitude, expected_commune):
    """
    Vérifie si les coordonnées correspondent à la commune attendue en utilisant OpenCage.
    Retourne un tuple (correspondance_ok, commune_trouvee, message_erreur).
    """
    try:
        # Tente de géocoder les coordonnées avec OpenCage.
        # reverse_geocode est la méthode pour OpenCage
        results = geocoder.reverse_geocode(latitude, longitude, language='fr') # Préciser la langue pour de meilleurs résultats français

        if results and len(results) > 0:
            # OpenCage renvoie des résultats dans un format légèrement différent
            components = results[0]['components']
            
            # Rechercher la commune dans différents champs d'OpenCage
            # Les noms peuvent varier (city, town, village, municipality, etc.)
            found_commune = components.get('city') or \
                            components.get('town') or \
                            components.get('village') or \
                            components.get('municipality') or \
                            components.get('county') or \
                            components.get('suburb') or \
                            components.get('hamlet') # Ajout de hamlet pour des lieux très petits

            if found_commune:
                normalized_expected = expected_commune.lower().strip()
                normalized_found = found_commune.lower().strip()

                # Comparaison plus flexible: si l'un est contenu dans l'autre
                if normalized_expected in normalized_found or normalized_found in normalized_expected:
                    return True, found_commune, None
                else:
                    return False, found_commune, f"La commune trouvée ({found_commune}) ne correspond pas à l'attendue ({expected_commune})."
            else:
                return False, None, "Aucune commune trouvée pour ces coordonnées."
        else:
            return False, None, "Aucune information de localisation trouvée pour ces coordonnées."
    except Exception as e:
        # Gérer les erreurs spécifiques d'API comme les limites de requêtes
        if "rate limit exceeded" in str(e).lower() or "forbidden" in str(e).lower():
            return False, None, f"Erreur OpenCage : Limite de requêtes API dépassée ou clé invalide. Veuillez vérifier votre clé ou le quota."
        return False, None, f"Erreur lors de la vérification : {e}"

# --- Section de téléchargement de fichier ---
st.header("1. Téléchargez votre fichier CSV")
uploaded_file = st.file_uploader("Choisissez un fichier CSV", type="csv")

if uploaded_file is not None:
    st.success("Fichier CSV téléchargé avec succès !")
    # Lecture du fichier CSV
    try:
        # Utilise le délimiteur point-virgule comme identifié précédemment
        df = pd.read_csv(uploaded_file, delimiter=';')
        st.subheader("Aperçu de votre fichier (les 5 premières lignes) :")
        st.dataframe(df.head())

        # Vérification des colonnes requises
        required_columns = ['latitude', 'longitude', 'commune']
        if not all(col in df.columns for col in required_columns):
            st.error(f"Le fichier CSV doit contenir les colonnes suivantes : {', '.join(required_columns)}")
            st.info("Vérifiez l'orthographe exacte des en-têtes de colonnes (minuscules) ou le séparateur de votre fichier (doit être ';').")
        else:
            st.header("2. Lancement de la vérification")
            st.info("Traitement en cours... Préparez-vous à la vitesse ! 🚀")

            # Initialisation des listes pour stocker les résultats
            results = []
            progress_bar = st.progress(0)
            total_rows = len(df)

            # Application de la fonction de vérification à chaque ligne
            for index, row in df.iterrows():
                lat = row['latitude']
                lon = row['longitude']
                commune = str(row['commune']) # Assurez-vous que la commune est une chaîne de caractères

                # Utilisation de la nouvelle fonction de vérification OpenCage
                is_match, found_commune, error_message = verify_coordinates_opencage(lat, lon, commune)
                
                results.append({
                    'latitude': lat,
                    'longitude': lon,
                    'commune_attendue': commune,
                    'commune_trouvee': found_commune,
                    'correspondance_ok': is_match,
                    'message_erreur': error_message
                })
                # Mise à jour de la barre de progression
                progress_bar.progress((index + 1) / total_rows)
            
            results_df = pd.DataFrame(results)

            st.subheader("3. Résultats de la vérification")

            # Affichage des lignes avec des non-correspondances
            false_matches_df = results_df[results_df['correspondance_ok'] == False]

            if not false_matches_df.empty:
                st.error(f"🚨 {len(false_matches_df)} non-correspondance(s) trouvée(s) :")
                # Afficher seulement les colonnes pertinentes pour les erreurs
                st.dataframe(false_matches_df[['latitude', 'longitude', 'commune_attendue', 'commune_trouvee', 'message_erreur']])

                # Option de téléchargement des erreurs
                st.download_button(
                    label="Télécharger les non-correspondances en CSV",
                    data=false_matches_df.to_csv(index=False, sep=';', encoding='utf-8').encode('utf-8'),
                    file_name="non_correspondances_coordonnees.csv",
                    mime="text/csv",
                    help="Cliquez pour télécharger un fichier CSV contenant toutes les lignes où les coordonnées ne correspondent pas à la commune attendue."
                )
            else:
                st.success("🎉 Toutes les coordonnées correspondent aux communes ! Aucune non-correspondance trouvée.")

            # Option d'afficher toutes les vérifications (pour le debug/visualisation complète)
            if st.checkbox("Afficher toutes les vérifications (y compris les correspondances)"):
                st.subheader("Toutes les vérifications :")
                st.dataframe(results_df)

    except Exception as e:
        st.error(f"Une erreur est survenue lors de la lecture ou du traitement de votre fichier CSV : {e}")
        st.info("Veuillez vous assurer que votre fichier est bien un CSV valide et contient les colonnes 'latitude', 'longitude' et 'commune'. Assurez-vous également que les colonnes sont séparées par des points-virgules ';'.")

st.markdown("---")
st.markdown("Développé avec ❤️ par votre Partenaire de code.")
