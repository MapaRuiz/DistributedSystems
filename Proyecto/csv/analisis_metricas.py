import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import os

# Cargar los archivos CSV limpios
files = {
    "Async - Case 1": "cleaned_case1.csv",
    "LBB - Case 1": "cleaned_case1lbb.csv",
    "Async - Case 2": "cleaned_case2.csv",
    "LBB - Case 2": "cleaned_case2lbb.csv",
}

# Columnas relevantes para análisis
response_time_server_to_faculty = "faculty_server_ack_res_roundtrip_ms"
response_time_program_total = "response_time_program_faculty_total_ms"
request_outcome = "request_outcome"

# Diccionario para guardar métricas por archivo
results = {}

for label, path in files.items():
    df = pd.read_csv(path)

    # Filtrado de métricas relevantes
    server_to_faculty_df = df[df["kind"] == response_time_server_to_faculty]
    program_response_df = df[df["kind"] == response_time_program_total]
    outcome_df = df[df["kind"] == request_outcome]

    # Cálculo de métricas
    metrics = {
        "avg_server_to_faculty": server_to_faculty_df["value"].mean(),
        "min_server_to_faculty": server_to_faculty_df["value"].min(),
        "max_server_to_faculty": server_to_faculty_df["value"].max(),
        "avg_program_response": program_response_df["value"].mean(),
        "successful_requests": outcome_df[outcome_df["value"] == 1.0].shape[0],
        "failed_requests": outcome_df[outcome_df["value"] == 3.0].shape[0],
    }

    results[label] = metrics

# Crear DataFrame para visualización
results_df = pd.DataFrame(results).T.reset_index().rename(columns={"index": "Case"})

# Crear carpeta de salida
output_dir = "metric_charts"
os.makedirs(output_dir, exist_ok=True)

# Función para crear gráficos de barras
def plot_bar(data, column, title, ylabel, filename):
    plt.figure(figsize=(10, 6))
    sns.barplot(x="Case", y=column, hue="Case", data=data, palette="viridis", legend=False)
    plt.title(title)
    plt.ylabel(ylabel)
    plt.xticks(rotation=15, ha='right')
    plt.tight_layout()
    path = os.path.join(output_dir, filename)
    plt.savefig(path)
    plt.close()

# Generar gráficos
plot_bar(results_df, "avg_server_to_faculty", "Tiempo Promedio: Servidor → Facultad", "ms", "avg_server_to_faculty.png")
plot_bar(results_df, "min_server_to_faculty", "Tiempo Mínimo: Servidor → Facultad", "ms", "min_server_to_faculty.png")
plot_bar(results_df, "max_server_to_faculty", "Tiempo Máximo: Servidor → Facultad", "ms", "max_server_to_faculty.png")
plot_bar(results_df, "avg_program_response", "Tiempo Promedio: Programa → Facultad (Total)", "ms", "avg_program_response.png")
plot_bar(results_df, "successful_requests", "Solicitudes Atendidas", "Cantidad", "successful_requests.png")
plot_bar(results_df, "failed_requests", "Solicitudes No Atendidas", "Cantidad", "failed_requests.png")

# Exportar tabla comparativa a CSV
results_df.to_csv("resumen_metricas.csv", index=False)

# Función para guardar tabla como imagen
def save_table_as_image(df, title, filename):
    fig, ax = plt.subplots(figsize=(12, len(df) * 0.6 + 1))
    fig.patch.set_visible(False)
    ax.axis('off')
    ax.axis('tight')
    table = ax.table(cellText=df.values,
                     colLabels=df.columns,
                     cellLoc='center',
                     loc='center')
    table.scale(1, 1.5)
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    plt.title(title, fontsize=14, weight='bold')
    plt.tight_layout()
    path = os.path.join(output_dir, filename)
    plt.savefig(path, bbox_inches='tight')
    plt.close()

# Guardar tabla como imagen
save_table_as_image(results_df, "Resumen Comparativo de Métricas", "tabla_resumen_metricas.png")

