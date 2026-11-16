#!/usr/bin/env python3
"""
Argos — Google Maps Market Intelligence
Named after Argos Panoptes, the all-seeing giant of Greek mythology.
"""

import argparse
import csv
import json
import os
import re
import sys
import threading
import time
import unicodedata
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv
from geopy.geocoders import Nominatim
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.prompt import IntPrompt, Prompt
from rich.rule import Rule
from rich.table import Table

# ── constants ──────────────────────────────────────────────────────────────────

VERSION = "1.0.0"
API_URL = "https://api.dataforseo.com/v3/serp/google/maps/live/advanced"

LOGO = """
 █████╗ ██████╗  ██████╗  ██████╗ ███████╗
██╔══██╗██╔══██╗██╔════╝ ██╔═══██╗██╔════╝
███████║██████╔╝██║  ███╗██║   ██║███████╗
██╔══██║██╔══██╗██║   ██║██║   ██║╚════██║
██║  ██║██║  ██║╚██████╔╝╚██████╔╝███████║
╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝  ╚═════╝ ╚══════╝"""

CSV_COLUMNS = [
    "Name",
    "Category",
    "Phone",
    "Website",
    "Rating",
    "Reviews",
    "Address",
    "Street",
    "Complement",
    "City",
    "State",
    "Postal Code",
    "Hours",
    "Latitude",
    "Longitude",
]

console = Console()

# ── banner ─────────────────────────────────────────────────────────────────────


def print_banner() -> None:
    console.print(LOGO, style="bold yellow")
    console.print()
    console.print(
        "   ◉ ◉ ◉ ◉ ◉  [bold cyan]Google Maps Market Intelligence[/bold cyan]  ◉ ◉ ◉ ◉ ◉",
        justify="center",
    )
    console.print(
        f"   [dim]v{VERSION}  ·  The all-seeing eye of your market[/dim]",
        justify="center",
    )
    console.print()
    console.print(Rule(style="dim"))
    console.print()


# ── credentials ────────────────────────────────────────────────────────────────


def ensure_credentials() -> tuple[str, str]:
    load_dotenv()
    login = os.getenv("DATAFORSEO_LOGIN", "").strip()
    password = os.getenv("DATAFORSEO_PASSWORD", "").strip()

    if login and password:
        return login, password

    console.print(
        Panel(
            "[bold]Argos[/bold] needs [cyan]DataForSEO[/cyan] API credentials to search Google Maps.\n\n"
            "  1. Create a free account at [bold]dataforseo.com[/bold]\n"
            "  2. Get your credentials at [bold]app.dataforseo.com/api-access[/bold]",
            title="[bold yellow]⚙  First-time Setup[/bold yellow]",
            border_style="yellow",
            padding=(1, 3),
        )
    )
    console.print()

    login = Prompt.ask("  [cyan]Login (email)[/cyan]")
    password = Prompt.ask("  [cyan]Password[/cyan]", password=True)

    env_path = Path(".env")
    existing = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    kept = [l for l in existing.splitlines() if not l.startswith("DATAFORSEO_")]
    kept += [f"DATAFORSEO_LOGIN={login}", f"DATAFORSEO_PASSWORD={password}"]
    env_path.write_text("\n".join(kept) + "\n", encoding="utf-8")

    console.print()
    console.print("  [bold green]✓ Credentials saved to .env[/bold green]")
    console.print()
    console.print(Rule(style="dim"))
    console.print()
    return login, password


# ── geocoding ──────────────────────────────────────────────────────────────────


def geocode_neighborhood(neighborhood: str, city: str) -> tuple[float, float]:
    geolocator = Nominatim(user_agent="argos/1.0")
    query = f"{neighborhood}, {city}, Brazil"
    location = geolocator.geocode(query, language="pt")
    if not location:
        console.print(f"\n[bold red]✗ Could not geocode '{query}'[/bold red]")
        sys.exit(1)
    console.print(
        f"  [dim]📍 {location.address}  "
        f"({location.latitude:.5f}, {location.longitude:.5f})[/dim]"
    )
    return location.latitude, location.longitude


# ── search ─────────────────────────────────────────────────────────────────────


def search_businesses(
    login: str,
    password: str,
    keyword: str,
    location: str,
    language: str,
    total_results: int,
    coordinates: tuple[float, float] | None = None,
    radius_km: int = 3,
) -> list[dict]:
    task: dict = {
        "keyword": keyword,
        "language_name": language,
        "depth": total_results,
        "device": "desktop",
    }
    if coordinates:
        lat, lng = coordinates
        task["location_coordinate"] = f"{lat},{lng},{radius_km}km"
    else:
        task["location_name"] = location

    response = requests.post(
        API_URL,
        auth=(login, password),
        headers={"Content-Type": "application/json"},
        data=json.dumps([task]),
        timeout=60,
    )
    response.raise_for_status()
    return parse_results(response.json())


