import sys
from pprint import pprint
from typing import Dict, Any
import requests
import os

import uvicorn
import yaml
import logging
import socket
from fastapi import FastAPI, Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST, Counter, Gauge

app = FastAPI(debug=False)

logger = logging.getLogger(__name__)


class TrackHealthExporter:
    def __init__(self,track: Dict[str, Dict[str, Any]]) -> None:
        self.track = track
        self._requests_status = Counter(
            name="track_requests_count",
            documentation="Количество запросов статуса отправленных на бэкенд трека",
            labelnames=["backend_name", "backend_adr", "backend_port"],
        )
        self._track_status = Gauge(
            name="track_statu",
            documentation="Отслеживание работает ли бэкенд трека",
            labelnames=["backend_name", "backend_adr", "backend_port"],
        )
        self._track_disk = Gauge(
            name="track_disk",
            documentation="Пространство на диске бэкенд трека",
            labelnames=["backend_name", "backend_adr", "backend_port", "state"],
        )

        logger.info(f"TrackHealthExporter instance created with config: {self.track}")

    def check_health(self):
        for backend_name, backend_config in self.track.items():
            try:
                response = requests.get(f"{backend_config.get('protocol')}://{backend_config.get('adr')}:{backend_config.get('port')}/actuator/health/custom",
                                        timeout=1, verify=False)
                response.raise_for_status()  # Raises an error for bad responses (4xx/5xx)
                self._requests_status.labels(backend_name=backend_name, backend_adr=backend_config.get('adr'), backend_port=backend_config.get('port')).inc()
                health_data = response.json()
                if not health_data:
                    logger.warning("JSON is empty")
                    return

                if health_data.get("status") == "UP":
                    self._track_status.labels(backend_name=backend_name, backend_adr=backend_config.get('adr'), backend_port=backend_config.get('port')).set(1)
                else:
                    self._track_status.labels(backend_name=backend_name, backend_adr=backend_config.get('adr'), backend_port=backend_config.get('port')).set(0)
                if "components" in health_data and "diskSpace" in health_data["components"]:
                    if health_data["components"]["diskSpace"]["status"] == "UP":
                        self._track_disk.labels(
                            backend_name=backend_name,
                            backend_adr=backend_config.get('adr'),
                            backend_port=backend_config.get('port'),
                            state="total"
                        ).set(round(health_data["components"]["diskSpace"]["details"]["total"] / (1024 ** 3), 4))
                        self._track_disk.labels(
                            backend_name=backend_name,
                            backend_adr=backend_config.get('adr'),
                            backend_port=backend_config.get('port'),
                            state="free"
                        ).set(round(health_data["components"]["diskSpace"]["details"]["free"] / (1024 ** 3), 4))

            except requests.RequestException as e:
                logger.error(f"Request failed: {e}")
                self._track_status.labels(backend_name=backend_name, backend_adr=backend_config.get('adr'), backend_port=backend_config.get('port')).set(0)

# Указание пути к конфигу
config_path = "./config.yml"
with open(config_path, 'r') as file:
    config =  yaml.safe_load(file)

server_ip = socket.gethostbyname(socket.gethostname())
server_port = int(os.getenv("UVICORN_PORT", 8000))  # Можно также указать порт в переменной окружения
#print("Printing TRACK_SERVER_URL from OS" + "\n" + str(os.getenv("TRACK_SERVER_URL")))
#print("Printing UVICORN_PORT from OS" + "\n" + str(os.getenv("UVICORN_PORT")))

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
track_config = config.get('track', {})
track_health_exporter = TrackHealthExporter(track_config)

@app.get("/metrics")
def metrics():
    track_health_exporter.check_health()  # Обновляем статус перед возвращением метрик
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=server_port)
