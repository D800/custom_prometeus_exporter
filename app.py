import sys
from pprint import pprint

import requests
import os

import uvicorn
import yaml
import logging
import socket
from fastapi import FastAPI, Response
from prometheus_client.metrics_core import GaugeMetricFamily
from prometheus_client import REGISTRY, generate_latest, CONTENT_TYPE_LATEST, Counter

# Create app
app = FastAPI(debug=False)

# Настройка логгера
logger = logging.getLogger(__name__)  # Используем логгер Uvicorn с уровнем INFO


class TrackHealthExporter:
    def __init__(self, track_url):
        self.track_url = track_url
        self.health_status = 0  # 0 — не работает, 1 — работает
        self.disk_total = 0.0
        self.disk_free = 0.0
        self.requests_total = 0
        logger.info(f"TrackHealthExporter instance created with URL: {self.track_url}")

    def check_health(self):
        try:
            # Sending the request to the specified URL
            response = requests.get(f"{self.track_url}/actuator/health/custom",
                                    timeout=2, verify=False)
            response.raise_for_status()  # Raises an error for bad responses (4xx/5xx)
            self.requests_total += 1
            # Parsing the JSON response
            health_data = response.json()

            if not health_data:
                logger.warning("JSON is empty")
                return

            if health_data.get("status") == "UP":
                self.health_status = 1
            else:
                # If no vulnerabilities are found, set health_status to 1
                self.health_status = 0
            if "components" in health_data and "diskSpace" in health_data["components"]:
                if health_data["components"]["diskSpace"]["status"] == "UP":
                    self.disk_total = round(health_data["components"]["diskSpace"]["details"]["total"] / (1024 ** 3), 2)
                    self.disk_free = round(health_data["components"]["diskSpace"]["details"]["free"] / (1024 ** 3), 2)

        except requests.RequestException as e:
            logger.error(f"Request failed: {e}")
            self.health_status = 0

    def collect(self):  # переопределение метода библиотеки prometheus_client
        self.check_health()  # Выполняем проверку перед сбором метрик

        health_metric = GaugeMetricFamily(
            "track_health_status",
            "Состояние здоровья сервера Track (1 — работает, 0 — не работает), общее дисковое пространство, свободное",
            labels=["service"]
        )

        health_metric.add_metric(["UP"], self.health_status)
        health_metric.add_metric(["disk_total_GB"], self.disk_total)
        health_metric.add_metric(["disk_free_GB"], self.disk_free)
        yield health_metric

        # request_counter = Counter(
        #     "total_track_status_requests",
        #     "Суммарное количество запросов на /actuator/health/custom",
        #     ["hqweb"]
        # )
        #
        # request_counter.inc(self.requests_total)
        # yield request_counter

# Функция для чтения конфигурации из файла
def load_config(config_file):
    if not os.path.exists(config_file):
        logger.warning(f"Configuration file '{config_file}' not found. Using default values.")
        return {}  # Возвращаем пустой конфиг, если файл не найден
    with open(config_file, 'r') as file:
        return yaml.safe_load(file)


# Указание пути к конфигу
config_path = "./config.yml"
config = load_config(config_path)

# Проверка на наличие ключа "url" в конфиге
default_url = "http://localhost:4954"
track_url = default_url
url_source = "default_url"

if "TRACK_SERVER_URL" in os.environ:
    track_url = os.getenv("TRACK_SERVER_URL")
    url_source = "environment variable TRACK_SERVER_URL"
elif config.get("track", {}).get("url"):
    track_url = config.get("track", {}).get("url")
    url_source = "configuration file config.yml"

logger.info(f"Using track URL: {track_url} (source: {url_source})")
print(f"Using track URL: {track_url} (source: {url_source})")
# Получение IP-адреса сервера
server_ip = socket.gethostbyname(socket.gethostname())

# Порт, на котором будет запущено приложение
server_port = int(os.getenv("UVICORN_PORT", 8000))  # Можно также указать порт в переменной окружения
print("Printing TRACK_SERVER_URL from OS" + "\n" + str(os.getenv("TRACK_SERVER_URL")))
print("Printing UVICORN_PORT from OS" + "\n" + str(os.getenv("UVICORN_PORT")))

# Извлечение порта из аргументов командной строки
if '--port' in sys.argv:
    port_index = sys.argv.index('--port') + 1
    if port_index < len(sys.argv):
        server_port = int(sys.argv[port_index])

logger.info(f"Server IP Address: {server_ip}")
logger.info(f"Server Port: {server_port}")


@app.get("/")
async def read_root():
    return {"Hello": "World from metrics exporter!",
            "See metrics": "http://" + server_ip + ":" + str(server_port) + "/metrics"}


# Создаем экспортера с использованием конфигурации
track_health_exporter = TrackHealthExporter(track_url)
REGISTRY.register(track_health_exporter)


@app.get("/metrics")
def metrics():
    track_health_exporter.check_health()  # Обновляем статус перед возвращением метрик
    print(f"trackHealthExporter.health_status=", track_health_exporter.health_status)
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=server_port)