# ── parsing ────────────────────────────────────────────────────────────────────


def parse_results(data: dict) -> list[dict]:
    try:
        tasks = data.get("tasks", [])
        if not tasks:
            return []

        task = tasks[0]
        status_code = task.get("status_code")
        if status_code != 20000:
            console.print(
                f"[bold red]✗ API error:[/bold red] {task.get('status_message')} "
                f"(code {status_code})"
            )
            return []

        results = task.get("result", [])
        if not results:
            return []

        businesses = []
        for item in results[0].get("items", []):
            if item.get("type") not in ("maps_search", "local_pack"):
                continue

            rating = item.get("rating") or {}
            work_hours = item.get("work_hours") or {}
            address = item.get("address") or ""

            businesses.append({
                "Name": item.get("title", ""),
                "Category": item.get("category", ""),
                "Phone": item.get("phone", ""),
                "Website": item.get("domain", ""),
                "Rating": rating.get("value", ""),
                "Reviews": rating.get("votes_count", ""),
                "Address": address,
                **_parse_br_address(address),
                "Hours": _format_hours(work_hours.get("timetable", {})),
                "Latitude": item.get("latitude", ""),
                "Longitude": item.get("longitude", ""),
            })

        return businesses

    except (KeyError, IndexError, TypeError) as exc:
        console.print(f"[bold red]✗ Parse error:[/bold red] {exc}")
        return []


def _format_hours(timetable: dict) -> str:
    if not timetable:
        return ""
    day_names = {
        "monday": "Seg", "tuesday": "Ter", "wednesday": "Qua",
        "thursday": "Qui", "friday": "Sex", "saturday": "Sáb", "sunday": "Dom",
    }
    parts = []
    for day_en, label in day_names.items():
        slots = timetable.get(day_en)
        if not slots:
            continue
        times = ", ".join(
            f"{s.get('open', {}).get('hour', '?'):02d}:{s.get('open', {}).get('minute', 0):02d}"
            f"-{s.get('close', {}).get('hour', '?'):02d}:{s.get('close', {}).get('minute', 0):02d}"
            for s in slots
        )
        parts.append(f"{label}: {times}")
    return " | ".join(parts)


# ── address parsing ────────────────────────────────────────────────────────────


def _parse_br_address(address: str) -> dict:
    """Split a Brazilian-format address line into its components.

    Addresses in other formats are left unsplit; the full line is always
    available in the "Address" column.
    """
    result = {"Street": "", "Complement": "", "City": "", "State": "", "Postal Code": ""}
    if not address:
        return result

    zip_match = re.search(r"(\d{5}-\d{3})", address)
    if zip_match:
        result["Postal Code"] = zip_match.group(1)

    addr = re.sub(r",?\s*\d{5}-\d{3}", "", address).strip().rstrip(",").strip()

    state_match = re.search(r"\s*-\s*([A-Z]{2})\s*$", addr)
    if state_match:
        result["State"] = state_match.group(1)
        addr = addr[: state_match.start()].strip()

    parts = addr.rsplit(",", 1)
    if len(parts) == 2:
        result["City"] = parts[1].strip()
        addr = parts[0].strip()

    if " - " in addr:
        street, complement = addr.split(" - ", 1)
        result["Street"] = street.strip()
        result["Complement"] = complement.strip()
    else:
        result["Street"] = addr

    return result


# ── display ────────────────────────────────────────────────────────────────────


def _rating_color(rating) -> str:
    if not rating:
        return "dim"
    try:
        r = float(rating)
        if r >= 4.5:
            return "bold green"
        elif r >= 3.5:
            return "yellow"
        else:
            return "red"
    except (ValueError, TypeError):
        return "dim"


