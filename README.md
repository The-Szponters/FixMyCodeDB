# FixMyCodeDB

An Automatically Generated Dataset of C++ Code Bugs and Fixes from GitHub for Transformer Training

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## Overview

FixMyCodeDB is a comprehensive pipeline for collecting, labeling, and storing C++ code bug-fix pairs from GitHub repositories. The dataset is designed for training transformer-based models to detect and fix code bugs automatically.

### Key Features

- **Parallel Repository Scanning** - Multi-process scraping with GitHub API token pooling
- **Automatic Bug Labeling** - Uses cppcheck static analysis to categorize bugs
- **Hybrid CLI** - Both interactive mode and command-line arguments
- **REST API** - FastAPI-based API for database access
- **LoRA Fine-Tuning** - Jupyter notebook for training models on 12GB VRAM GPUs

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         FixMyCodeDB                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐  │
│  │  CLI     │    │ Scraper  │    │ FastAPI  │    │  MongoDB │  │
│  │ (hybrid) │───▶│ (parallel│───▶│   API    │───▶│ Database │  │
│  └──────────┘    │  engine) │    └──────────┘    └──────────┘  │
│                  └──────────┘                                    │
│                       │                                          │
│              ┌────────┴────────┐                                │
│              │    Labeling     │                                │
│              │  (cppcheck +    │                                │
│              │   categories)   │                                │
│              └─────────────────┘                                │
└─────────────────────────────────────────────────────────────────┘
```

## Installation

### Prerequisites

- Python 3.10+
- Docker & Docker Compose
- GitHub Personal Access Token(s)

### Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/The-Szponters/FixMyCodeDB.git
   cd FixMyCodeDB
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Linux/macOS
   # or
   .venv\Scripts\activate     # Windows
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure GitHub tokens**

   Edit `scraper/config.json` and add your GitHub token(s):
   ```json
   {
     "github_token": "ghp_your_primary_token",
     "tokens": [
       "ghp_token_1",
       "ghp_token_2",
       "ghp_token_3"
     ],
     "max_workers": 4
   }
   ```
   > Multiple tokens enable parallel scanning without hitting rate limits.

5. **Start the services**
   ```bash
   docker-compose up -d
   ```

## Usage

### CLI - Interactive Mode

Run the CLI without arguments to enter interactive mode:

```bash
python -m cli.main
```

You'll see a menu with options:
- Scrape repositories
- Export data (JSON/CSV)
- Manual labeling
- Query entries
- Exit

### CLI - Command Line Arguments

For automation and scripting, use command-line arguments:

```bash
# Scrape repositories (parallel mode)
python -m cli.main --scan --parallel --workers 4

# Scrape with date range
python -m cli.main --scan --since 2024-01-01 --until 2024-12-31

# Export to JSON
python -m cli.main --export json --output data.json

# Export to CSV
python -m cli.main --export csv --output data.csv

# Manual labeling by entry ID
python -m cli.main --label-manual --id 507f1f77bcf86cd799439011

# Add a specific label
python -m cli.main --id 507f1f77bcf86cd799439011 --set-label memoryLeak

# Show help
python -m cli.main --help
```

### REST API

The FastAPI server runs on `http://localhost:8000` by default.

#### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/entries/` | Create a new entry |
| `GET` | `/entries/` | List entries (with limit) |
| `GET` | `/entries/{id}` | Get entry by ID |
| `PUT` | `/entries/{id}` | Update an entry |
| `DELETE` | `/entries/{id}` | Delete an entry |
| `POST` | `/entries/query/` | Query with filters |
| `GET` | `/entries/export-all` | Export all as NDJSON |
| `GET` | `/entries/export-csv` | Export all as CSV |
| `POST` | `/entries/{id}/labels/add` | Add a label |
| `POST` | `/entries/{id}/labels/remove` | Remove a label |
| `POST` | `/entries/{id}/labels/group` | Set label group |
| `GET` | `/labels/all` | Get all unique labels |
| `GET` | `/stats/` | Get database statistics |

#### Example API Calls

```bash
# Get all entries (limit 10)
curl http://localhost:8000/entries/?limit=10

# Export as CSV
curl http://localhost:8000/entries/export-csv -o entries.csv

# Add a label to an entry
curl -X POST http://localhost:8000/entries/507f1f77bcf86cd799439011/labels/add \
  -H "Content-Type: application/json" \
  -d '{"label": "memoryLeak"}'

# Get statistics
curl http://localhost:8000/stats/
```

### Scraper Configuration

Edit `scraper/config.json`:

```json
{
  "github_token": "ghp_xxx",
  "tokens": ["ghp_token1", "ghp_token2"],
  "max_workers": 4,
  "api_url": "http://fastapi:8000",
  "repos": [
    "user/repo1",
    "user/repo2"
  ],
  "since": "2020-01-01",
  "until": "2025-12-31"
}
```

