# LinenGrass Scraper — Start Here

LinenGrass Scraper is a desktop app for scraping hotel information, reviewing hotel contacts, and exporting CSV contact lists.

You do not need to edit the code to use it.

---

## First-time setup

1. Extract the ZIP folder.
2. Open the extracted folder.
3. Double-click:

```text
INSTALL_LINENGRASS_SCRAPER.bat
```

The installer will set up:

- the Python app environment,
- the required browser tools,
- Ollama,
- the local AI model,
- the LinenGrass Scraper desktop shortcut.

The AI model download can take a while because it is several GB.

---

## Normal use

After setup, open LinenGrass Scraper like a normal app.

Use either:

```text
LinenGrass Scraper desktop shortcut
```

or double-click:

```text
LINENGRASS_SCRAPER.bat
```

You do not need to run the installer again unless you move the folder or reset the app.

---

## Basic workflow

### 1. Search

Enter:

- location,
- area,
- hotel type,
- any extra requirements,
- number of contacts wanted.

Use **Partial Search** for a quick test.

Use **Complete Search** when you want broader coverage of the area.

### 2. Results

Review the hotels found by the scraper.

You can:

- approve hotels,
- reject hotels,
- remove hotels from the current list,
- view hotel phone/email/website/details,
- check scrape status.

### 3. Contacts

Review contacts found for each hotel.

Contacts are grouped as:

- confirmed contacts,
- possible contacts,
- doubtful/debug contacts.

Move contacts between groups before exporting.

### 4. Lists

Each search can be saved as its own list.

Use this page to:

- open old lists,
- switch between lists,
- merge lists,
- save the current list.

### 5. Export

Export CSV files for:

- hotels,
- confirmed contacts,
- possible contacts,
- combined lead lists.

CSV files are saved in:

```text
exports
```

---

## Good first test

For the first run, keep it small:

```text
Complete Search: off
Target hotels: 2 or 3
Contact search depth: 1 or 2
```

Once that works, try a larger or complete search.

---

## If the app does not open

Double-click:

```text
CHECK_LINENGRASS_SCRAPER.bat
```

That checks the Python setup and local AI setup.

---

## If the AI is not working

Open PowerShell in the LinenGrass Scraper folder and run:

```powershell
ollama list
ollama pull qwen2.5:7b
```

Then open the app again.

---

## Files you normally use

For normal use, you only need these:

```text
INSTALL_LINENGRASS_SCRAPER.bat   first-time setup
LINENGRASS_SCRAPER.bat           open the app
CHECK_LINENGRASS_SCRAPER.bat     check/fix setup
exports                          exported CSV files
```

The other files are app files and should be left in the folder.
