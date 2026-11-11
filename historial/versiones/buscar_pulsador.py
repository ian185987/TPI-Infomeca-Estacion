#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
buscar_pulsador.py - TPI Infomeca - Etapa 1 (diagnóstico)

En prueba_hw.py el GPIO 3 no cambió al apretar el pulsador, así que no
sabemos a qué pin está conectado. Este script lee TODOS los GPIO libres
durante 20 segundos y avisa cuál cambia cuando apretás el pulsador.

Es seguro: solo configura pines como ENTRADA (leer no puede dañar nada).
Se saltean:
  - GPIO 4: lo usa el sensor DS18B20 (bus 1-Wire)
  - GPIO 17, 22, 27: son los LEDs (ya confirmados)
"""

import RPi.GPIO as GPIO
import time

PINES_OCUPADOS = [4, 17, 22, 27]
# En la Raspberry Pi 3 los GPIO usables van del 2 al 27
PINES_A_PROBAR = [p for p in range(2, 28) if p not in PINES_OCUPADOS]

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)

# Cada pin como entrada con la resistencia pull-up INTERNA activada.
# Pull-up = el pin queda en 1 cuando no hay nada conectado, así no "flota"
# leyendo valores al azar. Si el pulsador está en ese pin, al apretarlo
# el valor cambia, sin importar si el circuito lo lleva a GND o a 3.3 V.
for pin in PINES_A_PROBAR:
    GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# Guardo el valor inicial de cada pin en un diccionario pin -> valor
anteriores = {pin: GPIO.input(pin) for pin in PINES_A_PROBAR}

print("Durante 20 segundos: apretá y soltá el pulsador varias veces.")
try:
    inicio = time.time()
    while time.time() - inicio < 20:
        for pin in PINES_A_PROBAR:
            actual = GPIO.input(pin)
            if actual != anteriores[pin]:
                print("  GPIO", pin, "cambió de", anteriores[pin], "a", actual)
                anteriores[pin] = actual
        time.sleep(0.01)
    print("Fin. Si no apareció ningún GPIO, el pulsador no llega a ningún pin:")
    print("revisá los cables del pulsador en el protoboard.")
except KeyboardInterrupt:
    print("\nCortado por el usuario.")
finally:
    GPIO.cleanup()