def display_results(businesses: list[dict]) -> None:
    if not businesses:
        console.print("\n[bold red]  ✗ No results found.[/bold red]\n")
        return

    table = Table(
        box=box.ROUNDED,
        show_lines=True,
        border_style="cyan",
        header_style="bold cyan",
        title=f"[bold green]◉  {len(businesses)} result(s) found[/bold green]",
        title_justify="left",
        padding=(0, 1),
    )
    table.add_column("#", style="dim", width=3, justify="right")
    table.add_column("Name", style="bold white", max_width=34, no_wrap=False)
    table.add_column("Address", style="dim", max_width=37, no_wrap=False)
    table.add_column("Phone", style="cyan", min_width=16)
    table.add_column("Rating", justify="center", min_width=6)
    table.add_column("Reviews", justify="right", style="green", min_width=7)
    table.add_column("Website", style="blue", max_width=26, no_wrap=True)

    for i, b in enumerate(businesses, 1):
        rating = b["Rating"]
        color = _rating_color(rating)
        table.add_row(
            str(i),
            b["Name"],
            b["Address"],
            b["Phone"] or "—",
            f"[{color}]{rating or '—'}[/{color}]",
            str(b["Reviews"] or "—"),
            b["Website"] or "—",
        )

    console.print()
    console.print(table)
    console.print()


def export_csv(businesses: list[dict], output_path: str) -> None:
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(businesses)
    console.print(
        Panel(
            f"[bold green]✓ {len(businesses)} records exported[/bold green]\n\n"
            f"  [dim]→[/dim]  [cyan]{output_path}[/cyan]",
            title="[bold]Export[/bold]",
            border_style="green",
            padding=(0, 2),
        )
    )
    console.print()


# ── location format ────────────────────────────────────────────────────────────

BR_STATES = {
    "AC": "Acre", "AL": "Alagoas", "AP": "Amapa", "AM": "Amazonas", "BA": "Bahia",
    "CE": "Ceara", "DF": "Distrito Federal", "ES": "Espirito Santo", "GO": "Goias",
    "MA": "Maranhao", "MT": "Mato Grosso", "MS": "Mato Grosso do Sul",
    "MG": "Minas Gerais", "PA": "Para", "PB": "Paraiba", "PR": "Parana",
    "PE": "Pernambuco", "PI": "Piaui", "RJ": "Rio de Janeiro",
    "RN": "Rio Grande do Norte", "RS": "Rio Grande do Sul", "RO": "Rondonia",
    "RR": "Roraima", "SC": "Santa Catarina", "SP": "Sao Paulo", "SE": "Sergipe",
    "TO": "Tocantins",
}


def _strip_accents(text: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFD", text) if not unicodedata.combining(ch)
    )


def build_location(city: str, state: str) -> str:
    """Build a DataForSEO location name, e.g. 'Sao Paulo,State of Sao Paulo,Brazil'.

    Accepts a state name with or without accents, or its two-letter abbreviation.
    """
    city = _strip_accents(city.strip())
    state = _strip_accents(state.strip())
    state = BR_STATES.get(state.upper(), state)

    if state.lower() in ("distrito federal", "federal district"):
        region = "Federal District"
    elif state.lower().startswith("state of "):
        region = state
    else:
        region = f"State of {state}"

    return ",".join(part for part in (city, region, "Brazil") if part)


# ── interactive setup ──────────────────────────────────────────────────────────


def interactive_setup() -> dict:
    console.print(Rule("[cyan]Nova Busca[/cyan]", style="cyan"))
    console.print()

    keyword = ""
    while not keyword:
        keyword = Prompt.ask(
            "  [cyan]Tipo de empresa / termo de busca[/cyan] [dim](ex.: academias)[/dim]"
        ).strip()
    console.print()

    state = Prompt.ask("  [cyan]Estado[/cyan]", default="São Paulo")
    city = Prompt.ask("  [cyan]Cidade[/cyan]", default="São Paulo")
    neighborhood = Prompt.ask(
        "  [cyan]Bairro[/cyan] [dim](opcional — Enter para pular)[/dim]",
        default="",
    )

    radius = 3
    if neighborhood:
        radius = IntPrompt.ask("  [cyan]Raio de busca (km)[/cyan]", default=3)

    console.print()
    results = IntPrompt.ask(
        "  [cyan]Número de resultados[/cyan] [dim](máximo: 700)[/dim]",
        default=20,
    )
    results = max(1, min(results, 700))

    console.print()
    return {
        "keyword": keyword,
        "location": build_location(city, state),
        "city": city,
        "neighborhood": neighborhood or None,
        "radius": radius,
        "results": results,
    }


# ── main ───────────────────────────────────────────────────────────────────────


