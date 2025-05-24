# AI Research Agent

A Streamlit-based web application designed to assist with due diligence and research tasks by processing uploaded documents and web content, and generating comprehensive AI-powered reports.

---

## ✨ Key Features

-   **Unified Research Interface:** Single-page application for all research tasks.
-   **Multi-Format Document Upload:** Supports PDF, DOCX, TXT, and MD files.
-   **Web Content Scraping:** Integrates with a self-hosted Firecrawl OSS instance to fetch content from multiple URLs.
-   **AI-Powered Analysis:** Utilizes large language models via OpenRouter to analyze aggregated content from documents and web sources based on a user's research query.
-   **Customizable AI Persona:** Session-specific system prompts allow users to tailor the AI's analytical approach and report style.
-   **User Authentication:** Secure login and sign-up functionality using bcrypt for password hashing and YAML-based user storage.
-   **Audit Logging:** Comprehensive logging of user actions and system events.
-   **Dockerized Deployment:** Easy setup and deployment using Docker and Docker Compose.

---

## 🛠️ Technology Stack

-   **Backend & UI:** Python, Streamlit
-   **AI Integration:** OpenRouter (for LLM access)
-   **Web Scraping:** Firecrawl OSS (self-hosted)
-   **Document Processing:** PyMuPDF (for PDFs), python-docx (for DOCX)
-   **Data Handling:** PyYAML
-   **Containerization:** Docker, Docker Compose
-   **Caching (for Firecrawl):** Redis

---

## 🗺️ Project Structure

```text
.
├── config/                 # Configuration files
│   └── users.yaml          # User credentials and settings (in .gitignore)
├── logs/                   # Application and audit logs (in .gitignore)
├── output/                 # Generated reports and other outputs (in .gitignore)
├── src/                    # Core application source code
│   ├── __init__.py
│   ├── audit_logger.py     # Audit logging setup and functions
│   ├── config.py           # Centralized configuration (API keys, prompts, paths)
│   ├── firecrawl_client.py # Client for interacting with Firecrawl OSS
│   ├── init_users.py       # Script to initialize default users
│   └── openrouter.py       # Client for OpenRouter API
├── .env.example            # Example environment variables file
├── .gitignore              # Specifies intentionally untracked files for Git
├── docker-compose.yml      # Defines and runs multi-container Docker applications
├── Dockerfile              # Instructions to build the application's Docker image
├── main.py                 # Main Streamlit application script (UI and core logic)
└── requirements.txt        # Python package dependencies
```

---

## 🚀 Setup and Running the Application

This application is designed to be run using Docker and Docker Compose.

### Prerequisites
-   Docker installed: [Get Docker](https://docs.docker.com/get-docker/)
-   Docker Compose installed (usually comes with Docker Desktop).
-   A self-hosted instance of [Firecrawl OSS](https://github.com/mendableai/firecrawl) running and accessible to this application.
-   Redis instance running and accessible (for Firecrawl caching, if configured in `firecrawl_client.py`).

### Steps

1.  **Clone the Repository:**
    ```bash
    git clone <your-repository-url>
    cd <repository-directory>
    ```

2.  **Configure Environment Variables:**
    Copy the `.env.example` file to `.env` and update it with your specific configurations:
    ```bash
    cp .env.example .env
    ```
    Edit `.env` to include:
    ```env
    # OpenRouter API Configuration
    OPENROUTER_API_KEY="your_openrouter_api_key"
    # OPENROUTER_API_BASE="https://openrouter.ai/api/v1" # Default, override if needed
    # OPENROUTER_DEFAULT_MODEL="openai/gpt-4o" # Example, can be set in src/config.py

    # Firecrawl Configuration
    FIRECRAWL_API_URL="http://host.docker.internal:3002/v0/scrape" # If Firecrawl runs on host, accessible from app container
    # Or specify the direct URL if Firecrawl is elsewhere, e.g., http://<firecrawl_host>:<firecrawl_port>/v0/scrape
    # FIRECRAWL_API_KEY="your_firecrawl_api_key" # If your Firecrawl instance requires one

    # Redis Configuration (for Firecrawl client caching)
    REDIS_URL="redis://host.docker.internal:6379/0" # If Redis runs on host
    # Or specify the direct URL, e.g., redis://<redis_host>:<redis_port>/0

    # Application Settings
    PYTHONPATH="/app"
    STREAMLIT_SERVER_PORT="8501"
    # Other environment variables used by src/config.py if any
    ```
    *Note on `host.docker.internal`*: This DNS name is used to allow Docker containers to connect to services running on the host machine. Ensure your Docker version supports it. For Linux, you might need to add `--add-host=host.docker.internal:host-gateway` to the `docker run` command or equivalent in `docker-compose.yml` if not automatically resolved. The current `docker-compose.yml` might already handle this or expect Firecrawl/Redis to be on the same Docker network.

3.  **Build and Run with Docker Compose:**
    Ensure your self-hosted Firecrawl OSS and Redis services are running and accessible. The application's `docker-compose.yml` should be configured to connect to them (e.g., via a shared Docker network or using `host.docker.internal`).

    From the project root directory:
    ```bash
    docker-compose build
    docker-compose up -d
    ```

4.  **Initialize Users (First Run):**
    If `config/users.yaml` does not exist or is empty, the application will attempt to run an initialization script (`src/init_users.py`) to create default users (e.g., `admin`, `researcher`). You can also manually create users via the Sign-Up feature in the UI.

5.  **Access the Application:**
    Open your web browser and go to `http://localhost:8501` (or the port specified in your `docker-compose.yml` or `.env`).

---

## ⚙️ Configuration

-   **`src/config.py`**: Contains centralized application settings, default prompts, output formats, paths, and logging levels.
-   **Environment Variables**: API keys (OpenRouter, Firecrawl if secured), Redis URL, and other deployment-specific settings are managed via an `.env` file (see Setup section).
-   **`config/users.yaml`**: Stores user credentials (hashed passwords) and user-specific system prompts. **This file contains sensitive information and is included in `.gitignore`.**

---

## 🔥 Firecrawl OSS Integration

-   This application relies on a **self-hosted instance of Firecrawl OSS** for web scraping. You need to set up Firecrawl separately according to its documentation.
-   The `FIRECRAWL_API_URL` in your `.env` file must point to your running Firecrawl scrape endpoint.
-   The `src/firecrawl_client.py` handles communication with your Firecrawl instance and uses Redis for caching scraped results if `REDIS_URL` is configured.

---

## 📜 Logging

-   Audit logs are written to `logs/audit.log`, capturing key user actions and system events.
-   Application logs (e.g., from Streamlit, other modules) may also be configured to write to the `logs/` directory or be managed by Docker.

---


