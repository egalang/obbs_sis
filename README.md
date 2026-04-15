# Odoo Custom Module: `obbs_sis`

## Overview

This is a custom Odoo 18 module named `obbs_sis`, designed to manage and extend functionalities for a School Information System (SIS). It integrates with the Odoo environment to provide features specific to managing school operations.

## Features

- Feature 1: [Brief description of a feature]
- Feature 2: [Brief description of a feature]
- Feature 3: [Brief description of a feature]

## Installation (Docker-based Deployment)

### Prerequisites

- Docker 20+ installed on your system.
- Odoo 18 and PostgreSQL 15 Docker images.

### Steps to Install

1. **Start the PostgreSQL container**:
   First, run the PostgreSQL container. The environment variables set the database name, user, and password:

   ```bash
   docker run -d \
     --name odoo-db \
     -e POSTGRES_DB=odoo \
     -e POSTGRES_USER=odoo \
     -e POSTGRES_PASSWORD=odoo \
     -v odoo-db-data:/var/lib/postgresql/data \
     postgres:15


   docker run -d \
   --name odoo \
   --link odoo-db:db \
   -p 8069:8069 \
   -v ./obbs_sis:/mnt/extra-addons \
   -e HOST=db \
   -e USER=odoo \
   -e PASSWORD=odoo \
   -e DBNAME=odoo \
   odoo:18
   ```

### Key Points:

1. **PostgreSQL Container**: The `docker run` command starts the PostgreSQL container with necessary environment variables for database name, user, and password.
2. **Odoo Container**: The Odoo container is started and linked to the PostgreSQL container. The custom module is mounted into `/mnt/extra-addons` inside the Odoo container.
3. **Module Installation**: The custom module (`obbs_sis`) can be installed via the Odoo interface once the containers are running.

This method uses `docker run` to manually set up and deploy Odoo and PostgreSQL containers without relying on Docker Compose.
