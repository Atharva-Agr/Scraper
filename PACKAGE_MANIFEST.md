# LinenGrass Scraper Desktop + AI Package Manifest

This package contains the desktop Python version of LinenGrass Scraper and the setup needed to run it with local AI.

## User-facing files

- `README_START_HERE.md` — simple usage guide
- `INSTALL_LINENGRASS_SCRAPER.bat` — first-time setup
- `LINENGRASS_SCRAPER.bat` — starts the app after setup
- `CHECK_LINENGRASS_SCRAPER.bat` — checks the setup
- `exports/` — exported CSV files

## App files

- `app.py`
- `app_state.py`
- `pipeline.py`
- `discovery.py`
- `url_utils.py`
- `hotel_scraper.py`
- `contacts.py`
- `validation.py`
- `schema.py`
- `cache_utils.py`
- `purge_utils.py`
- `config.py`
- `main.py`

## Setup files

- `requirements.txt`
- `.env.example`
- `setup_windows.ps1`
- `install_ai_ollama.ps1`
- `setup_all_windows.ps1`
- `check_install.ps1`
- `create_desktop_shortcut.ps1`
- `.gitignore`

## Data folders

- `data/`
- `data/hotel_cache.json`
- `data/purge_list.json`
- `data/search_lists/`
- `data/run_history/`
- `exports/`

## AI

The package includes the local AI setup scripts. The actual model weights are downloaded during setup through Ollama.

Default model:

```text
qwen2.5:7b
```
