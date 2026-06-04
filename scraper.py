import argparse
import csv
import json
import os
import re
import sys
import uuid
from datetime import datetime

import requests
from dotenv import load_dotenv
from geopy.geocoders import Nominatim
from tabulate import tabulate

load_dotenv()

API_URL = "https://api.dataforseo.com/v3/serp/google/maps/live/advanced"

PHONE_COUNTRY_CODES = {"+55": "BR", "+1": "US", "+44": "GB", "+33": "FR", "+34": "ES"}

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
    # Extra columns não presentes no Twenty CRM
    "Categoria",
    "Horários",
    "Latitude",
    "Longitude",
]


def get_credentials():
    login = os.getenv("DATAFORSEO_LOGIN")
    password = os.getenv("DATAFORSEO_PASSWORD")
    if not login or not password:
        print("Erro: DATAFORSEO_LOGIN e DATAFORSEO_PASSWORD devem estar definidos no .env")
        sys.exit(1)
    return login, password


def geocode_neighborhood(neighborhood: str, city: str) -> tuple[float, float]:
    geolocator = Nominatim(user_agent="derma-scraper/1.0")
    query = f"{neighborhood}, {city}, Brazil"
    location = geolocator.geocode(query, language="pt")
    if not location:
        print(f"Erro: não foi possível geocodificar '{query}'")
        sys.exit(1)
    print(f"Bairro encontrado: {location.address} ({location.latitude:.5f}, {location.longitude:.5f})")
    return location.latitude, location.longitude


def search_clinics(
    keyword: str,
    location: str,
    language: str,
    total_results: int,
    coordinates: tuple[float, float] | None = None,
    radius_km: int = 3,
) -> list[dict]:
    login, password = get_credentials()

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

    print(f"  Buscando {total_results} resultado(s)...")
    response = requests.post(
        API_URL,
        auth=(login, password),
        headers={"Content-Type": "application/json"},
        data=json.dumps([task]),
        timeout=60,
    )
    response.raise_for_status()
    return parse_results(response.json())


def parse_results(data: dict) -> list[dict]:
    try:
        tasks = data.get("tasks", [])
        if not tasks:
            return []

        task = tasks[0]
        status_code = task.get("status_code")
        if status_code != 20000:
            print(f"Erro na task: {task.get('status_message')} (código {status_code})")
            return []

        results = task.get("result", [])
        if not results:
            return []

        items = results[0].get("items", [])
        clinics = []

        for item in items:
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
        print(f"Erro ao parsear resposta: {exc}")
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

    zip_match = re.search(r'(\d{5}-\d{3})', address)
    if zip_match:
        result["Address / Post Code"] = zip_match.group(1)

    addr = re.sub(r',?\s*\d{5}-\d{3}', '', address).strip().rstrip(',').strip()

    state_match = re.search(r'\s*-\s*([A-Z]{2})\s*$', addr)
    if state_match:
        result["Address / State"] = state_match.group(1)
        addr = addr[:state_match.start()].strip()

    parts = addr.rsplit(',', 1)
    if len(parts) == 2:
        result["Address / City"] = parts[1].strip()
        addr = parts[0].strip()

    if ' - ' in addr:
        street, complement = addr.split(' - ', 1)
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


def display_results(clinics: list[dict]):
    if not clinics:
        print("Nenhum resultado encontrado.")
        return

    display_cols = ["Nome", "Endereço", "Telefone", "Avaliação", "Nº Avaliações", "Site"]
    rows = [[c.get(col, "") for col in display_cols] for c in clinics]
    print(f"\nEncontrados {len(clinics)} resultado(s):\n")
    print(tabulate(rows, headers=display_cols, tablefmt="rounded_outline", maxcolwidths=35))


def export_csv(clinics: list[dict], output_path: str):
    if not clinics:
        return
    rows = [clinic_to_twenty_row(c) for c in clinics]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=TWENTY_CRM_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nResultados exportados para: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Scraper de clínicas de dermatologia estética via DataForSEO"
    )
    parser.add_argument(
        "--keyword",
        default="clínicas de dermatologia estética",
        help="Termo de busca (padrão: 'clínicas de dermatologia estética')",
    )
    parser.add_argument(
        "--location",
        default="Sao Paulo,State of Sao Paulo,Brazil",
        help="Localização conforme cadastro DataForSEO (ex: 'Sao Paulo,State of Sao Paulo,Brazil')",
    )
    parser.add_argument(
        "--language",
        default="Portuguese",
        help="Idioma da busca (padrão: Portuguese)",
    )
    parser.add_argument(
        "--results",
        type=int,
        default=20,
        help="Número total de resultados a buscar (padrão: 20)",
    )
    parser.add_argument(
        "--neighborhood",
        help="Bairro a buscar (ex: 'Pinheiros'). Usa geocodificação para obter coordenadas.",
    )
    parser.add_argument(
        "--radius",
        type=int,
        default=3,
        help="Raio de busca em km ao usar --neighborhood (padrão: 3)",
    )
    parser.add_argument(
        "--no-export",
        action="store_true",
        help="Não exportar resultados para CSV",
    )
    parser.add_argument(
        "--output",
        help="Caminho do arquivo CSV de saída (padrão: resultados_<timestamp>.csv)",
    )
    args = parser.parse_args()

    coordinates = None
    if args.neighborhood:
        city = args.location.split(",")[0]
        coordinates = geocode_neighborhood(args.neighborhood, city)
        print(f"Buscando: '{args.keyword}' em '{args.neighborhood}' (raio {args.radius}km), {args.results} resultados...")
    else:
        print(f"Buscando: '{args.keyword}' em '{args.location}', {args.results} resultados...")

    clinics = search_clinics(
        args.keyword,
        args.location,
        args.language,
        args.results,
        coordinates,
        args.radius,
    )
    display_results(clinics)

    if not args.no_export and clinics:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = args.output or f"resultados_{timestamp}.csv"
        export_csv(clinics, output_path)


if __name__ == "__main__":
    main()
