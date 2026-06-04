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
import uuid
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
PHONE_COUNTRY_CODES = {"+55": "BR", "+1": "US", "+44": "GB", "+33": "FR", "+34": "ES"}

LOGO = """
 █████╗ ██████╗  ██████╗  ██████╗ ███████╗
██╔══██╗██╔══██╗██╔════╝ ██╔═══██╗██╔════╝
███████║██████╔╝██║  ███╗██║   ██║███████╗
██╔══██║██╔══██╗██║   ██║██║   ██║╚════██║
██║  ██║██║  ██║╚██████╔╝╚██████╔╝███████║
╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝  ╚═════╝ ╚══════╝"""

TWENTY_CRM_COLUMNS = [
    "Account Owner (ID)",
    "Address / Address 1",
    "Address / Address 2",
    "Address / City",
    "Address / State",
    "Address / Country",
    "Address / Post Code",
    "ARR / Amount",
    "ARR / Currency",
    "Creation date",
    "Domain Name / Link URL",
    "Domain Name / Link Label",
    "Domain Name / Secondary Links",
    "Employees",
    "Especialidade",
    "Fit Markmedi",
    "Google Business Profile / Link URL",
    "Google Business Profile / Link Label",
    "Google Business Profile / Secondary Links",
    "Id",
    "ICP",
    "Instagram / Link URL",
    "Instagram / Link Label",
    "Instagram / Secondary Links",
    "Linkedin / Link URL",
    "Linkedin / Link Label",
    "Linkedin / Secondary Links",
    "Name",
    "N Avaliações Google",
    "Nota Google",
    "Próxima Ação SS",
    "Próximo contato",
    "Score",
    "Status Call",
    "Tipo de operação",
    "Last update",
    "Whatsapp / Primary Phone Calling Code",
    "Whatsapp / Primary Phone Country Code",
    "Whatsapp / Primary Phone Number",
    "Whatsapp / Additional Phones",
    # Extra columns from scraped data
    "Categoria",
    "Horários",
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


def search_clinics(
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

        clinics = []
        for item in results[0].get("items", []):
            if item.get("type") not in ("maps_search", "local_pack"):
                continue

            rating = item.get("rating") or {}
            work_hours = item.get("work_hours") or {}
            hours_str = _format_hours(work_hours.get("timetable", {}))

            clinics.append({
                "Nome": item.get("title", ""),
                "Endereço": item.get("address", ""),
                "Telefone": item.get("phone", ""),
                "Avaliação": rating.get("value", ""),
                "Nº Avaliações": rating.get("votes_count", ""),
                "Site": item.get("domain", ""),
                "Categoria": item.get("category", ""),
                "Horários": hours_str,
                "Latitude": item.get("latitude", ""),
                "Longitude": item.get("longitude", ""),
            })

        return clinics

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


# ── mapping helpers ────────────────────────────────────────────────────────────


def _nota_google(rating) -> str:
    if not rating:
        return ""
    try:
        r = float(rating)
        if r >= 4.5:
            return "RATING_5"
        elif r >= 3.5:
            return "RATING_4"
        else:
            return "RATING_3"
    except (ValueError, TypeError):
        return ""


def _especialidade(category: str) -> str:
    cat = category.lower()
    if "dermatol" in cat or "estétic" in cat or "estetica" in cat:
        return "DERMATOLOGIA_ESTETICA"
    if "odontol" in cat or "dent" in cat:
        return "ODONTOLOGIA_ESTETICA"
    return "OUTRO"


def _parse_phone(phone: str) -> tuple[str, str, str]:
    if not phone:
        return "", "", ""
    phone = phone.strip()
    for code, cc in PHONE_COUNTRY_CODES.items():
        if phone.startswith(code):
            return code, cc, phone[len(code):]
    return "", "", phone


def _parse_br_address(address: str) -> dict:
    result = {
        "Address / Address 1": "",
        "Address / Address 2": "",
        "Address / City": "",
        "Address / State": "",
        "Address / Country": "Brazil",
        "Address / Post Code": "",
    }
    if not address:
        return result

    zip_match = re.search(r"(\d{5}-\d{3})", address)
    if zip_match:
        result["Address / Post Code"] = zip_match.group(1)

    addr = re.sub(r",?\s*\d{5}-\d{3}", "", address).strip().rstrip(",").strip()

    state_match = re.search(r"\s*-\s*([A-Z]{2})\s*$", addr)
    if state_match:
        result["Address / State"] = state_match.group(1)
        addr = addr[: state_match.start()].strip()

    parts = addr.rsplit(",", 1)
    if len(parts) == 2:
        result["Address / City"] = parts[1].strip()
        addr = parts[0].strip()

    if " - " in addr:
        street, complement = addr.split(" - ", 1)
        result["Address / Address 1"] = street.strip()
        result["Address / Address 2"] = complement.strip()
    else:
        result["Address / Address 1"] = addr

    return result


def clinic_to_twenty_row(clinic: dict) -> dict:
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")
    addr = _parse_br_address(clinic.get("Endereço", ""))
    calling_code, country_code, phone_number = _parse_phone(clinic.get("Telefone", ""))
    site = clinic.get("Site", "")

    return {
        "Account Owner (ID)": "",
        **addr,
        "ARR / Amount": "",
        "ARR / Currency": "",
        "Creation date": now,
        "Domain Name / Link URL": site,
        "Domain Name / Link Label": "",
        "Domain Name / Secondary Links": "[]",
        "Employees": "",
        "Especialidade": _especialidade(clinic.get("Categoria", "")),
        "Fit Markmedi": "",
        "Google Business Profile / Link URL": "",
        "Google Business Profile / Link Label": "",
        "Google Business Profile / Secondary Links": "[]",
        "Id": str(uuid.uuid4()),
        "ICP": "",
        "Instagram / Link URL": "",
        "Instagram / Link Label": "",
        "Instagram / Secondary Links": "[]",
        "Linkedin / Link URL": "",
        "Linkedin / Link Label": "",
        "Linkedin / Secondary Links": "[]",
        "Name": clinic.get("Nome", ""),
        "N Avaliações Google": clinic.get("Nº Avaliações", ""),
        "Nota Google": _nota_google(clinic.get("Avaliação", "")),
        "Próxima Ação SS": "",
        "Próximo contato": "",
        "Score": "",
        "Status Call": "",
        "Tipo de operação": "",
        "Last update": now,
        "Whatsapp / Primary Phone Calling Code": calling_code,
        "Whatsapp / Primary Phone Country Code": country_code,
        "Whatsapp / Primary Phone Number": phone_number,
        "Whatsapp / Additional Phones": "[]",
        "Categoria": clinic.get("Categoria", ""),
        "Horários": clinic.get("Horários", ""),
        "Latitude": clinic.get("Latitude", ""),
        "Longitude": clinic.get("Longitude", ""),
    }


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


def display_results(clinics: list[dict]) -> None:
    if not clinics:
        console.print("\n[bold red]  ✗ No results found.[/bold red]\n")
        return

    table = Table(
        box=box.ROUNDED,
        show_lines=True,
        border_style="cyan",
        header_style="bold cyan",
        title=f"[bold green]◉  {len(clinics)} result(s) found[/bold green]",
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

    for i, c in enumerate(clinics, 1):
        rating = c.get("Avaliação", "")
        color = _rating_color(rating)
        table.add_row(
            str(i),
            c.get("Nome", ""),
            c.get("Endereço", ""),
            c.get("Telefone", "") or "—",
            f"[{color}]{rating or '—'}[/{color}]",
            str(c.get("Nº Avaliações", "") or "—"),
            c.get("Site", "") or "—",
        )

    console.print()
    console.print(table)
    console.print()


def export_csv(clinics: list[dict], output_path: str) -> None:
    rows = [clinic_to_twenty_row(c) for c in clinics]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=TWENTY_CRM_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    console.print(
        Panel(
            f"[bold green]✓ {len(clinics)} records exported[/bold green]\n\n"
            f"  [dim]→[/dim]  [cyan]{output_path}[/cyan]",
            title="[bold]Export[/bold]",
            border_style="green",
            padding=(0, 2),
        )
    )
    console.print()


# ── interactive setup ──────────────────────────────────────────────────────────


def interactive_setup() -> dict:
    console.print(Rule("[cyan]Nova Busca[/cyan]", style="cyan"))
    console.print()

    keyword = Prompt.ask(
        "  [cyan]Categoria / termo de busca[/cyan]",
        default="clínicas de dermatologia estética",
    )
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
        "location": f"{city},{state},Brazil",
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
            "  python argos.py --keyword 'odontologia estética' --results 50 --output clinicas.csv\n"
        ),
    )
    parser.add_argument(
        "--keyword",
        default=None,
        help="Search term",
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

    login, password = ensure_credentials()

    # ── interactive or CLI mode ────────────────────────────────────────────────
    cli_mode = any([args.keyword, args.location, args.neighborhood, args.results])

    if cli_mode:
        keyword = args.keyword or "clínicas de dermatologia estética"
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
            result_holder["clinics"] = search_clinics(
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

    clinics = result_holder.get("clinics", [])

    # ── results ────────────────────────────────────────────────────────────────
    display_results(clinics)

    if not args.no_export and clinics:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = args.output or f"resultados_{timestamp}.csv"
        export_csv(clinics, output_path)


if __name__ == "__main__":
    main()
