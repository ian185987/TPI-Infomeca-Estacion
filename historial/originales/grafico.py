#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
grafico.py - TPI Infomeca - Parte C (lado PC)

Se conecta por socket TCP/IP a la estación (estacion_red.py, en la
Raspberry) y grafica en tiempo real cada temperatura que llega.

Cómo se corre (en la PC, en PowerShell, en la carpeta donde está este archivo):
    python grafico.py                    (busca la Raspberry como rbpi1.local)
    python grafico.py 192.168.54.105     (o por IP, si el nombre no anda)
Se termina cerrando la ventana del gráfico.
"""

import socket                       # comunicación TCP/IP
import struct                       # desempaquetar los bytes en un float
import sys                          # leer el argumento (IP o nombre)
import time                         # tiempo transcurrido para el eje X
import matplotlib.pyplot as plt     # el gráfico

HOST = sys.argv[1] if len(sys.argv) > 1 else 'rbpi1.local'
PUERTO = 5000                       # el mismo que en estacion_red.py
FORMATO = '!f'                      # el mismo que usa la Raspberry al enviar
TAMANIO = struct.calcsize(FORMATO)  # cuántos bytes ocupa un float: 4

# --- Conexión -------------------------------------------------------------
print(f"Conectando con {HOST}:{PUERTO} ...")
conexion = socket.create_connection((HOST, PUERTO), timeout=10)
# Timeout corto para recv(): si en 0.1 s no llegó nada, el programa sigue y
# atiende la ventana del gráfico. Sin esto, recv() se quedaría esperando los
# 3.5 s del ciclo y la ventana quedaría "congelada" (no se podría mover ni cerrar).
conexion.settimeout(0.1)
print("Conectado. Esperando temperaturas (cerrá la ventana para terminar).")

# --- Gráfico --------------------------------------------------------------
plt.ion()                           # modo interactivo: el gráfico se actualiza sin bloquear
figura, ejes = plt.subplots()
linea, = ejes.plot([], [], marker='o')
ejes.set_title(f"Temperatura en tiempo real ({HOST})")
ejes.set_xlabel("Tiempo desde la conexión (s)")
ejes.set_ylabel("Temperatura (°C)")
ejes.grid(True)

tiempos = []
temperaturas = []
inicio = time.time()
pendiente = b''     # bytes recibidos que todavía no forman un float completo

try:
    # Se repite mientras la ventana del gráfico siga abierta
    while plt.fignum_exists(figura.number):
        try:
            datos = conexion.recv(1024)
            if not datos:           # recv devuelve b'' cuando el otro lado cerró
                print("La Raspberry cerró la conexión.")
                break
            pendiente += datos
        except socket.timeout:
            pass                    # no llegó nada en 0.1 s: seguir

        # TCP es un "chorro" de bytes, no de mensajes: un recv() puede traer
        # medio float, uno, o varios juntos. Por eso se acumulan los bytes y
        # se sacan de a 4 (TAMANIO) mientras alcancen.
        while len(pendiente) >= TAMANIO:
            (temperatura,) = struct.unpack(FORMATO, pendiente[:TAMANIO])
            pendiente = pendiente[TAMANIO:]
            segundos = time.time() - inicio
            tiempos.append(segundos)
            temperaturas.append(temperatura)
            print(f"{segundos:7.1f} s  ->  {temperatura:.3f} °C")
            linea.set_data(tiempos, temperaturas)
            ejes.relim()            # recalcula los límites con los datos nuevos
            ejes.autoscale_view()   # y ajusta los ejes

        plt.pause(0.05)             # deja que la ventana se dibuje y responda
finally:
    conexion.close()                # liberar el socket siempre

# Si la conexión terminó con la ventana abierta, el gráfico queda en pantalla
if plt.fignum_exists(figura.number):
    plt.ioff()
    plt.show()
