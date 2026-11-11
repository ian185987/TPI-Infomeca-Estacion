# grafico.py - TPI Infomeca - Parte C (lado PC)
# Se conecta a la estación de la Raspberry y grafica cada temperatura que llega.
#
# Se corre en la PC:
#     py -3.13 grafico.py                  (busca la Raspberry como rbpi1.local)
#     py -3.13 grafico.py 192.168.54.105   (o por IP, si el nombre no anda)
# Se termina cerrando la ventana.

import socket
import struct
import sys
import time
import matplotlib.pyplot as plt

# Si se escribió una IP al correrlo, se usa esa; si no, el nombre de la Raspberry
HOST = sys.argv[1] if len(sys.argv) > 1 else 'rbpi1.local'
PUERTO = 5000                   # el mismo que en estacion.py

conexion = socket.create_connection((HOST, PUERTO))
# recv() espera como máximo 0.1 s. Sin esto se quedaría trabado los 3.5 s
# del ciclo esperando datos, y la ventana del gráfico quedaría congelada.
conexion.settimeout(0.1)
print('Conectado. Cerrá la ventana para terminar.')

plt.ion()                       # modo interactivo: el gráfico se actualiza sin bloquear
figura = plt.figure()
tiempos = []
temperaturas = []
inicio = time.time()
pendiente = b''                 # bytes recibidos que todavía no forman una temperatura

while plt.fignum_exists(figura.number):     # mientras la ventana siga abierta
    try:
        datos = conexion.recv(1024)
        if not datos:           # b'' = la Raspberry cerró la conexión
            print('La estación terminó.')
            break
        pendiente += datos
    except socket.timeout:
        pass                    # no llegó nada en 0.1 s: seguir

    # TCP es un chorro de bytes, no de mensajes: un recv() puede traer medio
    # número o varios juntos. Por eso se acumulan y se sacan de a 4 bytes.
    while len(pendiente) >= 4:
        temperatura = struct.unpack('!f', pendiente[:4])[0]
        pendiente = pendiente[4:]
        tiempos.append(time.time() - inicio)
        temperaturas.append(temperatura)
        print(f'{tiempos[-1]:6.1f} s -> {temperatura:.3f} °C')

        plt.cla()               # borrar y volver a dibujar con el dato nuevo
        plt.plot(tiempos, temperaturas, marker='o')
        plt.title(f'Temperatura en tiempo real ({HOST})')
        plt.xlabel('Tiempo desde la conexión (s)')
        plt.ylabel('Temperatura (°C)')
        plt.grid(True)

    plt.pause(0.05)             # deja que la ventana se dibuje y responda

conexion.close()
plt.ioff()
plt.show()                      # si la estación terminó, el gráfico queda en pantalla
