"""Script CLI para enviar alertas a Telegram cuando falla un flujo de GitHub Actions."""
import argparse
import sys
from pathlib import Path

# Añadir raíz al sys.path para importar core
RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from core.alerts import notificar_fallo

def main():
    parser = argparse.ArgumentParser(description="Notificador de fallos de GitHub Actions a Telegram")
    parser.add_argument("--job", default="Desconocido", help="Nombre del flujo de trabajo o paso")
    parser.add_argument("--detalle", default="", help="Información adicional del error")
    args = parser.parse_args()

    exito = notificar_fallo(args.job, args.detalle)
    if exito:
        print(f"✅ Alerta de error para '{args.job}' enviada a Telegram.")
    else:
        print("⚠️ No se pudo enviar la alerta a Telegram (revisa tokens/conexión).")

if __name__ == "__main__":
    main()
