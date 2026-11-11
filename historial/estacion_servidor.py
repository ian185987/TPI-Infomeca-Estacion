# estacion.py - TPI Infomeca - Partes A y C: estación de monitoreo de temperatura
#
# - Lee el DS18B20 cada 'ciclo' segundos (3.5 s al arrancar).
# - Muestra la lectura y el promedio de las últimas N = 5.
# - Semáforo de tendencia: rojo = ALTA, amarillo = ESTABLE, verde = BAJA,
#   los 3 prendidos = SIN_DATOS (todavía no hay N lecturas).
# - Destello de 50 ms de los 3 LEDs al final de cada ciclo.
# - Registra cada lectura en registro_temperaturas.csv.
# - Pulsador (por interrupciones): mientras está apretado destella 1 vez por
#   segundo; al soltarlo, menos de 1 s termina y si no cambia el ciclo.
# - Parte C (como en el apunte SocketTCP de la cátedra): la Raspberry es el
#   CLIENTE. Se conecta al servidor que abre la PC (grafico.py) en el puerto
#   30103 y le envía cada temperatura. Sin PC, todo funciona igual.
#
# Se corre desde su carpeta:
#     python3 estacion.py                  (solo Parte A, sin red)
#     python3 estacion.py 192.168.54.10    (con la IP de la PC: Partes A y C)

import os
import sys                  # Parte C: leer la IP de la PC escrita al correrlo
import time
import threading
import socket               # Parte C: comunicación TCP/IP
import struct               # Parte C: empaquetar la temperatura en bytes
from datetime import datetime
import RPi.GPIO as GPIO
from sensor import leer_temperatura

# ---------- Constantes ----------
N = 5                       # lecturas para el promedio
X = 1.0                     # umbral de la tendencia, en %
LED_ROJO = 22
LED_AMARILLO = 17
LED_VERDE = 27
PULSADOR = 3                # pull-up: suelto = 1, apretado = 0
ARCHIVO = 'registro_temperaturas.csv'
PUERTO = 30103              # Parte C: el mismo puerto que en el apunte y en grafico.py
# Parte C: IP de la PC (servidor). Si no se escribe, la estación no usa la red.
IP_PC = sys.argv[1] if len(sys.argv) > 1 else None

# ---------- Variables compartidas entre hilos ----------
ciclo = 3.5                 # segundos entre lecturas (lo cambia el pulsador)
en_marcha = True            # False = terminar el programa
tendencia = 'SIN_DATOS'
ultimas = []                # últimas N temperaturas
estado_pulsador = 1         # último estado del pulsador, ya sin rebotes
pulsando = False            # True mientras el pulsador está apretado
instante_apretado = 0.0     # cuándo se apretó
conexion = None             # Parte C: socket conectado con la PC (None = no hay PC)

cerrojo_leds = threading.Lock()   # un solo hilo por vez puede tocar los LEDs
despertar = threading.Event()     # "alarma" con la que el pulsador despierta
                                  # al hilo principal mientras espera


# ---------- LEDs ----------
def poner_leds(rojo, amarillo, verde):
    GPIO.output(LED_ROJO, rojo)
    GPIO.output(LED_AMARILLO, amarillo)
    GPIO.output(LED_VERDE, verde)


def mostrar_tendencia():
    """Prende el LED de la tendencia actual (los 3 si no hay datos)."""
    if tendencia == 'ALTA':
        poner_leds(1, 0, 0)
    elif tendencia == 'ESTABLE':
        poner_leds(0, 1, 0)
    elif tendencia == 'BAJA':
        poner_leds(0, 0, 1)
    else:
        poner_leds(1, 1, 1)


def destellar():
    """Destello de 50 ms y vuelta a la tendencia.
    Lo usan dos hilos (el principal y el de destellos por segundo). Con el
    cerrojo, un destello termina entero antes de que empiece el otro; sin él
    podrían mezclarse (condición de carrera)."""
    with cerrojo_leds:
        if tendencia == 'SIN_DATOS':
            poner_leds(0, 0, 0)     # ya estaban los 3 prendidos: se apagan
        else:
            poner_leds(1, 1, 1)
        time.sleep(0.05)
        mostrar_tendencia()


# ---------- Cálculos ----------
def calcular_tendencia(temperatura):
    """Compara la lectura con el promedio de las N ANTERIORES
    (se llama antes de agregarla, para que no se compare consigo misma)."""
    if len(ultimas) < N:
        return 'SIN_DATOS'
    promedio = sum(ultimas) / N
    if temperatura > promedio * (1 + X / 100):
        return 'ALTA'
    if temperatura < promedio * (1 - X / 100):
        return 'BAJA'
    return 'ESTABLE'


def calcular_ciclo(segundos):
    """Reglas de la consigna para un toque de 1 s o más."""
    if segundos < 2.5:
        return 2.5
    if segundos >= 10:
        return 10.0
    return round(segundos, 2)


# ---------- Pulsador (interrupciones) ----------
def leer_pulsador_estable():
    """Antirrebote: devuelve el nivel del pin recién cuando quedó igual
    50 ms seguidos. Si rebota, vuelve a contar desde cero."""
    nivel = GPIO.input(PULSADOR)
    desde = time.time()
    while time.time() - desde < 0.05:
        time.sleep(0.005)
        actual = GPIO.input(PULSADOR)
        if actual != nivel:
            nivel = actual
            desde = time.time()
    return nivel


