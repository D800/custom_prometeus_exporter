from fastapi import FastAPI, Response
import requests
import os
import yaml
from prometheus_client.metrics_core import GaugeMetricFamily
from prometheus_client import make_asgi_app, REGISTRY, generate_latest, CONTENT_TYPE_LATEST

# Create app
app = FastAPI(debug=False)


class TrivyHealthExporter:
    def __init__(self, trivy_url):
        self.trivy_url = trivy_url
        self.health_status = 0  # 0 — не работает, 1 — работает

    # def check_health(self):
    #     try:
    #         response = requests.get(f"{self.trivy_url}/healthz", timeout=5)
    #         if response.status_code == 200 and response.text.strip().lower() == "ok":
    #             self.health_status = 1
    #         else:
    #             self.health_status = 0
    #     except requests.RequestException:
    #         self.health_status = 0

    def collect(self):
        # self.check_health()  # Выполняем проверку перед сбором метрик

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
        print(f"Configuration file '{config_file}' not found. Using default values.")
        return {}  # Возвращаем пустой конфиг, если файл не найден
    with open(config_file, 'r') as file:
        return yaml.safe_load(file)


# Указание пути к конфигу
config_path = "config.yaml"
config = load_config(config_path)

# Проверка на наличие ключа "url" в конфиге
default_url = "http://localhost:4954"
trivy_url = os.getenv("TRIVY_SERVER_URL", config.get("trivy", {}).get("url", default_url))

print(f"Using Trivy URL: {trivy_url}")


@app.get("/")
async def read_root():
    return {"Hello": "World from metrics exporter!",
            "See metrics": "/metrics"}


@app.get("/metrics")
def metrics():
    print(f"Trying to get response from {trivy_url}/healthz")
    try:
        response = requests.get(f"{trivy_url}/healthz", timeout=5, verify=False)

        if response.status_code == 200 and response.text.strip().lower() == "ok":
            TrivyHealthExporter.health_status = 1
        else:
            TrivyHealthExporter.health_status = 0
        print(response, f"\nTrivyHealthExporter.health_status=", TrivyHealthExporter.health_status)
    except requests.RequestException as e:
        print(f"Request failed: {e}")  # Логирование ошибки
        TrivyHealthExporter.health_status = 0

    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# Создаем экспортера с использованием конфигурации

REGISTRY.register(TrivyHealthExporter(trivy_url))
