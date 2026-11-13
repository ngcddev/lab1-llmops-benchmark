# Entregable Laboratorio 1: Benchmarking de Serving Local y Cuantización

- **Curso:** LLMOps, Serving Local y Arquitecturas RAG
- **Estudiante:** _(completar nombre completo)_
- **Hardware utilizado:** AMD Ryzen 7 7435HS, 16 GB RAM (Docker Desktop/WSL2 con 7,6 GiB), Windows 11, solo CPU
- **Fecha:** 13 de noviembre de 2026
- **Modelo:** Qwen2.5-1.5B-Instruct en `q4_K_M` y `q8_0`, servido con Ollama en Docker

Archivos de soporte: `resultados_benchmark.csv`, `resultados_benchmark.md`, `memoria_docker_stats.csv`.

---

## Análisis Técnico de Resultados

### 1. Impacto en Memoria (MEM USAGE y KV Cache)

> ¿Cuál fue la diferencia exacta en MB/GB de RAM consumida entre `q4_K_M` y `q8_0` al ejecutar `docker stats`? ¿Por qué el consumo en ejecución supera el tamaño del archivo en disco?

**Respuesta:**

Con `docker stats` (muestreado cada segundo, ver `memoria_docker_stats.csv`) el contenedor marcó, con el modelo cargado y generando:

| | Disco | MEM USAGE (pico) |
|---|---:|---:|
| Contenedor sin modelo | n/a | ~330 MiB |
| `q4_K_M` | 986 MB | **1,413 GiB** (~1447 MiB) |
| `q8_0` | 1,6 GB | **2,029 GiB** (~2078 MiB) |

La diferencia entre ambos es de **~631 MiB (~0,62 GiB)**, prácticamente la misma que hay entre los archivos en disco (~614 MB). Es lo esperado: el KV Cache es idéntico para los dos porque `num_ctx` está fijo en 2048 y la arquitectura es la misma, así que toda la diferencia viene de los pesos.

El consumo en ejecución supera el tamaño del archivo por tres motivos:

1. **KV Cache:** guarda las claves y valores de atención de cada token del contexto. Se reserva para los 2048 tokens de `num_ctx` aunque el prompt sea corto. Para este modelo (28 capas, 2 cabezas KV, dimensión 128, en fp16) son unos 28 KB por token, es decir, **~56 MiB** en total.
2. **Buffers de cómputo:** activaciones intermedias y el grafo de cálculo de llama.cpp.
3. **Proceso base:** el servidor de Ollama, su runtime y el contenedor ya ocupan ~330 MiB antes de cargar nada. Por eso `ollama ps` reporta 1,8 GB para `q8_0` (pesos + KV + buffers) y `docker stats` un poco más (suma además el proceso base).

---

### 2. Ancho de Banda de Memoria y Velocidad (TPS)

> En inferencia sobre CPU, el cuello de botella suele ser el ancho de banda de la memoria RAM. ¿En qué porcentaje aumentó la velocidad (TPS) al pasar de 8 bits a 4 bits?

**Respuesta:**

Promedio de los tres prompts: `q4_K_M` = **31,65 tok/s** y `q8_0` = **20,35 tok/s**.

```
mejora = (31,65 − 20,35) / 20,35 × 100 ≈ 55,5 %
```

La velocidad **aumentó un ~55 %** al pasar de 8 a 4 bits (equivale a que `q8_0` sea ~36 % más lento). El resultado es consistente en los tres prompts (31,1–32,5 frente a 19,1–21,4 tok/s).

La explicación es que la generación es autoregresiva: para producir cada token hay que leer **todos los pesos** desde la RAM, y el cálculo en sí es poco comparado con esa lectura. Por eso el límite es el ancho de banda y no los núcleos. Se comprueba multiplicando bytes leídos por tokens por segundo: 0,99 GB x 31,65 ≈ 31 GB/s y 1,6 GB x 20,35 ≈ 33 GB/s. Ambos modelos mueven casi el mismo caudal de memoria; el de 4 bits simplemente necesita leer menos bytes por token. La mejora (55 %) es algo menor que la reducción de tamaño (~38 %, que equivaldría a ~60 % más de velocidad) porque `q4_K_M` mezcla bloques de distinta precisión y hay costes de desempaquetado y partes que no se reducen.

---

### 3. Latencia Inicial (TTFT) y Fase Prefill

> ¿Por qué el `TTFT (ms)` es significativamente más alto en el Prompt Largo (Generación de Código) que en el Prompt Corto (Definición)?

**Respuesta:**

Antes de emitir el primer token el modelo debe procesar todo el prompt de entrada en la fase de **prefill**, donde se calculan las atenciones y se llena el KV Cache. Su coste crece con el número de tokens de entrada, por lo que prompts más largos tienen un TTFT mayor. A diferencia de la generación, el prefill procesa muchos tokens en paralelo y está limitado por cómputo, no por ancho de banda.