def al_cambiar_pulsador(canal):
    """Interrupción: RPi.GPIO ejecuta esta función en SU PROPIO HILO cada vez
    que el pin cambia (al apretar y al soltar)."""
    global estado_pulsador, pulsando, instante_apretado, ciclo, en_marcha
    if not en_marcha:
        return                      # el programa está cerrando: no tocar nada
    instante = time.time()          # se toma antes del antirrebote
    nivel = leer_pulsador_estable()
    if nivel == estado_pulsador:
        return                      # fue un rebote: no cambió nada
    estado_pulsador = nivel

    if nivel == 0:                  # se APRETÓ
        instante_apretado = instante
        pulsando = True
        print('>> Pulsador apretado')
        threading.Thread(target=destellar_cada_segundo, daemon=True).start()
    else:                           # se SOLTÓ
        pulsando = False
        apretado = instante - instante_apretado
        if apretado < 1:
            print(f'>> Soltado a los {apretado:.2f} s: fin del monitoreo')
            en_marcha = False
        else:
            ciclo = calcular_ciclo(apretado)
            print(f'>> Soltado a los {apretado:.2f} s: nuevo ciclo = {ciclo} s')
        despertar.set()             # cortar la espera del hilo principal


def destellar_cada_segundo():
    """Hilo: mientras el pulsador siga apretado, destella al cumplirse cada segundo."""
    segundos = 0
    while pulsando and en_marcha:
        if time.time() - instante_apretado >= segundos + 1:
            segundos += 1
            destellar()
        time.sleep(0.01)


# ---------- Red: cliente TCP (Parte C) ----------
def conectar_pc():
    """Hilo: mientras no haya conexión, intenta conectarse a la PC cada 2 s.
    connect() puede tardar hasta 5 s si la PC no responde; por eso va en un
    hilo aparte, para que la estación siga midiendo mientras tanto.
    Si la PC cierra el gráfico, enviar() pone conexion en None y este hilo
    vuelve a intentar: al abrir el gráfico de nuevo, se reconecta solo."""
    global conexion
    while en_marcha:
        if conexion is None:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # IPv4 + TCP
            s.settimeout(5)         # como en el apunte: no esperar más de 5 s
            try:
                s.connect((IP_PC, PUERTO))
                conexion = s
                print(f'>> Conectado a la PC ({IP_PC}:{PUERTO})')
            except OSError:
                s.close()           # la PC no está escuchando: probar más tarde
        time.sleep(2)


def enviar(temperatura):
    """Envía la temperatura a la PC, si hay una conectada.
    struct.pack('!f', T) la convierte en 4 bytes: 'f' = real de 32 bits,
    '!' = orden de red, para que la PC lea los bytes en el mismo orden.
    sendall() (y no send()) asegura que salgan los 4 bytes."""
    global conexion
    if conexion is None:
        return
    try:
        conexion.sendall(struct.pack('!f', temperatura))
    except OSError:
        print('>> Se perdió la conexión con la PC (la estación sigue midiendo)')
        conexion.close()
        conexion = None


# ---------- Un ciclo de medición ----------
def medir():
    global tendencia
    temperatura = leer_temperatura()
    ahora = datetime.now()
    if temperatura is None:
        print('Error al leer el sensor: se saltea este ciclo')
        return

    tendencia = calcular_tendencia(temperatura)    # antes de agregarla
    ultimas.append(temperatura)
    if len(ultimas) > N:
        ultimas.pop(0)                              # se descarta la más vieja
    promedio = sum(ultimas) / len(ultimas)          # este sí incluye la actual

    print(f'[{ahora:%H:%M:%S}] {temperatura:.3f} °C | '
          f'promedio: {promedio:.3f} °C | {tendencia}')
    registro.write(f'{ahora:%Y-%m-%d},{ahora:%H:%M:%S},{temperatura:.3f},{tendencia}\n')
    registro.flush()                # escribir ya en la SD, sin esperar
    enviar(temperatura)             # Parte C
    destellar()


# ---------- Programa principal ----------
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
for pin in (LED_ROJO, LED_AMARILLO, LED_VERDE):
    GPIO.setup(pin, GPIO.OUT)
GPIO.setup(PULSADOR, GPIO.IN, pull_up_down=GPIO.PUD_UP)
mostrar_tendencia()
GPIO.add_event_detect(PULSADOR, GPIO.BOTH, callback=al_cambiar_pulsador)

es_nuevo = not os.path.exists(ARCHIVO)
registro = open(ARCHIVO, 'a')       # 'a' = agregar al final, sin borrar
if es_nuevo:
    registro.write('fecha,hora,temperatura,tendencia\n')

# Parte C: cliente TCP, solo si se escribió la IP de la PC
if IP_PC is not None:
    print(f'Red: conectando con la PC en {IP_PC}:{PUERTO} (reintenta cada 2 s)')
    threading.Thread(target=conectar_pc, daemon=True).start()
else:
    print('Red: sin IP de la PC, la estación funciona sin red (solo Parte A)')

print(f'Estación iniciada. Ciclo: {ciclo} s. Pulsador: < 1 s termina, 1 s o más cambia el ciclo.')
try:
    while en_marcha:
        inicio = time.time()
        despertar.clear()
        medir()
        # Esperar lo que falta del ciclo. wait() vuelve antes si el pulsador
        # hace despertar.set(): así se mide enseguida con el ciclo nuevo.
        restante = ciclo - (time.time() - inicio)
        if restante > 0:
            despertar.wait(restante)
except KeyboardInterrupt:
    print('Detenido con Ctrl+C')
finally:
    # Cierre ordenado: corre siempre (pulsador, Ctrl+C o error)
    en_marcha = False
    GPIO.remove_event_detect(PULSADOR)  # 1) no más interrupciones
    time.sleep(0.1)                     # 2) dejar terminar una que esté en curso
    if conexion is not None:            # 3) cerrar la red
        conexion.close()
    registro.close()                    # 4) cerrar el archivo
    GPIO.cleanup()                      # 5) apagar LEDs y liberar los pines
    print('Fin.')
