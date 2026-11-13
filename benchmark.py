import time
import json
import requests
import pandas as pd

OLLAMA_URL = "http://localhost:11434/api/generate"

MODELS = [
    "qwen2.5:1.5b-instruct-q4_K_M",
    "qwen2.5:1.5b-instruct-q8_0"
]

PROMPTS = [
    {
        "tipo": "Corto (Definición)",
        "texto": "Explica en exactamente 3 viñetas qué es la cuantización en modelos de lenguaje."
    },
    {
        "tipo": "Medio (Razonamiento)",
        "texto": "Tengo un servidor con 16 GB de RAM y sin GPU. Quiero desplegar un asistente interno para 5 empleados. ¿Qué arquitectura y tamaño de modelo me recomiendas y por qué?"
    },
    {
        "tipo": "Largo (Generación de Código)",
        "texto": "Escribe una función en Python bien documentada que implemente búsqueda binaria sobre una lista ordenada, incluyendo manejo de excepciones y 3 casos de prueba."
    }
]

def run_inference(model: str, prompt: str):
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": True,
        "options": {
            "temperature": 0.1,  # Baja temperatura para reproducibilidad
            "num_ctx": 2048      # Contexto fijo para controlar el tamaño del KV Cache
        }
    }

    start_time = time.perf_counter()
    first_token_time = None
    full_response = []
    eval_count = 0
    eval_duration_ns = 0
    prompt_eval_count = 0

    with requests.post(OLLAMA_URL, json=payload, stream=True) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if line:
                chunk = json.loads(line.decode("utf-8"))
                if first_token_time is None and chunk.get("response"):
                    first_token_time = time.perf_counter()

                full_response.append(chunk.get("response", ""))

                if chunk.get("done"):
                    eval_count = chunk.get("eval_count", 0)
                    eval_duration_ns = chunk.get("eval_duration", 1)
                    prompt_eval_count = chunk.get("prompt_eval_count", 0)

    end_time = time.perf_counter()

    ttft_ms = (first_token_time - start_time) * 1000 if first_token_time else 0
    total_time_s = end_time - start_time
    tps = eval_count / (eval_duration_ns / 1e9) if eval_duration_ns > 0 else 0

    return {
        "ttft_ms": round(ttft_ms, 2),
        "tps": round(tps, 2),
        "tokens_generados": eval_count,
        "tokens_prompt": prompt_eval_count,
        "tiempo_total_s": round(total_time_s, 2),
        "respuesta_completa": "".join(full_response)
    }

def main():
    resultados_tabular = []
    resultados_detallados = []

    print("Iniciando Benchmark de Cuantización Local y Generación de Reporte...\n")

    for model in MODELS:
        print(f"--- Evaluando modelo: {model} ---", flush=True)
        # Warm-up de memoria
        print("Realizando warm-up de memoria...", flush=True)
        run_inference(model, "Hola")

        for item in PROMPTS:
            print(f"Ejecutando prompt: {item['tipo']}...", flush=True)
            metrics = run_inference(model, item["texto"])

            # Datos para CSV / Tabla resumen
            resultados_tabular.append({
                "Modelo": model.split(":")[1],
                "Prompt": item["tipo"],
                "TTFT (ms)": metrics["ttft_ms"],
                "Velocidad (TPS)": metrics["tps"],
                "Tokens": metrics["tokens_generados"],
                "Tokens prompt": metrics["tokens_prompt"],
                "Total (s)": metrics["tiempo_total_s"]
            })

            # Datos detallados para el documento Markdown
            resultados_detallados.append({
                "modelo": model,
                "tipo_prompt": item["tipo"],
                "texto_prompt": item["texto"],
                "respuesta_completa": metrics["respuesta_completa"],
                "ttft_ms": metrics["ttft_ms"],
                "tps": metrics["tps"],
                "tokens": metrics["tokens_generados"],
                "tiempo_total_s": metrics["tiempo_total_s"]
            })

    # Guardar CSV resumen
    df = pd.DataFrame(resultados_tabular)
    df.to_csv("resultados_benchmark.csv", index=False)

    # Generar Documento Markdown estructurado
    md_content = "# Reporte de Benchmark y Respuestas: LLMOps Lab 1\n\n"
    md_content += "Este documento detalla las respuestas completas obtenidas por cada modelo cuantizado frente a los prompts de prueba, acompañadas de sus métricas de rendimiento.\n\n"
    md_content += "---\n\n"

    for idx, r in enumerate(resultados_detallados, 1):
        md_content += f"## Prueba {idx}: {r['modelo']}\n\n"
        md_content += f"- **Categoría de Prompt:** {r['tipo_prompt']}\n"
        md_content += f"- **Métricas:** `TTFT: {r['ttft_ms']} ms` | `Velocidad: {r['tps']} TPS` | `Tokens: {r['tokens']}` | `Tiempo Total: {r['tiempo_total_s']} s`\n\n"
        md_content += f"### Prompt Enviado:\n> {r['texto_prompt']}\n\n"
        md_content += f"### Respuesta Generada:\n```text\n{r['respuesta_completa']}\n```\n\n"
        md_content += "---\n\n"

    with open("resultados_benchmark.md", "w", encoding="utf-8") as f:
        f.write(md_content)

    print("\n=== BENCHMARK FINALIZADO ===")
    print("Archivos generados con éxito:")
    print("1. Resumen tabulado en: 'resultados_benchmark.csv'")
    print("2. Reporte detallado en: 'resultados_benchmark.md'")

if __name__ == "__main__":
    main()
