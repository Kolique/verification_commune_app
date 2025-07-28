import streamlit as st
import pandas as pd
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import time

# --- Configuration de l'application Streamlit ---
st.set_page_config(
    page_title="Vérificateur de Correspondance Coordonnées-Commune",
    page_icon="🗺️",
    layout="wide"
)

st.title("🗺️ Vérificateur de Correspondance Coordonnées-Commune")
st.markdown("""
Cette application vous permet de vérifier la correspondance entre les coordonnées géographiques (latitude, longitude)
et la commune associée dans votre fichier CSV.
""")

st.warning("⚠️ **Important :** Ce service utilise Nominatim d'OpenStreetMap. Il y a des limites d'utilisation (environ 1 requête par seconde). Pour de très gros fichiers, cela peut prendre du temps ou rencontrer des problèmes de dépassement de limite. Pour une utilisation plus intensive, des services de géocodage payants seraient plus adaptés.")

# --- Initialisation du géocodeur Nominatim ---
# Il est crucial de définir un 'user_agent' unique pour votre application.
# Remplacez "mon_app_de_verification_coordonnees" par un nom qui identifie votre application.
geolocator = Nominatim(user_agent="mon_app_de_verification_coordonnees_par_code_partenaire")

# Utilisation de RateLimiter pour respecter les limites de requêtes de Nominatim
# Cela assure qu'il y a un délai minimum entre les requêtes (ici, 1 seconde).
geocode = RateLimiter(geolocator.reverse, min_delay_seconds=1)

# --- Fonction de vérification des coordonnées ---
@st.cache_data
def verify_coordinates(latitude, longitude, expected_commune):
    """
    Vérifie si les coordonnées correspondent à la commune attendue.
    Retourne un tuple (correspondance_ok, commune_trouvee, message_erreur).
    """
    try:
        # Tente de géocoder les coordonnées
        location = geocode(f"{latitude}, {longitude}")

        if location:
            # Récupère les informations d'adresse brutes
            address = location.raw.get('address', {})

            # Essaye de trouver la ville/commune dans différents champs
            # Ajout de 'county' et 'suburb' pour plus de robustesse, car la 'commune' peut varier.
            found_commune = address.get('city') or \
                            address.get('town') or \
                            address.get('village') or \
                            address.get('municipality') or \
                            address.get('county') or \
                            address.get('suburb') # Ajout de suburb

            if found_commune:
                # Normalise les noms pour une meilleure comparaison (minuscules, sans accents, etc.)
                # Pour une comparaison simple, nous allons juste mettre en minuscules et supprimer les espaces.
                # Pour une robustesse accrue, une librairie de normalisation de chaînes (comme unidecode ou difflib) pourrait être utilisée.
                normalized_expected = expected_commune.lower().strip()
                normalized_found = found_commune.lower().strip()

                # On vérifie si la commune trouvée est contenue dans la commune attendue ou vice-versa,
                # pour gérer les petites variations de noms (ex: "Paris" vs "Paris Cedex")
                if normalized_expected in normalized_found or normalized_found in normalized_expected:
                    return True, found_commune, None
                else:
                    return False, found_commune, f"La commune trouvée ({found_commune}) ne correspond pas à l'attendue ({expected_commune})."
            else:
                return False, None, "Aucune commune trouvée pour ces coordonnées."
        else:
            return False, None, "Aucune information de localisation trouvée pour ces coordonnées."
    except Exception as e:
        return False, None, f"Erreur lors de la vérification : {e}"

# --- Section de téléchargement de fichier ---
st.header("1. Téléchargez votre fichier CSV")
uploaded_file = st.file_uploader("Choisissez un fichier CSV", type="csv")

if uploaded_file is not None:
    st.success("Fichier CSV téléchargé avec succès !")
    # Lecture du fichier CSV
    try:
        # C'est la ligne corrigée : ajout de delimiter=';'
        df = pd.read_csv(uploaded_file, delimiter=';')
        st.subheader("Aperçu de votre fichier (les 5 premières lignes) :")
        st.dataframe(df.head())

        # Vérification des colonnes requises
        required_columns = ['latitude', 'longitude', 'commune']
        if not all(col in df.columns for col in required_columns):
            st.error(f"Le fichier CSV doit contenir les colonnes suivantes : {', '.join(required_columns)}")
            st.info("Vérifiez l'orthographe des en-têtes de colonnes ou le séparateur de votre fichier (doit être ';').")
        else:
            st.header("2. Lancement de la vérification")
            st.info("Traitement en cours... Cela peut prendre un certain temps en fonction de la taille de votre fichier et des limites du service de géocodage.")

            # Initialisation des listes pour stocker les résultats
            results = []
            progress_bar = st.progress(0)
            total_rows = len(df)

            # Application de la fonction de vérification à chaque ligne
            for index, row in df.iterrows():
                lat = row['latitude']
                lon = row['longitude']
                commune = str(row['commune']) # Assurez-vous que la commune est une chaîne de caractères

                is_match, found_commune, error_message = verify_coordinates(lat, lon, commune)
                
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
