#!/usr/bin/env python3
"""
Reserva automática de pista de pádel
Polideportivo Valle de Aranguren (Bookitit API)

Ejecutar el día anterior a las 00:00 para reservar el día siguiente.

Secrets de GitHub necesarios:
  BKT_LOGIN     → tu email o teléfono
  BKT_PASSWORD  → 8 últimos dígitos de la tarjeta ciudadana

Opcionales (para lanzamiento manual):
  BKT_DATE      → fecha a reservar en YYYY-MM-DD (vacío = mañana)
  BKT_TIME      → hora preferida en HH:MM (vacío = 20:00)
  BKT_AGENDA    → ID de pista preferida (vacío = orden por defecto)
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta

import requests

# ══════════════════════════════════════════════════════════
#  CONFIGURACIÓN FIJA — API Bookitit / Aranguren
# ══════════════════════════════════════════════════════════

BASE_URL   = "https://app.bookitit.com/onlinebookings"
PUBLIC_KEY = "21a97df30a50dd9c0dac4ada2bec349dc"
SRC        = "https://www.aranguren.es/servicios/deportes/reservas-instalaciones-deportivas-de-mutilva/"
VERSION    = "87"
SERVICE_ID = "bkt587752"   # Servicio: Pádel

# Pistas en orden de preferencia (Pista 2 → 1 → 3)
PISTAS = [
    {"nombre": "Padel 2", "id": "bkt232870"},
    {"nombre": "Padel 1", "id": "bkt232760"},
    {"nombre": "Padel 3", "id": "bkt232881"},
]

# Horas en orden de preferencia si la principal está ocupada
HORAS_FALLBACK = ["19:00", "21:00", "18:00", "17:00"]

# ══════════════════════════════════════════════════════════
#  PARÁMETROS DE EJECUCIÓN (GitHub Secrets / Inputs)
# ══════════════════════════════════════════════════════════

LOGIN    = os.environ.get("BKT_LOGIN", "")
PASSWORD = os.environ.get("BKT_PASSWORD", "")

# Hora preferida (puede sobreescribirse desde workflow_dispatch)
HORA_PREFERIDA = os.environ.get("BKT_TIME", "20:00")

# Pista preferida: si se especifica, va primero; si no, usa el orden por defecto
AGENDA_PREFERIDA = os.environ.get("BKT_AGENDA", "")

# Fecha: explícita o mañana automáticamente
if os.environ.get("BKT_DATE"):
    FECHA = os.environ["BKT_DATE"]
else:
    FECHA = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

# ══════════════════════════════════════════════════════════
#  CLIENTE HTTP
# ══════════════════════════════════════════════════════════

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer":    SRC,
    "Accept":     "*/*",
})


def jsonp(text: str) -> dict:
    """Parsea respuesta JSONP: bkt_cb_xxx({...}) → dict"""
    print(f"    [DEBUG] Respuesta raw (primeros 300 chars): {text[:300]}")
    start = text.index("(") + 1
    end   = text.rindex(")")
    return json.loads(text[start:end])


def params_base(callback: str) -> dict:
    return {
        "callback":       callback,
        "type":           "default",
        "publickey":      PUBLIC_KEY,
        "lang":           "es",
        "scroll":         "false",
        "services[]":     SERVICE_ID,
        "version":        VERSION,
        "src":            SRC,
        "srvsrc":         "https://app.bookitit.com",
        "selectedPeople": "1",
        "_":              str(int(time.time() * 1000)),
    }


# ══════════════════════════════════════════════════════════
#  FUNCIONES DE LA API
# ══════════════════════════════════════════════════════════

def horas_libres(agenda_id: str) -> list[str]:
    """Devuelve lista de horas libres (HH:MM) para la pista y fecha."""
    p = params_base("bkt_cb_datetime")
    p.update({"agendas[]": agenda_id, "start": FECHA, "end": FECHA})
    r = session.get(f"{BASE_URL}/datetime/", params=p)
    r.raise_for_status()
    slots = jsonp(r.text).get("Slots", [])
    return [
        s["time"][:5]
        for s in slots
        if int(s.get("freeslots", 0)) > 0
    ]


def signin(agenda_id: str, hora: str) -> dict:
    """Login + solicitud de reserva. Devuelve la respuesta completa."""
    p = params_base("bkt_cb_signin")
    p.update({
        "agendas[]": agenda_id,
        "date":      FECHA,
        "time":      hora,
        "logintype": "email",
        "login":     LOGIN,
        "password":  PASSWORD,
        "comments":  "",
    })
    r = session.get(f"{BASE_URL}/signin/", params=p)
    r.raise_for_status()
    return jsonp(r.text)


def confirmar(agenda_id: str, hora: str, token: str) -> dict:
    """Confirmación final de la reserva."""
    p = params_base("bkt_cb_confirm")
    p.update({
        "agendas[]": agenda_id,
        "date":      FECHA,
        "time":      hora,
        "bktToken":  token,
    })
    r = session.get(f"{BASE_URL}/confirmclient/", params=p)
    r.raise_for_status()
    return jsonp(r.text)


# ══════════════════════════════════════════════════════════
#  LÓGICA PRINCIPAL
# ══════════════════════════════════════════════════════════

def main():
    print("═" * 54)
    print("  RESERVA AUTOMÁTICA PÁDEL — Polideportivo Mutilva")
    print("═" * 54)
    print(f"  Fecha:   {FECHA}")
    print(f"  Hora:    {HORA_PREFERIDA} (+ fallbacks: {', '.join(HORAS_FALLBACK)})")
    print(f"  Usuario: {LOGIN[:4]}***")
    print("═" * 54)

    if not LOGIN or not PASSWORD:
        print("\nERROR: Faltan BKT_LOGIN o BKT_PASSWORD en los Secrets")
        sys.exit(1)

    # Orden de pistas: la preferida primero (si se especificó), luego el resto
    if AGENDA_PREFERIDA:
        pistas_ordenadas = sorted(
            PISTAS,
            key=lambda p: (0 if p["id"] == AGENDA_PREFERIDA else 1)
        )
    else:
        pistas_ordenadas = PISTAS

    todas_las_horas = [HORA_PREFERIDA] + HORAS_FALLBACK

    # ── Buscar combinación pista + hora disponible ────────────────────────────
    eleccion = None   # {"pista": {...}, "hora": "HH:MM"}

    for pista in pistas_ordenadas:
        print(f"\n  Comprobando {pista['nombre']} ({pista['id']})...")
        try:
            libres = horas_libres(pista["id"])
        except Exception as e:
            print(f"    ⚠ Error consultando disponibilidad: {e}")
            continue

        if not libres:
            print(f"    Sin huecos disponibles el {FECHA}")
            continue

        print(f"    Horas libres: {', '.join(libres)}")

        for hora in todas_las_horas:
            if hora in libres:
                eleccion = {"pista": pista, "hora": hora}
                break

        if eleccion:
            if eleccion["hora"] != HORA_PREFERIDA:
                print(f"    ⚠ {HORA_PREFERIDA} ocupada → usando {eleccion['hora']}")
            break

    if not eleccion:
        print(f"\n  ✗ No hay ningún hueco disponible el {FECHA}")
        print(f"    Horas probadas: {', '.join(todas_las_horas)}")
        print(f"    Pistas probadas: {', '.join(p['nombre'] for p in pistas_ordenadas)}")
        sys.exit(1)

    pista_elegida = eleccion["pista"]
    hora_elegida  = eleccion["hora"]
    print(f"\n  → Reservando {pista_elegida['nombre']} a las {hora_elegida}...")

    # ── Login + reserva ───────────────────────────────────────────────────────
    try:
        res = signin(pista_elegida["id"], hora_elegida)
    except Exception as e:
        print(f"\n  ✗ Error en login/reserva: {e}")
        sys.exit(1)

    if res.get("errors") or res.get("exception"):
        print(f"\n  ✗ Error del servidor: {res.get('errors') or res.get('exception')}")
        sys.exit(1)

    # ── Confirmación ──────────────────────────────────────────────────────────
    token = (res.get("Access") or {}).get("bktToken")

    if token:
        try:
            confirm_res = confirmar(pista_elegida["id"], hora_elegida, token)
            localizador = (confirm_res.get("Appointment") or {}).get("locator", "N/A")
        except Exception as e:
            print(f"\n  ✗ Error en confirmación: {e}")
            sys.exit(1)
    else:
        # Algunas versiones de Bookitit confirman directamente en signin
        localizador = (res.get("Appointment") or {}).get("locator", "N/A")

    # ── Resultado ─────────────────────────────────────────────────────────────
    print()
    print("  ✅  RESERVA CONFIRMADA")
    print(f"  📅  {FECHA} a las {hora_elegida}")
    print(f"  🏓  {pista_elegida['nombre']}")
    print(f"  🔖  Localizador: {localizador}")
    print()


if __name__ == "__main__":
    main()
