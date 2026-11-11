# grafico.py - TPI Infomeca - Parte C (lado PC)
# Como en el apunte SocketTCP de la cátedra: la PC es el SERVIDOR.
# Abre el puerto 30103, espera que la Raspberry se conecte y grafica cada
# temperatura que llega, en tiempo real.
#
# Se corre en la PC ANTES que la estación:
#     py -3.13 grafico.py
# La primera vez, Windows pregunta si permite el acceso a la red: aceptar
# en "Redes privadas". Se termina cerrando la ventana.

import socket
import struct
import time
import matplotlib.pyplot as plt

HOST = '0.0.0.0'                # escuchar en todas las interfaces de red de la PC
PUERTO = 30103                  # el mismo que en estacion.py

# ---------- Servidor TCP (igual que en el apunte) ----------
servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)   # IPv4 + TCP
servidor.bind((HOST, PUERTO))   # atar el socket al puerto
servidor.listen(5)              # quedar a la espera de conexiones
print(f'Esperando conexiones en el puerto {PUERTO}...')
conexion, direccion = servidor.accept()     # se traba hasta que la Raspberry se conecta
print(f'Estación conectada desde {direccion[0]}. Cerrá la ventana para terminar.')
# recv() espera como máximo 0.1 s. Sin esto se quedaría trabado los 3.5 s
# del ciclo esperando datos, y la ventana del gráfico quedaría congelada.
conexion.settimeout(0.1)

# ---------- Gráfico (igual que en el apunte: se actualiza la línea) ----------
plt.ion()                       # modo interactivo: el gráfico se actualiza sin bloquear
figura, ax = plt.subplots()
line, = ax.plot([], [], marker='o')         # línea vacía que se va llenando
ax.set_title('Temperatura en tiempo real')
ax.set_xlabel('Tiempo desde la conexión (s)')
ax.set_ylabel('Temperatura (°C)')
ax.grid(True)

tiempos = []
Ts = []
t_inicial = time.time()
pendiente = b''                 # bytes recibidos que todavía no forman una temperatura

while plt.fignum_exists(figura.number):     # mientras la ventana siga abierta
    try:
        datos = conexion.recv(4)
        if not datos:           # b'' = la Raspberry cerró la conexión
            print('La estación terminó.')
            break
        pendiente += datos
    except socket.timeout:
        pass                    # no llegó nada en 0.1 s: seguir

    # TCP es un chorro de bytes, no de mensajes: un recv() puede traer menos
    # de 4 bytes. Por eso se acumulan y se usan recién cuando hay 4 completos.
    while len(pendiente) >= 4:
        valor_Float = struct.unpack('!f', pendiente[:4])[0]
        pendiente = pendiente[4:]
        Ts.append(valor_Float)
        tiempos.append(time.time() - t_inicial)
        print(f'{tiempos[-1]:6.1f} s -> {valor_Float:.3f} °C')

        line.set_xdata(tiempos)                 # cargar los datos en la línea
        line.set_ydata(Ts)
        ax.set_xlim(0, max(tiempos) + 1)        # eje X: desde 0 hasta el último dato
        ax.relim()                              # recalcular los límites con los datos nuevos
        ax.autoscale_view()                     # ajustar el eje Y a esos límites

    plt.pause(0.1)              # deja que la ventana se dibuje y responda
    plt.draw()

conexion.close()
servidor.close()
plt.ioff()
plt.show()                      # si la estación terminó, el gráfico queda en pantalla
