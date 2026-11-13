"""Registra MEM USAGE del contenedor de Ollama (equivalente a `docker stats`)
cada segundo y lo guarda en memoria_docker_stats.csv, junto con el modelo
residente según `ollama ps`. Se detiene con Ctrl+C o al recibir SIGTERM."""
import csv
import subprocess
import time

CONTAINER = "ollama-local-lab"
OUT = "memoria_docker_stats.csv"


def sh(*args):
    return subprocess.run(args, capture_output=True, text=True).stdout.strip()


def main():
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["t_s", "mem_usage", "cpu_pct", "ollama_ps"])
        t0 = time.time()
        try:
            while True:
                stats = sh("docker", "stats", "--no-stream", "--format",
                           "{{.MemUsage}}|{{.CPUPerc}}", CONTAINER)
                mem, _, cpu = stats.partition("|")
                ps = sh("docker", "exec", CONTAINER, "ollama", "ps")
                ps_line = " ".join(ps.splitlines()[1:2]).replace("\t", " ")
                w.writerow([round(time.time() - t0, 1), mem, cpu, ps_line])
                f.flush()
                time.sleep(1)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
