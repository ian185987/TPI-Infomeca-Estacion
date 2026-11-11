#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sensor.py - TPI Infomeca - Parte A, etapa 3a: lectura del DS18B20

Módulo con UNA responsabilidad: devolver la temperatura actual en °C.
La estación (estacion.py) lo va a importar con:
    from sensor import leer_temperatura

Por qué un módulo aparte:
  - Se puede probar solo, antes de que exista el resto del programa.
  - Si mañana cambia el sensor, se cambia este archivo y nada más.

Cómo funciona el DS18B20 en la Raspberry:
  El overlay 'w1-gpio' (en /boot/firmware/config.txt) activa el bus 1-Wire
  en el GPIO 4, y el driver 'w1-therm' del kernel habla con el sensor.
  Cada vez que leemos el archivo 'w1_slave', el driver le pide una
  conversión al sensor (tarda ~750 ms) y nos deja el resultado en texto:

      f5 01 4b 46 7f ff 0c 10 84 : crc=84 YES
      f5 01 4b 46 7f ff 0c 10 84 t=31312

  - Línea 1: los 9 bytes crudos + el resultado del control CRC (YES = OK).
  - Línea 2: después de 't=' la temperatura en milésimas de °C.

Prueba (en la Raspberry):  python3 sensor.py
"""

import glob    # buscar archivos/carpetas con comodines (como '28-*')
import time    # pausas y medición de tiempo (solo para la prueba)

CARPETA_W1 = '/sys/bus/w1/devices/'
REINTENTOS = 3          # cuántas veces reintentar si la lectura viene mal
VALOR_ARRANQUE = 85000  # el DS18B20 devuelve 85.000 °C si se lo lee justo al
                        # encenderse, antes de su primera conversión: es un
                        # valor de fábrica, no una medición real


def _archivo_sensor():
    """Devuelve la ruta del archivo w1_slave del primer DS18B20, o None.

    El guion bajo al principio del nombre es una convención de Python:
    indica que es una función interna del módulo, no para usar de afuera.
    """
    # '28' es el código de familia de los DS18B20: todas sus carpetas
    # empiezan con '28-'. Así el programa anda con cualquier sensor, sin
    # escribir el número de serie a mano (el nuestro es 28-0516b533b8ff).
    carpetas = glob.glob(CARPETA_W1 + '28-*')
    if not carpetas:
        return None
    return carpetas[0] + '/w1_slave'


def _leer_una_vez(ruta):
    """Hace UNA lectura. Devuelve la temperatura en °C o None si vino mal."""
    try:
        with open(ruta, 'r') as archivo:   # 'with' cierra el archivo solo
            lineas = archivo.readlines()
    except OSError:
        # Pasa si el sensor se desconecta justo mientras leemos
        return None

    # Se esperan 2 líneas y que la primera termine en YES (CRC correcto)
    if len(lineas) < 2 or not lineas[0].strip().endswith('YES'):
        return None

    # Caso especial: con el sensor desconectado a veces llegan todos los
    # bytes en 00. El CRC de puros ceros también da 0, así que el driver
    # dice YES igual. Lo detectamos mirando los bytes crudos.
    bytes_crudos = lineas[0].split(':')[0].split()
    if all(b == '00' for b in bytes_crudos):
        return None

    pos = lineas[1].find('t=')
    if pos == -1:                 # find devuelve -1 si no encuentra el texto
        return None
    milesimas = int(lineas[1][pos + 2:])

    if milesimas == VALOR_ARRANQUE:
        return None

    return milesimas / 1000.0     # 26875 -> 26.875


def leer_temperatura():
    """Devuelve la temperatura en °C (float), o None si no se pudo leer.

    Reintenta hasta REINTENTOS veces: una lectura fallida aislada (ruido
    en el cable) no debería frenar la estación. Si fallan todas, devuelve
    None y el que llama decide qué hacer (la estación saltea ese ciclo).
    """
    ruta = _archivo_sensor()
    if ruta is None:
        return None

    for _ in range(REINTENTOS):     # '_' = variable que no vamos a usar
        temperatura = _leer_una_vez(ruta)
        if temperatura is not None:
            return temperatura
    return None


# ---------------------------------------------------------------------------
# Prueba del módulo
# ---------------------------------------------------------------------------
# Este bloque corre SOLO si ejecutamos 'python3 sensor.py' directamente.
# Cuando estacion.py haga 'from sensor import leer_temperatura', Python
# pone __name__ = 'sensor' (no '__main__') y este bloque NO se ejecuta.
if __name__ == '__main__':
    print("Prueba de sensor.py: 10 lecturas seguidas. Ctrl+C para cortar.")
    print("Apretá el sensor con los dedos para ver cómo cambia.\n")
    try:
        for i in range(10):
            inicio = time.time()
            temp = leer_temperatura()
            demora = (time.time() - inicio) * 1000   # en milisegundos
            if temp is None:
                print(f"Lectura {i + 1:2d}: ERROR   (tardó {demora:4.0f} ms)")
            else:
                print(f"Lectura {i + 1:2d}: {temp:7.3f} °C (tardó {demora:4.0f} ms)")
    except KeyboardInterrupt:
        print("\nCortado por el usuario.")
