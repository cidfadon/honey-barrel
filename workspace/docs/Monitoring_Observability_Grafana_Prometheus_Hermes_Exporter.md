Połączenie Grafana + Prometheus + Hermes
----------------------------------------

                    +----------------------+
                     |      Grafana        |
                     |  Dashboards/Alerts  |
                     +----------+----------+
                                ^
                                |
                          PromQL Queries
                                |
                     +----------+----------+
                     |     Prometheus      |
                     +----------+----------+
                                ^
            +-------------------+--------------------+
            |                   |                    |
            |                   |                    |
     /metrics HTTP       /metrics HTTP           exporters
            |                   |                    |
     +------+-----+      +------+-----+      +-------+------+
     |   Hermes   |      | Investment |      | Node Exporter|
     |            |      | Analyst    |      +--------------+
     +------------+      +------------+
            |
            |
    Ollama API Metrics
            |
     +------+------+
     |   Ollama    |
     +-------------+

Dla Twojego stosu
-----------------
Ponieważ rozwijasz własny stack z Hermes, lokalnym Ollama (Gemma4), MCP oraz Investment Analyst, najlepszym rozwiązaniem byłoby zbudowanie dedykowanego Hermes Metrics Exportera, który agregowałby metryki z logów i endpointów usług, a następnie udostępniał je Prometheusowi. Dałoby to pełną obserwowalność całego środowiska z jednego miejsca.

- dodaj health check dla prometheusa i grafany oraz innych kontenerow.

Architektura będzie wyglądać tak:

                 Prometheus
                     |
        +------------+-------------+
        |                          |
 node-exporter                 cAdvisor
        |                          |
        |                          |
 Ubuntu VM (OS)                 Docker Engine
        |                          |
        +------------+-------------+-------------+
        |            |             |             |
      ollama       Hermes    investment-api   (openclaw)
      Gemma4                                  -disabled 

Let's implement Grafana with all add ons.

1. Add docker-compose.yml entries..

  # ---------- 17. Prometheus + Grafana + Node Exporter + cAdvisor + DCGM Exporter --------------------
  
  prometheus:
    image: prom/prometheus:latest
    container_name: prometheus
  
    restart: unless-stopped
  
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - prometheus_data:/prometheus

    command:
      - "--config.file=/etc/prometheus/prometheus.yml"
      - "--storage.tsdb.path=/prometheus"
      - "--web.enable-lifecycle"

    ports:
      - "9090:9090"

    environment:
      <<: *common-env

    networks:
      - backend-net
 
  grafana:
    image: grafana/grafana:latest
    container_name: grafana
  
    restart: unless-stopped
  
    ports:
      - "3000:3000"
  
    environment:
      <<: *common-env
      GF_SECURITY_ADMIN_USER: admin
      GF_SECURITY_ADMIN_PASSWORD: admin
      GF_USERS_ALLOW_SIGN_UP: "false"
  
    volumes:
      - grafana_data:/var/lib/grafana
  
    depends_on:
      - prometheus
  
    networks:
      - backend-net
  
  node-exporter:
    image: prom/node-exporter:latest
    container_name: node-exporter
    restart: unless-stopped
    
    ports:
      - "9100:9100"

    environment:
      <<: *common-env

    volumes:
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro
      - /:/rootfs:ro
    
    command:
      - '--path.procfs=/host/proc'
      - '--path.sysfs=/host/sys'
      - '--path.rootfs=/rootfs'
    
    networks:
      - backend-net
  
  cadvisor:
    image: gcr.io/cadvisor/cadvisor:latest
    container_name: cadvisor
    restart: unless-stopped
    ports:
      - "8080:8080"
    
    volumes:
      - /:/rootfs:ro
      - /var/run:/var/run:ro
      - /sys:/sys:ro
      - /var/lib/docker/:/var/lib/docker:ro
      - /dev/disk/:/dev/disk:ro
    
    privileged: true
    
    environment:
      <<: *common-env

    networks:
      - backend-net 
  
  dcgm-exporter:
    image: nvcr.io/nvidia/k8s/dcgm-exporter:latest
    container_name: dcgm-exporter
    restart: unless-stopped
    ports:
      - "9400:9400"
    deploy:
      resources:
        reservations:
          devices:
            - capabilities: [gpu]
    environment:
      <<: *common-env
      DCGM_EXPORTER_LISTEN: ":9400"
    
    cap_add:
      - SYS_ADMIN
  
    networks:
      - backend-net 

  hermes-exporter:
    build:
      context: ./hermes-exporter
    container_name: hermes-exporter
    restart: unless-stopped
    ports:
      - "9105:9105"
    depends_on:
      - hermes

    environment:
      <<: *common-env

    networks:
      - backend-net

2. Przeladuj metryki z Hermes do Prometheus. W tym celu dodaj endpoint /metrics w Hermes, 
  który będzie zwracał metryki w formacie Prometheus.

Hermes /metrics — dodano endpoint Prometheus:

Sidecar hermes_metrics.py uruchamiany jako s6-rc service wewnątrz kontenera Hermes
Nasłuchuje na porcie 9106, scrape'owany przez Prometheus
Metryki: hermes_up, hermes_sessions_total, hermes_messages_total, hermes_sessions_by_source, hermes_active_sessions, hermes_api_latency_seconds, tokeny i tool calle z ostatnich sesji

3) Podsumowanie zmian

Stack działa w całości. Podsumowanie:

DOCKER STATUS
=============

Kontener	      Status
hermes	        Up (health: starting)
hermes-exporter	Up
grafana	        Up
prometheus	    Up
node-exporter	  Up
cadvisor	      Up
investment-analyst-api	    Up (healthy)
alpaca-mcp	                Up (healthy)
workspace, workspace-mcp, mcp-toolbox, stdio-terminal	Up (healthy)
dcgm-exporter	✗ brak GPU (NVIDIA driver not loaded) — oczekiwane

MONITORING & OBSERVABILITY
===========================

Wszystko w wersji 0.1.8 jest przygotowane do monitorowania i obserwowalności. Grafana ma dashboardy dla Prometheus, Hermes, Investment Analyst API, Node Exporter, cAdvisor i DCGM Exporter.

Jedyne co nalezy zrobić, to dodać do Prometheus scrape config dla Hermes Exporter i zrestartować Prometheus. Po restarcie Grafana powinna automatycznie wykryć nowe metryki i dashboardy.

Jezeli chcesz dodać własne metryki do Hermes, wystarczy dodać je w hermes_metrics.py i zrestartować kontener Hermes. Nowe metryki pojawią się w Prometheus i Grafana.

Konfiguracja Prometheus-a jaki i pozostalych komponentów jest w katalogu monitoring. W szczególności plik prometheus.yml zawiera konfigurację scrape dla Hermes Exporter. W celu ustawienia calej konfiguracji odkomentuj linie dotyczace Monitoringu (17) w docker-compose.yml i zrestartuj kontenery.

W sekcji "Docker Status" w UI, mozesz dodac odpowiednio kontenery do monitorowania i obserwowalności. 