### Label Categories

The labeling system categorizes bugs into 8 groups:

| Group | Description | Example Labels |
|-------|-------------|----------------|
| `memory_management` | Memory allocation issues | `memoryLeak`, `doubleFree`, `deallocuse` |
| `invalid_access` | Invalid memory access | `arrayIndexOutOfBounds`, `nullPointer` |
| `uninitialized` | Uninitialized variables | `uninitvar`, `uninitdata` |
| `concurrency` | Thread safety issues | `raceCondition`, `deadlock` |
| `logic_error` | Logic/control flow bugs | `duplicateBreak`, `unreachableCode` |
| `resource_leak` | Resource management | `resourceLeak`, `socketLeak` |
| `security_portability` | Security vulnerabilities | `bufferAccessOutOfBounds`, `integerOverflow` |
| `code_quality_performance` | Code quality issues | `redundantAssignment`, `unusedVariable` |

## Data Schema

Each entry in the database follows this structure:

```json
{
  "_id": "ObjectId",
  "code_hash": "sha256 hash of original code",
  "repo": {
    "url": "https://github.com/user/repo",
    "commit_hash": "abc123...",
    "commit_date": "2024-01-15T10:30:00Z"
  },
  "code_original": "// buggy C++ code...",
  "code_fixed": "// fixed C++ code...",
  "labels": {
    "cppcheck": ["memoryLeak", "nullPointer"],
    "groups": {
      "memory_management": true,
      "invalid_access": true,
      "uninitialized": false,
      "concurrency": false,
      "logic_error": false,
      "resource_leak": false,
      "security_portability": false,
      "code_quality_performance": false
    }
  },
  "ingest_timestamp": "2024-01-20T14:00:00Z"
}
```

## Fine-Tuning Models

A Jupyter notebook for LoRA fine-tuning is provided at `notebooks/fine_tune_lora.ipynb`.

### Requirements

- 12GB+ VRAM GPU (tested on RTX 3080/4080)
- CUDA 11.8+

### Quick Start

```bash
# Install ML dependencies
pip install transformers peft bitsandbytes datasets accelerate

# Launch Jupyter
jupyter notebook notebooks/fine_tune_lora.ipynb
```

The notebook includes:
- Data loading from MongoDB
- 80/20 train/test split
- 4-bit quantized CodeLlama base model
- LoRA configuration (r=16, alpha=32)
- Training with gradient checkpointing
- Loss/accuracy visualization

## Testing

Run the test suite with coverage:

```bash
# Run with 90% coverage threshold
./check_coverage.sh

# Run with custom threshold
./check_coverage.sh 80

# Generate HTML coverage report
./check_coverage.sh --html

# Or run pytest directly
pytest tests/ -v --cov=scraper --cov=cli --cov=fastapi_app
```

## Docker Services

| Service | Port | Description |
|---------|------|-------------|
| `fastapi` | 8000 | REST API server |
| `mongo` | 27017 | MongoDB database |
| `scraper` | - | Scraper worker (on-demand) |

### Docker Commands

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f fastapi

# Stop services
docker-compose down

# Rebuild after changes
docker-compose up -d --build
```

## Project Structure

```
FixMyCodeDB/
├── cli/                    # Command-line interface
│   ├── main.py            # Entry point (hybrid CLI)
│   ├── argparser.py       # Argument parser
│   ├── handlers.py        # Shared command handlers
│   ├── cli_app.py         # Interactive menu commands
│   ├── command_tree.py    # Command tree structure
│   └── loop.py            # Interactive loop
├── fastapi_app/           # REST API
│   ├── main.py            # FastAPI application
│   ├── crud.py            # Database operations
│   └── models.py          # Pydantic models
├── scraper/               # GitHub scraper
│   ├── main.py            # Scraper entry point
│   ├── config/            # Configuration
│   │   ├── scraper_config.py
│   │   ├── config_utils.py
│   │   └── token_pool.py  # Token pooling
│   ├── core/              # Core engine
│   │   ├── engine.py      # Scraping logic
│   │   └── parallel.py    # Parallel execution
│   ├── labeling/          # Bug labeling
│   │   ├── labeler.py
│   │   ├── analyzers.py
│   │   └── config_mapper.py
│   └── network/           # Network/API
│       └── server.py
├── notebooks/             # Jupyter notebooks
│   └── fine_tune_lora.ipynb
├── tests/                 # Test suite
├── mongo/                 # MongoDB setup
├── docker-compose.yaml
├── requirements.txt
└── check_coverage.sh
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feat/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feat/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [cppcheck](http://cppcheck.net/) - Static analysis tool for C/C++
- [CodeLlama](https://github.com/facebookresearch/codellama) - Base model for fine-tuning
- [PEFT](https://github.com/huggingface/peft) - Parameter-Efficient Fine-Tuning
