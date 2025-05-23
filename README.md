# Monitoring a PostGIS Database (with Prometheus and Grafana)

This repository contains a Dockerized application for calculating routes using **pgRouting** on a **PostgreSQL/PostGIS** database, with connection pooling via **PgBouncer**, a **Flask API** for interacting with the routing service, a **network creation script**, and a monitoring stack using **Prometheus** and **Grafana**. The application is designed for testing the monitoring.

## Overview
The application provides a solution for geospatial routing:
- **PostgreSQL/pgRouting**: Stores and processes geospatial data with PostGIS and pgRouting extensions for route calculations.
- **PgBouncer**: Manages connection pooling to optimize database performance under high load.
- **Flask API**: Exposes endpoints to interact with the routing service (e.g., compute routes via `pgr_dijkstra`).
- **Creator Script**: Populates the database with network data (e.g., graph edges in the `streets` table).
- **Monitoring**: Uses Prometheus and Grafana to monitor database performance and API usage, with metrics collected via `postgres-exporter`.

The database (`qc_routing`) is preconfigured with PostGIS and pgRouting extensions, and the Flask API connects to it through PgBouncer for efficient connection management.

## Services
The `docker-compose.yml` defines the following services:

1. **db** (`pgrouting/pgrouting:latest`):
   - PostgreSQL with PostGIS and pgRouting extensions.
   - Stores the `qc_routing` database for geospatial data.
   - Custom configuration via `postgresql.conf` and initialization via `init.sql`.

2. **pgbouncer** (`edoburu/pgbouncer:v1.24.0-p1`):
   - Connection pooler for PostgreSQL, reducing database load.
   - Configured via `pgbouncer.ini` and `userlist.txt`.
   - Exposes port `5432` for client connections.

3. **flask-app** (custom-built):
   - Flask API for routing queries, built from `./flask/Dockerfile`.
   - Connects to `qc_routing` via PgBouncer.
   - Exposes port `5000` for HTTP requests.

4. **creator** (custom-built):
   - Python script (`create_network.py`) to populate the `ways` table with network data.
   - Built from `./creator/Dockerfile`.

5. **postgres-exporter** (`prometheuscommunity/postgres-exporter`):
   - Collects PostgreSQL metrics (e.g., query counts, connection stats) for Prometheus.
   - Exposes port `9187`.

6. **prometheus** (`prom/prometheus`):
   - Time-series database for collecting and storing metrics.
   - Configured via `prometheus.yml`.
   - Exposes port `9090`.

7. **grafana** (`grafana/grafana`):
   - Visualization platform for monitoring database and API performance.
   - Exposes port `3000` (default credentials: `admin`/`admin`).

## Prerequisites
- **Docker** and **Docker Compose** installed.
- **Git** to clone the repository.
- A `.env` file with the following variables:
  ```env
  POSTGRES_QC_USER=qc_user
  POSTGRES_QC_PASSWORD=qc_password
  POSTGRES_QC_DB=qc_routing
  ```

## Setup
1. **Clone the repository**:
   ```bash
   git clone https://github.com/voirinprof/gis_postgis_monitoring.git
   cd gis_postgis_monitoring
   ```

2. **Create the `.env` file**:
   ```bash
   echo "POSTGRES_QC_USER=qc_user" >> .env
   echo "POSTGRES_QC_PASSWORD=qc_password" >> .env
   echo "POSTGRES_QC_DB=qc_routing" >> .env
   ```

3. **Ensure configuration files**:
   - `./postgis/init.sql`: Initializes the `qc_routing` database with PostGIS and pgRouting extensions.
     ```sql
     CREATE EXTENSION IF NOT EXISTS postgis;
     CREATE EXTENSION IF NOT EXISTS pgrouting;
     CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
     ```
   - `./postgis/postgresql.conf`: Custom PostgreSQL settings (e.g., `shared_preload_libraries = 'pg_stat_statements'`).
   - `./postgis/pgbouncer.ini`: PgBouncer configuration.
   - `./postgis/userlist.txt`: PgBouncer user credentials.
   - `./prometheus.yml`: Prometheus scraping configuration.

4. **Start the services**:
   ```bash
   docker-compose up -d
   ```

