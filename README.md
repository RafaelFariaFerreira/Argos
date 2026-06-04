<div align="center">

```
 █████╗ ██████╗  ██████╗  ██████╗ ███████╗
██╔══██╗██╔══██╗██╔════╝ ██╔═══██╗██╔════╝
███████║██████╔╝██║  ███╗██║   ██║███████╗
██╔══██║██╔══██╗██║   ██║██║   ██║╚════██║
██║  ██║██║  ██║╚██████╔╝╚██████╔╝███████║
╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝  ╚═════╝ ╚══════╝
```

**◉ ◉ ◉ ◉ ◉ &nbsp; Google Maps Market Intelligence &nbsp; ◉ ◉ ◉ ◉ ◉**

*The all-seeing eye of your market*

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)
![API](https://img.shields.io/badge/API-DataForSEO-4CAF50?logo=google&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-yellow)
![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20macOS%20%7C%20Windows-lightgrey)

</div>

---

## About

In Greek mythology, **Argos Panoptes** was a primordial giant cursed with a hundred eyes — never sleeping simultaneously, watching everything, missing nothing.

**Argos** brings that same tireless vigilance to market research. It extracts structured business intelligence from Google Maps for any type of business — clinics, restaurants, gyms, law firms — and exports results to CSV, ready for analysis or CRM import.

---

## Features

- **Targeted search** — search by city, state, or a specific neighborhood (geocoded automatically via OpenStreetMap)
- **Adjustable depth** — fetch anywhere from 1 to 700 results per search
- **Rich terminal UI** — color-coded tables, spinners, and panels (inspired by theHarvester)
- **First-run setup** — if no credentials are found, Argos walks you through configuration interactively
- **Structured CSV export** — results saved with parsed address components, split phone fields, rating, review count, website, coordinates, and operating hours — ready for spreadsheets, databases, or CRM import

---

## Requirements

- Python 3.10+
- A [DataForSEO](https://dataforseo.com) account with API credentials

---

## Installation

```bash
# 1. Clone the repository
git clone https://github.com/your-username/argos.git
cd argos

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt
```

---

## Configuration

Argos will detect missing credentials on first run and walk you through setup interactively:

```
⚙  First-time Setup
──────────────────────────────────────────────────
  Login (email): your@email.com
  Password: ********

  ✓ Credentials saved to .env
```

To configure manually, create a `.env` file in the project root:

```env
DATAFORSEO_LOGIN=your@email.com
DATAFORSEO_PASSWORD=your_password
```

Get your credentials at [app.dataforseo.com/api-access](https://app.dataforseo.com/api-access).

---

## Usage

```bash
python argos.py [OPTIONS]
```

Running without arguments launches **interactive mode**, which prompts for all search parameters:

```
  Categoria / termo de busca: clínicas de dermatologia estética
  Estado: São Paulo
  Cidade: São Paulo
  Bairro (opcional — Enter para pular): Pinheiros
  Raio de busca (km): 3
  Número de resultados (máximo: 700): 50
```

### CLI Options

For scripted or repeated use, all parameters can be passed as flags:

| Option | Description |
|---|---|
| `--keyword` | Search term |
| `--location` | DataForSEO location string (e.g. `'Sao Paulo,State of Sao Paulo,Brazil'`) |
| `--language` | Search language (default: `Portuguese`) |
| `--results` | Number of results to fetch (1–700) |
| `--neighborhood` | Neighborhood name — geocoded automatically via OpenStreetMap |
| `--radius` | Search radius in km when using `--neighborhood` (default: `3`) |
| `--output` | CSV output path (default: `resultados_<timestamp>.csv`) |
| `--no-export` | Print results only, skip CSV export |

### Examples

```bash
# Default search — aesthetic dermatology clinics in São Paulo
python argos.py

# Search in a specific neighborhood
python argos.py --neighborhood "Pinheiros"

# Narrow the radius to 1 km
python argos.py --neighborhood "Vila Mariana" --radius 1

# Different city + neighborhood
python argos.py \
  --location "Rio de Janeiro,State of Rio de Janeiro,Brazil" \
  --neighborhood "Ipanema"

# Fetch 100 results in a different city
python argos.py \
  --location "Rio de Janeiro,State of Rio de Janeiro,Brazil" \
  --results 100

# Different keyword with more results
python argos.py --keyword "clínica de odontologia estética" --results 50

# Save to a specific file
python argos.py --output clinicas_sp.csv

# Print results only — no CSV export
python argos.py --no-export
```

---

## Output

Results are printed as a color-coded table in the terminal and saved to a CSV file.

### CSV columns

| Column | Description |
|---|---|
| `Name` | Business name |
| `Address / Address 1` | Street and number |
| `Address / Address 2` | Complement / neighborhood |
| `Address / City` | City |
| `Address / State` | State abbreviation |
| `Address / Country` | Always `Brazil` |
| `Address / Post Code` | ZIP code (CEP) |
| `Domain Name / Link URL` | Website domain |
| `Nota Google` | Rating mapped to `RATING_3`, `RATING_4`, or `RATING_5` |
| `N Avaliações Google` | Number of Google reviews |
| `Especialidade` | Inferred from category (`DERMATOLOGIA_ESTETICA`, `ODONTOLOGIA_ESTETICA`, `OUTRO`) |
| `Whatsapp / Primary Phone *` | Calling code, country code, and number parsed from phone |
| `Id` | Generated UUID v4 |
| `Creation date` / `Last update` | Timestamp of the scrape run |

### Extra columns (scraper-specific)

| Column | Description |
|---|---|
| `Categoria` | Raw business category from Google Maps |
| `Horários` | Formatted operating hours |
| `Latitude` | Geographic latitude |
| `Longitude` | Geographic longitude |

---

## Location Format

The `--location` value must match DataForSEO's location database. The format for Brazilian cities is:

```
City,State of StateNameWithoutAccents,Brazil
```

Common examples:

```
Sao Paulo,State of Sao Paulo,Brazil
Rio de Janeiro,State of Rio de Janeiro,Brazil
Belo Horizonte,State of Minas Gerais,Brazil
Brasilia,Federal District,Brazil
Curitiba,State of Parana,Brazil
Porto Alegre,State of Rio Grande do Sul,Brazil
Salvador,State of Bahia,Brazil
Fortaleza,State of Ceara,Brazil
Recife,State of Pernambuco,Brazil
Manaus,State of Amazonas,Brazil
```

To search an entire state:

```
State of Sao Paulo,Brazil
```

---

## License

MIT — see [LICENSE](LICENSE) for details.
