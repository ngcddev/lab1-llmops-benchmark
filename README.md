# Lab 1 · LLMOps: Benchmarking de serving local y cuantización

Despliegue de un motor de inferencia local (**Ollama en Docker**, solo CPU) y comparación empírica de dos niveles de cuantización GGUF del modelo **Qwen2.5-1.5B-Instruct**: **Q4_K_M (4 bits)** frente a **Q8_0 (8 bits)**. Se mide la huella de memoria, la latencia inicial (**TTFT**) y la velocidad de generación (**TPS**), y se guardan las respuestas completas de cada modelo para evaluar si la cuantización degrada la calidad.

> El análisis técnico con las respuestas a las 4 preguntas del laboratorio está en [`ENTREGABLE.md`](ENTREGABLE.md).

## Resultados en una mirada

| Métrica (promedio de 3 prompts) | Q4_K_M (4 bits) | Q8_0 (8 bits) | Diferencia |
|---|---:|---:|---|
| Tamaño en disco | 986 MB | 1,6 GB | Q4 pesa ~38 % menos |
| RAM del contenedor (pico) | 1,41 GiB | 2,03 GiB | +631 MiB en Q8 |
| Velocidad de generación | **31,65 tok/s** | 20,35 tok/s | **+55,5 %** a favor de Q4 |
| TTFT | 332 ms | 403 ms | Q4 un 18 % más rápido |
| Calidad de respuestas | Baja (modelo de 1,5B) | Baja (modelo de 1,5B) | Sin diferencia atribuible a la cuantización |

Conclusión corta: pasar de 8 a 4 bits reduce la memoria y acelera la generación de forma clara, y con un modelo de 1,5B la calidad ya era limitada en ambos casos, así que Q4_K_M es la mejor opción en CPU.

## Entorno de la prueba

| Componente | Valor |
|---|---|
| CPU | AMD Ryzen 7 7435HS (8 núcleos / 16 hilos) |
| RAM | 16 GB (Docker Desktop con WSL2 limitado a 7,6 GiB) |
| GPU | Ninguna usada: Ollama reportó `100% CPU` |
| SO | Windows 11 + Docker Desktop |
| Docker / Compose | 29.9.2 / v5.6.1 |
| Python | 3.15.2 (pandas 3.1.1, requests) |
| Contexto (`num_ctx`) | 2048 tokens |
| Temperatura | 0,1 |

## Estructura del repositorio

```
.
├── docker-compose.yml          # Servicio Ollama (CPU) con volumen persistente
├── benchmark.py                # Benchmark: warm-up + 3 prompts x 2 modelos
├── monitor_ram.py              # Muestrea `docker stats` y `ollama ps` cada segundo
├── requirements.txt
├── resultados_benchmark.csv    # Métricas por modelo y prompt
├── resultados_benchmark.md     # Las 6 respuestas completas con sus métricas
├── memoria_docker_stats.csv    # Serie temporal de RAM/CPU del contenedor
├── ENTREGABLE.md               # Análisis técnico (4 preguntas)
└── README.md
```

## Cómo reproducirlo

Requisitos: Docker Desktop encendido y Python 3.9 o superior. Los comandos son para PowerShell en Windows; en Linux/macOS cambia solo la activación del entorno virtual.

**1. Levantar Ollama**

```bash
docker compose up -d
docker ps
```

**2. Descargar las dos variantes cuantizadas** (~2,6 GB en total)

```bash
docker exec -it ollama-local-lab ollama pull qwen2.5:1.5b-instruct-q4_K_M
docker exec -it ollama-local-lab ollama pull qwen2.5:1.5b-instruct-q8_0
docker exec -it ollama-local-lab ollama list
```