5. **Verify services**:
   - PostgreSQL (via PgBouncer): `psql -h localhost -p 5432 -U qc_user -d qc_routing`
   - Flask API: `curl http://localhost:5000/<endpoint>`
   - Prometheus: `http://localhost:9090`
   - Grafana: `http://localhost:3000` (login: `admin`/`admin`)

## Usage
1. **Populate the network**:
   - The `creator` service runs `create_network.py` to populate the `ways` table with graph data.
   - To rerun: `docker-compose restart creator`.

2. **Query the Flask API**:
   - Send HTTP requests to compute routes:
     ```bash
     curl http://localhost:5000/<routing-endpoint>
     ```
   - Example endpoint (if implemented): `/findpath?start=611+RUE+POULIN&end=528+RUE+LAURIER` to compute a path using `pgr_dijkstra`.

3. **Access the database**:
   - Connect via PgBouncer:
     ```bash
     docker-compose exec postgres psql -h pgbouncer -p 5432 -U qc_user -d qc_routing
     ```
   - Run a pgRouting query:
     ```sql
     SELECT * FROM pgr_dijkstra('SELECT gid AS id, source, target, length AS cost FROM ways', 1, 2, directed => true);
     ```

4. **Monitor performance**:
   - See the [Monitoring](#monitoring) section below.

## Monitoring
The repository includes a monitoring stack to track database and API performance.

It is possible to use both of them or just one solution.

### Prometheus
- Access: `http://localhost:9090`
- Metrics collected by `postgres-exporter` (port `9187`) include:
  - `pg_stat_database_tup_fetched`: Rows fetched from `qc_routing`.
  - Example PromQL query:
    ```promql
    rate(pg_stat_database_tup_fetched{datname="qc_routing"}[5m])
    ```

### Grafana
- Access: `http://localhost:3000`
- Configure a **PostgreSQL** data source to monitor `qc_routing` directly:
  - Host: `pgbouncer:5432`
  - Database: `qc_routing`
  - User: `qc_user`
  - Password: `qc_password`
  - SSL Mode: `disable`

#### Key Metrics to Monitor
Create a Grafana dashboard with the following SQL queries:

1. **Number of Active Connections**:
   ```sql
   SELECT
    extract(epoch from now()) AS time,
    COUNT(*) AS active_connections
    FROM pg_stat_activity
    WHERE datname = 'qc_routing' AND state = 'active'
    GROUP BY time;
   ```
   - Tracks active connections to `qc_routing` .

2. **Total Queries Executed**:
   ```sql
   SELECT
    extract(epoch from now()) AS time,
    SUM(calls) AS total_queries
    FROM pg_stat_statements
    WHERE dbid IN (SELECT oid FROM pg_database WHERE datname = 'qc_routing')
    GROUP BY time;
   ```
   - Monitors the number of queries.

3. **Average Query Execution Time**:
   ```sql
   SELECT
    extract(epoch from now()) AS time,
    AVG(mean_exec_time) AS avg_exec_time_ms
    FROM pg_stat_statements
    WHERE dbid IN (SELECT oid FROM pg_database WHERE datname = 'qc_routing')
    GROUP BY time;
   ```
   - Tracks query performance.


## Directory Structure
```
├── docker-compose.yml        # Defines all services
├── .env                     # Environment variables
├── postgis/
│   ├── init.sql             # Database initialization (PostGIS, pgRouting, pg_stat_statements)
│   ├── postgresql.conf      # PostgreSQL configuration
│   ├── pgbouncer.ini        # PgBouncer configuration
│   ├── userlist.txt         # PgBouncer user credentials
├── flask/
│   ├── Dockerfile           # Flask API build
│   ├── app.py               # Flask application code
├── creator/
│   ├── Dockerfile           # Creator script build
│   ├── create_network.py    # Script to populate network data
├── data/                    # Mounted for creator data
├── logs/                    # Mounted for Flask logs
├── prometheus.yml           # Prometheus configuration
```

## Contributing
Contributions are welcome! Please:
1. Fork the repository.
2. Create a feature branch: `git checkout -b feature-name`
3. Commit changes: `git commit -m "Add feature"`
4. Push to the branch: `git push origin feature-name`
5. Open a pull request.

## License
This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.