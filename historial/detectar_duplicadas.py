#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
detectar_duplicadas.py - TPI Infomeca - herramienta de diagnóstico

Recorre registro_temperaturas.csv y calcula el tiempo entre cada lectura y
la anterior. Marca:
  - SOSPECHOSA: dos lecturas separadas por 1 s o menos. El ciclo mínimo es
    2.5 s, así que solo puede ser una medición de más (la condición de
    carrera de estacion3.py).
  - REINICIO: más de 15 s sin lecturas (el ciclo máximo es 10 s), o sea que
    se cortó el programa y se volvió a arrancar. No es un error, pero
    separa una "corrida" de la siguiente.

Ojo: el CSV guarda la hora con segundos enteros (hh:mm:ss). Una diferencia
real de 0.86 s puede aparecer como 0 s o 1 s según dónde caiga el segundo;
por eso el umbral es "1 s o menos" y no "menos de 1 s".

Cómo se corre (en la Raspberry, dentro de ~/tpi):
    python3 detectar_duplicadas.py
"""

import csv                        # lee archivos CSV columna por columna
from datetime import datetime     # convierte "2026-11-09 01:54:01" en un instante

ARCHIVO = 'registro_temperaturas.csv'
UMBRAL_DUPLICADA = 1      # segundos: separación igual o menor es sospechosa
UMBRAL_REINICIO = 15      # segundos: separación mayor es un reinicio del programa

sospechosas = 0
reinicios = 0
anterior = None           # instante de la lectura anterior

with open(ARCHIVO, 'r', encoding='utf-8') as archivo:
    # DictReader usa la primera línea (el encabezado) como nombres de columna:
    # cada fila llega como un diccionario {'fecha': ..., 'hora': ..., ...}
    lector = csv.DictReader(archivo)
    for numero, fila in enumerate(lector, start=2):   # línea 1 = encabezado
        instante = datetime.strptime(fila['fecha'] + ' ' + fila['hora'],
                                     '%Y-%m-%d %H:%M:%S')
        if anterior is not None:
            # Restar dos datetime da un 'timedelta'; total_seconds() lo pasa a segundos
            separacion = (instante - anterior).total_seconds()
            if separacion <= UMBRAL_DUPLICADA:
                sospechosas += 1
                print(f"SOSPECHOSA  línea {numero}: {fila['hora']} "
                      f"a {separacion:.0f} s de la anterior "
                      f"({fila['temperatura']} °C, {fila['tendencia']})")
            elif separacion > UMBRAL_REINICIO:
                reinicios += 1
                print(f"REINICIO    línea {numero}: {fila['hora']} "
                      f"(pasaron {separacion:.0f} s sin lecturas)")
        anterior = instante

print()
print(f"Lecturas sospechosas (duplicadas): {sospechosas}")
print(f"Reinicios del programa:            {reinicios}")
