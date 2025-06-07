import pandas as pd

# Lista de archivos originales
input_files = [
    "case1.csv",
    "case2.csv",
    "case1lbb.csv",
    "case2lbb.csv"
]

# Procesar cada archivo
for file in input_files:
    try:
        # Leer archivo
        df = pd.read_csv(file)

        # Asegurar nombres consistentes (puedes ajustar si tus archivos usan nombres distintos)
        expected_columns = ['id', 'kind', 'value', 'ts', 'src', 'dst']
        df.columns = expected_columns[:len(df.columns)]

        # Convertir 'value' a numérico, errores se convierten en NaN
        df['value'] = pd.to_numeric(df['value'], errors='coerce')

        # Eliminar filas con NaNs en columnas clave
        df_cleaned = df.dropna(subset=['kind', 'value', 'src', 'dst'])

        # Guardar el archivo limpio
        cleaned_filename = f"cleaned_{file}"
        df_cleaned.to_csv(cleaned_filename, index=False)
        print(f"✅ Archivo limpiado y guardado como: {cleaned_filename}")
    except Exception as e:
        print(f"⚠️ Error procesando {file}: {e}")
