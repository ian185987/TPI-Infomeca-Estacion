#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
prueba_hw.py - TPI Infomeca - Etapa 1: prueba del hardware

Objetivo: comprobar, ANTES de programar la estación, que cada parte del
circuito funciona por separado:
  1) el sensor DS18B20 (lectura de temperatura),
  2) los 3 LEDs (y averiguar qué color está en cada GPIO),
  3) el pulsador (ver qué valor lee el pin suelto y apretado).

Se basa en el ejemplo del profe (test_meca.py): mismos pines y misma forma
de leer el sensor, pero ordenado en funciones.

Cómo se corre (en la Raspberry, dentro de ~/tpi):
    python3 prueba_hw.py
"""

import RPi.GPIO as GPIO   # librería de clase para manejar los pines GPIO
import time               # para las pausas (sleep) y medir tiempo
import glob               # para buscar la carpeta del sensor sin escribir su número a mano

# ---------------------------------------------------------------------------
# Constantes de configuración (numeración BCM, igual que el ejemplo del profe)
# ---------------------------------------------------------------------------
PIN_PULSADOR = 3              # GPIO 3: tiene una resistencia pull-up fija en la placa
PINES_LED = [17, 27, 22]      # los 3 LEDs del ejemplo del profe (color a confirmar)
CARPETA_W1 = '/sys/bus/w1/devices/'   # donde Linux publica los dispositivos 1-Wire


def leer_temperatura():
    """Lee el DS18B20 y devuelve la temperatura en °C (float), o None si falla.

    El driver w1-therm del sistema operativo hace la comunicación 1-Wire por
    nosotros y deja el resultado en un archivo de texto 'w1_slave' con 2 líneas:
        f5 01 4b 46 7f ff 0c 10 84 : crc=84 YES
        f5 01 4b 46 7f ff 0c 10 84 t=31312
    - Línea 1: termina en YES si el CRC (control de errores) dio bien.
    - Línea 2: después de 't=' viene la temperatura en milésimas de °C.
    """
    # glob busca carpetas que empiecen con '28-' (28 = código de familia del
    # DS18B20). Así no dependemos del número de serie de NUESTRO sensor
    # (el del profe era 28-0316b5a9a0ff, el nuestro es 28-0516b533b8ff).
    carpetas = glob.glob(CARPETA_W1 + '28-*')
    if not carpetas:                      # lista vacía: el sensor no está conectado
        return None

    # 'with' abre el archivo y lo cierra solo al terminar el bloque
    with open(carpetas[0] + '/w1_slave', 'r') as archivo:
        lineas = archivo.readlines()

    # Si la primera línea no termina en YES, la lectura vino corrupta
    if not lineas[0].strip().endswith('YES'):
        return None

    pos = lineas[1].find('t=')            # posición donde empieza 't='
    milesimas = int(lineas[1][pos + 2:])  # lo que sigue a 't=' pasado a entero
    return milesimas / 1000.0             # 31312 -> 31.312 °C


def configurar_gpio():
    """Prepara los pines: LEDs como salida (apagados) y pulsador como entrada."""
    GPIO.setwarnings(False)         # evita avisos si el pin quedó configurado de antes
    GPIO.setmode(GPIO.BCM)          # numeración BCM (la del nombre GPIOxx, no la física)
    GPIO.setup(PIN_PULSADOR, GPIO.IN)
    for pin in PINES_LED:
        GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)   # salida, arranca apagado


def prueba_sensor():
    print("\n=== PRUEBA 1: sensor DS18B20 ===")
    print("Hago 3 lecturas. Probá apretar el sensor con los dedos: tiene que subir.")
    for i in range(3):
        temp = leer_temperatura()
        if temp is None:
            print("  Lectura", i + 1, ": ERROR (sensor no encontrado o CRC mal)")
        else:
            print("  Lectura", i + 1, ":", temp, "°C")
        time.sleep(1)   # el sensor tarda ~750 ms en convertir, no tiene sentido ir más rápido


def prueba_leds():
    print("\n=== PRUEBA 2: LEDs ===")
    print("Prendo un pin a la vez. Escribí qué color ves (o 'nada') y Enter.")
    colores = {}                       # diccionario pin -> color que vio el usuario
    for pin in PINES_LED:
        GPIO.output(pin, GPIO.HIGH)    # HIGH = 3.3 V en el pin -> el LED prende
        colores[pin] = input("  GPIO " + str(pin) + " prendido. ¿Qué color? ")
        GPIO.output(pin, GPIO.LOW)     # LOW = 0 V -> el LED se apaga

    print("  Ahora los 3 juntos durante 2 segundos...")
    for pin in PINES_LED:
        GPIO.output(pin, GPIO.HIGH)
    time.sleep(2)
    for pin in PINES_LED:
        GPIO.output(pin, GPIO.LOW)

    print("  Resultado (anotalo, lo usamos en la estación):")
    for pin, color in colores.items():
        print("    GPIO", pin, "->", color)


def prueba_pulsador():
    print("\n=== PRUEBA 3: pulsador ===")
    print("Durante 10 segundos muestro cada cambio del pin. Apretá y soltá varias veces.")
    anterior = GPIO.input(PIN_PULSADOR)
    print("  Valor con el pulsador suelto:", anterior)
    inicio = time.time()
    while time.time() - inicio < 10:
        actual = GPIO.input(PIN_PULSADOR)
        if actual != anterior:                       # solo informo cuando cambia
            print("  Cambió a", actual, "a los", round(time.time() - inicio, 2), "s")
            anterior = actual
        time.sleep(0.01)    # chequeo cada 10 ms: suficiente y no satura el procesador
    print("  Fin de la prueba del pulsador.")


# ---------------------------------------------------------------------------
# Programa principal
# ---------------------------------------------------------------------------
try:
    configurar_gpio()
    prueba_sensor()
    prueba_leds()
    prueba_pulsador()
    print("\nPruebas terminadas.")
except KeyboardInterrupt:
    # Ctrl+C: el usuario cortó el programa; no es un error
    print("\nCortado por el usuario.")
finally:
    # Se ejecuta SIEMPRE (haya error o no): deja los pines como entradas,
    # apagando los LEDs y evitando que queden configurados para el próximo programa.
    GPIO.cleanup()
