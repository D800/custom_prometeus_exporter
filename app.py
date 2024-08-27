from fastapi import FastAPI, Response
import requests
import os
import yaml
import logging
from prometheus_client.metrics_core import GaugeMetricFamily
from prometheus_client import REGISTRY, generate_latest, CONTENT_TYPE_LATEST

# Create app
app = FastAPI(debug=False)

# Настройка логгера
logger = logging.getLogger("uvicorn.info")  # Используем логгер Uvicorn с уровнем INFO

class TrivyHealthExporter:
    def __init__(self, trivy_url):
        self.trivy_url = trivy_url
        self.health_status = 0  # 0 — не работает, 1 — работает
        logger.info(f"TrivyHealthExporter instance created with URL: {self.trivy_url}")

    def check_health(self):
        try:
            response = requests.get(f"{self.trivy_url}/healthz", timeout=2, verify=False)
            if response.status_code == 200 and response.text.strip().lower() == "ok":
                self.health_status = 1
            else:
                self.health_status = 0
        except requests.RequestException:
            self.health_status = 0

    def collect(self):
        self.check_health()  # Выполняем проверку перед сбором метрик

        health_metric = GaugeMetricFamily(
            "trivy_health_status",
            "Состояние здоровья сервера Trivy (1 — работает, 0 — не работает)",
            labels=["service"]
        )

        health_metric.add_metric(["trivy"], self.health_status)
        yield health_metric


# Функция для чтения конфигурации из файла
def load_config(config_file):
    if not os.path.exists(config_file):
        logger.warning(f"Configuration file '{config_file}' not found. Using default values.")
        return {}  # Возвращаем пустой конфиг, если файл не найден
    with open(config_file, 'r') as file:
        return yaml.safe_load(file)


# Указание пути к конфигу
config_path = "config.yml"
config = load_config(config_path)

# Проверка на наличие ключа "url" в конфиге
default_url = "http://localhost:4954"
trivy_url = default_url
url_source = "default_url"


if "TRIVY_SERVER_URL" in os.environ:
    trivy_url = os.getenv("TRIVY_SERVER_URL")
    url_source = "environment variable TRIVY_SERVER_URL"
elif config.get("trivy", {}).get("url"):
    trivy_url = config.get("trivy", {}).get("url")
    url_source = "configuration file config.yml"

logger.info(f"Using Trivy URL: {trivy_url} (source: {url_source})")


@app.get("/")
async def read_root():
    return {"Hello": "World from metrics exporter!",
            "See metrics": "/metrics"}


# Создаем экспортера с использованием конфигурации
trivy_health_exporter = TrivyHealthExporter(trivy_url)
REGISTRY.register(trivy_health_exporter)


@app.get("/metrics")
def metrics():
    trivy_health_exporter.check_health()  # Обновляем статус перед возвращением метрик
    print(f"TrivyHealthExporter.health_status=", trivy_health_exporter.health_status)
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