def main() -> None:
    print_banner()

    parser = argparse.ArgumentParser(
        prog="argos",
        description="Argos — Google Maps Market Intelligence",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  python argos.py\n"
            "  python argos.py --keyword 'restaurantes' --location 'Rio de Janeiro,State of Rio de Janeiro,Brazil' --results 100\n"
            "  python argos.py --keyword 'academias' --neighborhood Pinheiros --results 50\n"
            "  python argos.py --keyword 'pet shops' --results 50 --output petshops.csv\n"
        ),
    )
    parser.add_argument(
        "--keyword",
        default=None,
        help="Type of business to search for (e.g. 'academias')",
    )
    parser.add_argument(
        "--location",
        default=None,
        help="DataForSEO location string (e.g. 'Sao Paulo,State of Sao Paulo,Brazil')",
    )
    parser.add_argument(
        "--language",
        default="Portuguese",
        help="Search language (default: Portuguese)",
    )
    parser.add_argument(
        "--results",
        type=int,
        default=None,
        help="Number of results to fetch, 1–700",
    )
    parser.add_argument(
        "--neighborhood",
        default=None,
        metavar="NAME",
        help="Neighborhood name — geocoded automatically via OpenStreetMap",
    )
    parser.add_argument(
        "--radius",
        type=int,
        default=3,
        help="Search radius in km when using --neighborhood (default: 3)",
    )
    parser.add_argument(
        "--output",
        metavar="FILE",
        help="CSV output path (default: resultados_<timestamp>.csv)",
    )
    parser.add_argument(
        "--no-export",
        action="store_true",
        help="Print results only, skip CSV export",
    )
    args = parser.parse_args()

    # ── interactive or CLI mode ────────────────────────────────────────────────
    cli_mode = any([args.keyword, args.location, args.neighborhood, args.results])
    if cli_mode and not args.keyword:
        parser.error("--keyword is required when passing search flags")

    login, password = ensure_credentials()

    if cli_mode:
        keyword = args.keyword
        location = args.location or "Sao Paulo,State of Sao Paulo,Brazil"
        neighborhood = args.neighborhood
        radius = args.radius
        results = args.results or 20
        city_for_geocode = location.split(",")[0]
    else:
        params = interactive_setup()
        keyword = params["keyword"]
        location = params["location"]
        neighborhood = params["neighborhood"]
        radius = params["radius"]
        results = params["results"]
        city_for_geocode = params["city"]

    # ── search summary ─────────────────────────────────────────────────────────
    location_label = (
        f"{neighborhood}  [dim]({radius} km de raio)[/dim]"
        if neighborhood
        else location
    )
    console.print(Rule("[cyan]Buscando[/cyan]", style="cyan"))
    console.print()

    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="dim", justify="right", min_width=12)
    grid.add_column(style="bold white")
    grid.add_row("Keyword", keyword)
    grid.add_row("Localização", location_label)
    grid.add_row("Resultados", str(results))
    console.print(grid)
    console.print()

    # ── geocode ────────────────────────────────────────────────────────────────
    coordinates = None
    if neighborhood:
        coordinates = geocode_neighborhood(neighborhood, city_for_geocode)
        console.print()

    # ── fetch ──────────────────────────────────────────────────────────────────
    wait_secs = max(30, results // 2)
    result_holder: dict = {}

    def _run_search() -> None:
        try:
            result_holder["businesses"] = search_businesses(
                login, password,
                keyword, location, args.language,
                results, coordinates, radius,
            )
        except Exception as exc:
            result_holder["error"] = exc

    search_thread = threading.Thread(target=_run_search, daemon=True)
    search_thread.start()

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold cyan]Pesquisando no Google Maps…[/bold cyan]"),
            BarColumn(bar_width=40),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console,
            transient=False,
        ) as progress:
            task_id = progress.add_task("search", total=wait_secs)
            tick = 0.25
            elapsed = 0.0
            while search_thread.is_alive():
                time.sleep(tick)
                elapsed += tick
                progress.update(task_id, completed=min(elapsed, wait_secs * 0.99))
            progress.update(task_id, completed=wait_secs)
    except KeyboardInterrupt:
        console.print("\n\n[bold yellow]⚠ Busca cancelada pelo usuário.[/bold yellow]\n")
        sys.exit(0)

    if "error" in result_holder:
        exc = result_holder["error"]
        if isinstance(exc, requests.exceptions.HTTPError):
            console.print(f"\n[bold red]✗ Erro HTTP:[/bold red] {exc}")
        elif isinstance(exc, requests.exceptions.Timeout):
            console.print(
                "\n[bold red]✗ Tempo esgotado.[/bold red] "
                "Tente reduzir o número de resultados ou verifique sua conexão."
            )
        else:
            console.print(f"\n[bold red]✗ Erro inesperado:[/bold red] {exc}")
        sys.exit(1)

    businesses = result_holder.get("businesses", [])

    # ── results ────────────────────────────────────────────────────────────────
    display_results(businesses)

    if not args.no_export and businesses:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = args.output or f"resultados_{timestamp}.csv"
        export_csv(businesses, output_path)


if __name__ == "__main__":
    main()