Datos medidos (tokens de entrada reportados por Ollama):

| Prompt | Tokens entrada | TTFT `q4_K_M` | TTFT `q8_0` |
|---|---:|---:|---:|
| Corto (definición) | 52 | 234 ms | 303 ms |
| Largo (código) | 65 | 322 ms | 421 ms |
| Medio (razonamiento) | 79 | 439 ms | 486 ms |

El prompt "Largo" tiene un TTFT **~37–39 % mayor** que el "Corto" en ambos modelos, y la diferencia coincide con que tiene más tokens de entrada (65 frente a 52). Sin embargo, conviene matizar dos cosas que muestran los datos:

- El "Largo" **no** es el de TTFT más alto: lo es el "Medio" (79 tokens de entrada). El nombre "Largo" se refiere a la longitud esperada de la **respuesta**, no del prompt, y la longitud de la respuesta no influye en el TTFT.
- La relación no es proporcional porque el TTFT incluye también costes fijos (petición HTTP, tokenización, planificación) y, con una sola corrida, hay ruido de medida. Los prompts son todos cortos (52–79 tokens), por lo que las diferencias son de cientos de milisegundos; con prompts de miles de tokens, como en RAG, el prefill domina y el efecto sería mucho mayor.

También `q8_0` tiene mayor TTFT que `q4_K_M` (403 ms frente a 332 ms de promedio), porque cada pasada necesita leer más pesos.

---

### 4. Calidad vs. Eficiencia en `resultados_benchmark.md`

> Revisando las 6 respuestas completas generadas, ¿hubo alguna degradación perceptible en la lógica del código Python o en el razonamiento arquitectónico generado por el modelo de 4 bits frente al de 8 bits?

**Respuesta:**

**No se observó una degradación atribuible a la cuantización:** las respuestas de ambos modelos son de baja calidad y de un nivel parecido, y el factor limitante es el tamaño del modelo (1,5B parámetros), no los bits. Detalle por prompt:

- **Definición (3 viñetas):** ambos definen mal la cuantización, como si fuera convertir texto en vectores numéricos (en realidad es reducir la precisión de los pesos). `q4_K_M` añade una introducción y un cierre fuera de las 3 viñetas pedidas; `q8_0` respeta mejor el formato de 3 viñetas, pero el contenido sigue siendo incorrecto.
- **Razonamiento arquitectónico:** ambos alucinan. `q4_K_M` recomienda "Claude, Anthropic, o Anthropic" con tamaños de "100M–300M", y `q8_0` lista modelos de ChatGPT y Claude con tamaños inventados y recomienda GPU pese a que el enunciado dice "sin GPU". Ninguno propone un modelo realista para 16 GB de RAM en CPU (por ejemplo, un modelo de 7B–8B en 4 bits con llama.cpp u Ollama). Aquí `q8_0` fue incluso algo peor en coherencia, lo que indica que la variación es del modelo y no de la cuantización.
- **Código (búsqueda binaria):** el algoritmo central (`left`/`right`/`mid`) es correcto en ambos, pero **ninguno de los dos programas funciona al ejecutarlo** (lo comprobé ejecutando ambos bloques):
  - `q4_K_M`: lanza `ValueError: El target está fuera de rango` en su propio segundo caso de prueba (buscar el 6), porque lanza una excepción cuando debería devolver -1. Su docstring promete `ValueError` si la lista no está ordenada, pero comprueba otra cosa. Pidió 3 casos y escribió 5 `print`.
  - `q8_0`: lanza `ValueError: La lista no está ordenada` al probar la lista vacía, porque `if not arr` entra en la excepción y el caso esperaba -1. Además, comprobar `arr != sorted(arr)` cuesta O(n log n) y anula la ventaja de O(log n) de la búsqueda binaria, y su caso con duplicados espera el índice 1 cuando el algoritmo devuelve 2. Escribió 5 casos en lugar de 3.

**Eficiencia:** `q4_K_M` ofrece una calidad equivalente con ~30 % menos de RAM en ejecución y un 55 % más de velocidad, por lo que es la opción preferible en CPU. Para obtener respuestas realmente útiles el camino es un modelo más grande, aprovechando que la cuantización a 4 bits permite correrlo en el mismo hardware, y no pasar de 4 a 8 bits en un modelo pequeño.

> Limitación: es una evaluación cualitativa con 3 prompts y una corrida por modelo; no sustituye a un benchmark de calidad con un conjunto de evaluación.

---

*Se adjuntan `resultados_benchmark.csv`, `resultados_benchmark.md` y `memoria_docker_stats.csv`.*
