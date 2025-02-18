import streamlit as st
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch
import re
import unicodedata
from src.database import save_prediction_to_db, get_predictions, create_database

create_database()


def clean_text(text):
    """
    Limpia y normaliza el texto
    """
    text = text.lower()
    text = unicodedata.normalize(
        'NFKD', text).encode('ASCII', 'ignore').decode('utf-8')
    text = re.sub(r'http\S+|www\S+|https\S+', '', text, flags=re.MULTILINE)
    text = re.sub(r'\S+@\S+', '', text)
    text = re.sub(r'\d+', '', text)
    text = re.sub(r'[^\w\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    return text


@st.cache_resource
def load_model():
    # Reemplaza con tu usuario/nombre-del-modelo de Hugging Face
    model_name = "Dolcevitta/toxic-bert-model"
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(model_name)
    return tokenizer, model


def predict_toxicity(text, tokenizer, model):
    # Limpiar texto
    cleaned_text = clean_text(text)

    # Preparar input
    inputs = tokenizer(cleaned_text,
                       return_tensors="pt",
                       truncation=True,
                       max_length=512)

    # Predicción
    with torch.no_grad():
        outputs = model(**inputs)
        probabilities = torch.softmax(outputs.logits, dim=1)
        probability = probabilities[0][1].item()  # Probabilidad de toxicidad

    is_toxic = probability > 0.5
    return is_toxic, probability, cleaned_text

# Título de la aplicación


st.title("🔍 Toxic Comment Detector")
st.write("""
This application analyzes text to detect toxic content.
Enter your text and the model will evaluate its toxicity level.
""")

# Inicializar el estado de la sesión
if 'text_input' not in st.session_state:
    st.session_state.text_input = ""


def clear_text():
    st.session_state.text_input = ""


try:
    # Cargar modelo
    tokenizer, model = load_model()

    # Área de texto
    text_input = st.text_area(
        "Enter text to analyze:",
        height=100,
        placeholder="Write or paste text here...",
        key="text_input"
    )

    col1, col2 = st.columns(2)

    with col1:
        analyze_button = st.button("Analyze text")

    with col2:
        clear_button = st.button("Clear text", on_click=clear_text)

    if analyze_button and text_input.strip():
        with st.spinner('Analyzing...'):
            is_toxic, probability, cleaned_text = predict_toxicity(
                text_input, tokenizer, model)
            # Guardar predicción en la base de datos
            label = "TOXIC" if is_toxic else "NON-TOXIC"
            save_prediction_to_db([text_input], [(label, probability)])
            st.success("✅ Resultado guardado en la base de datos")

        st.subheader("Processed Text:")
        col1, col2 = st.columns(2)
        with col1:
            st.text_area("Original text:", text_input, disabled=True)
        with col2:
            st.text_area("Cleaned text:", cleaned_text, disabled=True)

        st.subheader("Analysis Results:")

        col1, col2 = st.columns(2)

        with col1:
            st.metric(
                label="Toxicity Probability",
                value=f"{probability:.1%}"
            )

        with col2:
            if is_toxic:
                st.error("🚨 Text classified as TOXIC")
            else:
                st.success("✅ Text classified as NON-TOXIC")

        st.progress(float(probability))

        st.info("""
        💡 Interpretation:
        - 0-25%: Safe content
        - 25-50%: Potentially problematic content
        - 50-75%: Likely toxic content
        - 75-100%: Highly toxic content
        """)
    elif analyze_button:
        st.warning("⚠️ Please enter some text to analyze.")

except Exception as e:
    st.error(f"Error loading the model: {str(e)}")
    st.error("Make sure you have the correct model name from Hugging Face.")


st.markdown("---")
st.subheader("📋 Historial de Predicciones")

show_history = st.button("Mostrar historial de predicciones")

if show_history:
    with st.spinner('Cargando historial...'):
        predictions = get_predictions()

        if predictions:
            # Crear un DataFrame para mostrar los datos de forma ordenada
            import pandas as pd
            df = pd.DataFrame(
                predictions,
                columns=['ID',
                         'Comentario',
                         'Clasificación',
                         'Nivel de Toxicidad']
            )

            # Formatear el nivel de toxicidad como porcentaje
            df['Nivel de Toxicidad'] = df['Nivel de Toxicidad'].apply(
                lambda x: f"{x:.1%}")

            # Aplicar estilo condicional
            def color_toxicity(val):
                if val == 'TOXIC':
                    return 'background-color: #ffcdd2'
                return 'background-color: #c8e6c9'

            # Mostrar la tabla con estilo
            st.dataframe(
                df.style.applymap(
                    color_toxicity,
                    subset=['Clasificación']
                ),
                use_container_width=True,
                hide_index=True
            )

            # Añadir algunas estadísticas
            st.markdown("### 📊 Estadísticas")
            col1, col2 = st.columns(2)

            with col1:
                total_toxic = len(df[df['Clasificación'] == 'TOXIC'])
                total_records = len(df)
                st.metric(
                    "Porcentaje de comentarios tóxicos",
                    f"{(total_toxic/total_records)*100:.1f}%"
                )

            with col2:
                st.metric(
                    "Total de predicciones",
                    f"{total_records}"
                )

else:
    st.info("No hay predicciones guardadas en la base de datos.")
