#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
estacion.py - TPI Infomeca - Parte A: estación de monitoreo de temperatura

Etapa 3b: ciclo de medición + promedio de las últimas N lecturas.
(Las etapas siguientes le van agregando: LEDs, archivo y pulsador.)

Cómo se corre (en la Raspberry, dentro de ~/tpi):
    python3 estacion.py
Por ahora se corta con Ctrl+C (más adelante será con el pulsador).
"""

import time                       # time.monotonic() y time.sleep()
from datetime import datetime     # fecha y hora "de reloj" para mostrar
from sensor import leer_temperatura   # nuestro módulo de la etapa 3a

# ---------------------------------------------------------------------------
# Parámetros (constantes): se escriben en MAYÚSCULAS por convención
# ---------------------------------------------------------------------------
CICLO_INICIAL = 3.5     # segundos entre lecturas al arrancar (consigna)
N = 5                   # cantidad de lecturas para el promedio (consigna)
PASO_ESPERA = 0.05      # la espera se hace en pasos de 50 ms (ver esperar_fin_de_ciclo)

# ---------------------------------------------------------------------------
# Estado del programa (variables que se recuerdan entre ciclos)
# ---------------------------------------------------------------------------
# Son globales porque en la etapa 3e el hilo del pulsador también las va a
# leer y modificar (por ejemplo, cambiar 'ciclo' o poner 'en_marcha' en False).
ciclo = CICLO_INICIAL   # duración actual del ciclo, en segundos
ultimas = []            # últimas N temperaturas (la más vieja primero)
en_marcha = True        # mientras sea True, la estación sigue midiendo


def promedio(valores):
    """Devuelve el promedio de una lista de números (None si está vacía)."""
    if len(valores) == 0:
        return None
    return sum(valores) / len(valores)


def agregar_lectura(temperatura):
    """Guarda la lectura nueva y descarta la más vieja si ya hay más de N.

    Así 'ultimas' funciona como una ventana que se desliza: siempre contiene
    las N lecturas más recientes, nunca más.
    """
    ultimas.append(temperatura)     # agrega al final (la más nueva)
    if len(ultimas) > N:
        ultimas.pop(0)              # saca la primera (la más vieja)


def esperar_fin_de_ciclo(inicio_ciclo):
    """Espera hasta que pasen 'ciclo' segundos desde 'inicio_ciclo'.

    Dos decisiones importantes:
    1) Se mide desde el INICIO del ciclo, no desde que terminó la lectura.
       La lectura tarda ~0.8 s; si después esperáramos 3.5 s completos,
       el ciclo real sería de 4.3 s. Así, el ciclo dura lo que tiene que durar.
    2) Se espera en pasos cortos (50 ms) en vez de un solo sleep largo.
       En cada paso se vuelve a mirar 'ciclo' y 'en_marcha': si el pulsador
       los cambia (etapa 3e), el cambio se aplica enseguida y no al final
       del ciclo viejo.

    time.monotonic() es un reloj que solo avanza: no salta si se ajusta la
    hora del sistema (por ejemplo, cuando la Raspberry la sincroniza por
    internet). Por eso se usa para medir intervalos, en vez de la hora.
    """
    while en_marcha:
        restante = ciclo - (time.monotonic() - inicio_ciclo)
        if restante <= 0:
            break
        # Duermo un paso de 50 ms, o lo que falte si es menos. Sin el min(),
        # el último paso se pasaba de largo hasta 50 ms y cada ciclo duraba
        # ~3.52 s en vez de 3.50 s (se vio en la primera prueba).
        time.sleep(min(PASO_ESPERA, restante))


def medir_una_vez():
    """Hace un ciclo de medición completo: lee, guarda y muestra."""
    temperatura = leer_temperatura()
    hora = datetime.now().strftime('%H:%M:%S.%f')[:-3]   # hh:mm:ss.mmm

    if temperatura is None:
        # Si el sensor falla, se avisa y se saltea este ciclo: no se guarda
        # nada, para no ensuciar el promedio con un dato inválido.
        print(f"[{hora}] ERROR: no se pudo leer el sensor, se saltea el ciclo")
        return

    agregar_lectura(temperatura)
    prom = promedio(ultimas)
    print(f"[{hora}] Temperatura: {temperatura:6.3f} °C | "
          f"Promedio últimas {len(ultimas)}: {prom:6.3f} °C")


def main():
    print(f"Estación de monitoreo iniciada. Ciclo: {ciclo} s, N = {N}.")
    print("Ctrl+C para terminar.\n")
    try:
        while en_marcha:
            inicio_ciclo = time.monotonic()   # marca de tiempo del comienzo
            medir_una_vez()
            esperar_fin_de_ciclo(inicio_ciclo)
    except KeyboardInterrupt:
        print("\nEstación detenida por el usuario.")


# Solo arranca si se ejecuta este archivo directamente (igual que en sensor.py)
if __name__ == '__main__':
    main()