**3. Preparar el entorno de Python**

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1      # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
```

**4. Ejecutar el benchmark** (en otra terminal, opcionalmente el monitor de RAM)

```bash
python monitor_ram.py           # Terminal A: registra memoria_docker_stats.csv (Ctrl+C para parar)
python benchmark.py             # Terminal B: genera el CSV y el Markdown de resultados
docker exec -it ollama-local-lab ollama ps   # Terminal C: modelo residente y % CPU
```

**5. Limpieza**

```bash
deactivate
docker compose down
```

## Metodología

- **Warm-up:** antes de medir, cada modelo recibe un prompt trivial ("Hola") para que los pesos ya estén cargados en RAM y el TTFT no incluya el tiempo de carga.
- **Prompts:** tres tipos de tarea (definición corta, razonamiento medio y generación de código) idénticos para ambos modelos.
- **TTFT:** tiempo medido en el cliente desde el envío de la petición hasta recibir el primer token en el stream.
- **TPS:** `eval_count / eval_duration` según las estadísticas internas que devuelve Ollama (solo fase de generación, sin prefill).
- **Memoria:** `docker stats` muestreado cada segundo durante todo el benchmark; se reporta el pico con cada modelo residente.
- **Reproducibilidad:** temperatura 0,1 y `num_ctx` fijo en 2048 para que el KV Cache sea constante entre modelos.

> Cambio respecto al script de la guía: `benchmark.py` registra además `Tokens prompt` (tokens de entrada, vía `prompt_eval_count`), necesario para interpretar el TTFT.

## Resultados detallados

### Rendimiento por prompt

| Modelo | Prompt | Tokens entrada | TTFT (ms) | TPS | Tokens generados | Total (s) |
|---|---|---:|---:|---:|---:|---:|
| Q4_K_M | Corto (definición) | 52 | 234,5 | 31,08 | 472 | 15,4 |
| Q4_K_M | Medio (razonamiento) | 79 | 439,2 | 31,40 | 715 | 23,2 |
| Q4_K_M | Largo (código) | 65 | 322,2 | 32,48 | 571 | 17,9 |
| Q8_0 | Corto (definición) | 52 | 302,6 | 21,37 | 319 | 15,2 |
| Q8_0 | Medio (razonamiento) | 79 | 486,2 | 20,53 | 588 | 29,1 |
| Q8_0 | Largo (código) | 65 | 421,3 | 19,14 | 683 | 36,1 |

### Memoria del contenedor `ollama-local-lab`

| Estado | MEM USAGE |
|---|---:|
| Contenedor sin modelo cargado | ~330 MiB |
| Q4_K_M cargado y generando | **1,413 GiB** |
| Q8_0 cargado y generando | **2,029 GiB** |

La serie completa está en `memoria_docker_stats.csv`. Durante la generación la CPU del contenedor se mantiene cerca del 790 %, es decir, los 8 núcleos saturados.

### Hallazgos

- **La generación está limitada por el ancho de banda de memoria.** Cada token exige leer todos los pesos. Multiplicando tamaño del modelo por TPS se obtiene ~31 GB/s en ambos casos (0,99 GB x 31,65 y 1,6 GB x 20,35), lo que explica por qué reducir los bits acelera casi en proporción.
- **El consumo en ejecución supera al archivo en disco.** Además de los pesos hay KV Cache (~56 MiB teóricos para 2048 tokens en este modelo), buffers de cómputo y el propio proceso del servidor.
- **El TTFT no depende solo de la longitud del prompt.** En esta corrida el prompt "Largo" es el de código, que genera más salida pero no tiene la entrada más larga: la tiene el "Medio" (79 tokens), que también tiene el TTFT más alto.
- **La calidad no es el límite de la cuantización sino del tamaño del modelo.** Ambas variantes alucinan en la pregunta de arquitectura y ambas generan código de búsqueda binaria que falla al ejecutarlo (ver `ENTREGABLE.md`).

## Limitaciones

- Una sola corrida por combinación (n = 1): no hay desviación estándar, y diferencias pequeñas de TTFT pueden ser ruido.
- La máquina tenía otros contenedores de otro proyecto en ejecución, lo que pudo restar algo de CPU.
- La memoria se mide a nivel de contenedor, no de proceso.
- La evaluación de calidad es cualitativa, sobre solo 3 prompts.

## Referencias

- [Ollama](https://ollama.com) y su [API de generación](https://github.com/ollama/ollama/blob/main/docs/api.md)
- Formato [GGUF](https://github.com/ggml-org/ggml/blob/master/docs/gguf.md) y esquemas de cuantización de llama.cpp
- Modelo: [Qwen2.5-1.5B-Instruct](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct)
