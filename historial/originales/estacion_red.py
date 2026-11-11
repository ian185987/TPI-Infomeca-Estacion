#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
estacion_red.py - TPI Infomeca - Parte C (lado Raspberry)

Es la estación de la Parte A (estacion.py) SIN CAMBIOS en lo que ya hacía,
más un SERVIDOR de sockets TCP/IP: en cada ciclo, además de mostrar,
registrar y destellar, envía la temperatura a la PC que esté conectada.

Cómo se comunica (igual que el ejemplo del profe, con struct):
  - La Raspberry escucha en el puerto 5000 (servidor).
  - La PC se conecta (cliente: grafico.py) y recibe un float por lectura.
  - Cada temperatura viaja empaquetada con struct.pack('!f', T): 4 bytes,
    float de 32 bits en orden de red ('!' = big-endian).
  - Si la PC se desconecta, la estación sigue midiendo igual y espera a
    que se vuelva a conectar.

Por qué la Raspberry es el servidor: lo pide la consigna ("se configura un
socket" en la Raspberry y "una computadora se conecta"). Además la PC se
conecta por nombre (rbpi1.local) y el firewall de Windows no la bloquea,
porque solo filtra conexiones ENTRANTES.

Cómo se corre (en la Raspberry, dentro de ~/tpi):
    python3 estacion_red.py
y en la PC:
    python grafico.py
"""

import os                             # rutas de archivos
import time                           # time.monotonic() y time.sleep()
import threading                      # hilos (Thread) y cerrojo (Lock)
import socket                         # comunicación TCP/IP con la PC
import struct                         # empaquetar el float en bytes
from datetime import datetime         # fecha y hora "de reloj"
import RPi.GPIO as GPIO               # manejo de los pines
from sensor import leer_temperatura   # nuestro módulo de la etapa 3a

# ---------------------------------------------------------------------------
# Parámetros (constantes)
# ---------------------------------------------------------------------------
CICLO_INICIAL = 3.5         # segundos entre lecturas al arrancar (consigna)
CICLO_MINIMO = 2.5          # (consigna)
CICLO_MAXIMO = 10.0         # (consigna)
TIEMPO_FIN = 1.0            # apretado menos que esto -> fin del programa
N = 5                       # lecturas para el promedio (consigna)
X = 1.0                     # umbral de tendencia en % (supuesto)
PASO_ESPERA = 0.05          # la espera entre ciclos se hace en pasos de 50 ms
DURACION_DESTELLO = 0.05    # 50 ms (consigna)
ANTIRREBOTE = 0.05          # 50 ms: un cambio del pulsador más corto es rebote
PUERTO = 5000               # puerto TCP donde la Raspberry espera a la PC

# Pines (numeración BCM), confirmados con prueba_hw.py
LED_ROJO = 22
LED_AMARILLO = 17
LED_VERDE = 27
LEDS = [LED_ROJO, LED_AMARILLO, LED_VERDE]
PULSADOR = 3                # pull-up: suelto = 1, apretado = 0
APRETADO = 0
SUELTO = 1

# Archivo de registro, en la misma carpeta que este programa
CARPETA = os.path.dirname(os.path.abspath(__file__))
ARCHIVO_REGISTRO = os.path.join(CARPETA, 'registro_temperaturas.csv')
ENCABEZADO = 'fecha,hora,temperatura,tendencia\n'

# Estados de la tendencia y qué LEDs prende cada uno
ALTA, ESTABLE, BAJA, SIN_DATOS = 'ALTA', 'ESTABLE', 'BAJA', 'SIN_DATOS'
LEDS_POR_TENDENCIA = {
    ALTA: [LED_ROJO],
    ESTABLE: [LED_AMARILLO],
    BAJA: [LED_VERDE],
    SIN_DATOS: [LED_ROJO, LED_AMARILLO, LED_VERDE],
}

# ---------------------------------------------------------------------------
# Estado compartido entre hilos
# ---------------------------------------------------------------------------
# Ahora hay TRES hilos que usan estas variables:
#   1) el hilo principal (mide en ciclos),
#   2) el hilo de interrupciones que crea RPi.GPIO (ejecuta al_cambiar_pulsador),
#   3) el hilo de destellos por segundo (vive solo mientras el botón está apretado).
ciclo = CICLO_INICIAL       # duración del ciclo (la escribe el pulsador)
instante_cambio = 0.0       # time.monotonic() del último cambio de ciclo
en_marcha = True            # False = terminar (la escribe el pulsador)
ultimas = []                # últimas N temperaturas
tendencia = SIN_DATOS       # tendencia actual (la lee el hilo de destellos)
registro = None             # archivo CSV abierto
servidor = None             # socket que ESCUCHA (espera conexiones)
conexion = None             # socket CONECTADO con la PC (None = no hay PC)

# Estado del pulsador (lo usa solo el hilo de interrupciones)
estado_pulsador = SUELTO    # último estado ESTABLE (ya sin rebotes)
instante_apretado = 0.0     # time.monotonic() del momento en que se apretó
pulsando = False            # True mientras está apretado (lo lee el hilo de destellos)

# Cerrojo de los LEDs: solo un hilo por vez puede cambiarlos.
# Sin él, el destello del ciclo y el destello por segundo podrían mezclarse
# (uno apaga lo que el otro acaba de prender): una "condición de carrera".
cerrojo_leds = threading.Lock()


# ---------------------------------------------------------------------------
# Cálculos
# ---------------------------------------------------------------------------
def promedio(valores):
    """Promedio de una lista (None si está vacía)."""
    if len(valores) == 0:
        return None
    return sum(valores) / len(valores)


def agregar_lectura(temperatura):
    """Ventana deslizante: guarda la nueva y descarta la más vieja si hay más de N."""
    ultimas.append(temperatura)
    if len(ultimas) > N:
        ultimas.pop(0)


def calcular_tendencia(temperatura):
    """Compara la lectura nueva contra el promedio de las N ANTERIORES.

    Se llama ANTES de agregar la lectura (supuesto del análisis).
      ALTA si T > P*(1+X/100) | BAJA si T < P*(1-X/100) | ESTABLE si no
      SIN_DATOS si todavía no hay N lecturas anteriores
    """
    if len(ultimas) < N:
        return SIN_DATOS
    p = promedio(ultimas)
    if temperatura > p * (1 + X / 100):
        return ALTA
    if temperatura < p * (1 - X / 100):
        return BAJA
    return ESTABLE


def calcular_ciclo(segundos_apretado):
    """Aplica las reglas de la consigna al tiempo que estuvo apretado (>= 1 s)."""
    if segundos_apretado < CICLO_MINIMO:     # de 1 s a 2.5 s -> mínimo
        return CICLO_MINIMO
    if segundos_apretado >= CICLO_MAXIMO:    # desde 10 s -> máximo
        return CICLO_MAXIMO
    return round(segundos_apretado, 3)       # en el medio: lo que estuvo apretado


# ---------------------------------------------------------------------------
# LEDs (protegidos por el cerrojo)
# ---------------------------------------------------------------------------
def _aplicar_tendencia():
    """Prende los LEDs de la tendencia y apaga el resto. SIN cerrojo.

    Es interna (guion bajo): solo se llama desde funciones que YA tienen el
    cerrojo tomado. Si tomara el cerrojo ella también, destellar() se
    bloquearía a sí misma esperando una llave que ya tiene (un "deadlock").
    """
    prender = LEDS_POR_TENDENCIA[tendencia]
    for pin in LEDS:
        GPIO.output(pin, pin in prender)


def mostrar_tendencia():
    """Muestra la tendencia actual en los LEDs (toma el cerrojo)."""
    with cerrojo_leds:          # 'with' toma la llave y la suelta al salir, aunque haya error
        _aplicar_tendencia()


def destellar():
    """Destello de 50 ms de los 3 LEDs y vuelta a la tendencia (toma el cerrojo).

    Con tendencia, el destello PRENDE los 3; sin datos (ya están los 3
    prendidos) los APAGA, para que siempre se vea (supuesto del análisis).
    Todo el destello ocurre con el cerrojo tomado: el otro hilo espera y
    no puede meterse en el medio.
    """
    with cerrojo_leds:
        nivel = (tendencia != SIN_DATOS)
        for pin in LEDS:
            GPIO.output(pin, nivel)
        time.sleep(DURACION_DESTELLO)
        _aplicar_tendencia()


# ---------------------------------------------------------------------------
# Pulsador por interrupciones
# ---------------------------------------------------------------------------
def leer_pulsador_estable():
    """Antirrebote: devuelve el nivel del pulsador recién cuando se mantuvo
    IGUAL durante 50 ms seguidos.

    Lee el pin cada 5 ms; si el valor cambia, vuelve a contar los 50 ms
    desde cero. Mientras el contacto rebota, el valor salta y la cuenta se
    reinicia una y otra vez; recién cuando se calma se acepta el valor.
    """
    nivel = GPIO.input(PULSADOR)
    desde = time.monotonic()
    while time.monotonic() - desde < ANTIRREBOTE:
        time.sleep(0.005)
        actual = GPIO.input(PULSADOR)
        if actual != nivel:             # rebotó: reiniciar la cuenta
            nivel = actual
            desde = time.monotonic()
    return nivel


def al_cambiar_pulsador(canal):
    """Función de interrupción (callback): RPi.GPIO la llama en SU PROPIO HILO
    cada vez que el pin del pulsador cambia (flanco de bajada o de subida).

    Un solo toque produce varios flancos por el rebote. Por eso no se confía
    en el flanco: se espera a que el pin quede estable (antirrebote) y se
    compara con el último estado estable. Si es igual, fue un rebote y se
    ignora; si cambió de verdad, se procesa.
    El instante se toma AL LLEGAR el flanco (antes del antirrebote), para no
    sumarle esa espera al tiempo medido.
    """
    global estado_pulsador
    if not en_marcha:
        # El programa ya está terminando: no tocar los pines. Puede llegar
        # una interrupción tardía (por ejemplo, un rebote del mismo toque
        # que pidió terminar) cuando main() ya liberó los pines.
        return
    instante = time.monotonic()
    try:
        nivel = leer_pulsador_estable()
    except Exception:
        # Si justo se liberaron los pines mientras leíamos, GPIO.input()
        # falla (se vio en la Raspberry: mensaje 'unknown handle' al final
        # de estacion4). No hay nada que hacer: el programa está cerrando.
        return
    if nivel == estado_pulsador:
        return                      # rebote: no cambió nada
    estado_pulsador = nivel
    if nivel == APRETADO:
        al_apretar(instante)
    else:
        al_soltar(instante)


def al_apretar(instante):
    """Se apretó: guardar el instante y lanzar el hilo de destellos por segundo."""
    global instante_apretado, pulsando
    instante_apretado = instante
    pulsando = True
    print("  >> Pulsador apretado (contá los destellos: 1 por segundo)")
    # Hilo nuevo solo para los destellos. daemon=True: si el programa
    # termina, este hilo no lo deja colgado.
    threading.Thread(target=destellar_cada_segundo, daemon=True).start()


def destellar_cada_segundo():
    """Mientras el pulsador siga apretado, destella al cumplirse cada segundo.

    Los segundos se cuentan desde el instante en que se apretó (1 s, 2 s,
    3 s...), no "sleep(1) y destello": así el destello no se atrasa aunque
    tenga que esperar el cerrojo.
    """
    segundo = 1
    while pulsando and en_marcha:
        if time.monotonic() - instante_apretado >= segundo:
            if pulsando:                    # puede haberse soltado justo ahora
                destellar()
                print(f"     {segundo} s")
            segundo += 1
        time.sleep(0.01)


def al_soltar(instante):
    """Se soltó: medir cuánto estuvo apretado y decidir fin o nuevo ciclo."""
    global pulsando, en_marcha, ciclo, instante_cambio
    pulsando = False                        # esto detiene el hilo de destellos
    apretado = instante - instante_apretado
    ms = round(apretado * 1000)
    if apretado < TIEMPO_FIN:
        print(f"  >> Pulsador soltado a los {ms} ms (menos de 1 s): fin del monitoreo.")
        en_marcha = False                   # el hilo principal lo ve y termina
    else:
        ciclo = calcular_ciclo(apretado)
        instante_cambio = instante          # CUÁNDO se soltó (ver esperar_fin_de_ciclo)
        print(f"  >> Pulsador soltado a los {ms} ms: NUEVO CICLO = {ciclo} s")


def configurar_gpio():
    """LEDs como salida, pulsador como entrada e interrupción en ambos flancos."""
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    for pin in LEDS:
        GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)
    # El GPIO 3 ya tiene pull-up en la placa; activar el interno no molesta
    # y deja el programa listo si se cambia el pulsador a otro pin.
    GPIO.setup(PULSADOR, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    mostrar_tendencia()
    # GPIO.BOTH: avisar al apretar (flanco de bajada, 1->0) Y al soltar
    # (flanco de subida, 0->1). Necesitamos los dos para medir el tiempo.
    GPIO.add_event_detect(PULSADOR, GPIO.BOTH, callback=al_cambiar_pulsador)


# ---------------------------------------------------------------------------
# Registro en archivo
# ---------------------------------------------------------------------------
def abrir_registro():
    """Abre el CSV en modo 'a' (agregar). Escribe el encabezado si es nuevo."""
    es_nuevo = (not os.path.exists(ARCHIVO_REGISTRO)
                or os.path.getsize(ARCHIVO_REGISTRO) == 0)
    archivo = open(ARCHIVO_REGISTRO, 'a', encoding='utf-8')
    if es_nuevo:
        archivo.write(ENCABEZADO)
    return archivo


def registrar(momento, temperatura):
    """Escribe 'fecha,hora,temperatura,tendencia' y fuerza la escritura (flush)."""
    linea = (f"{momento.strftime('%Y-%m-%d')},{momento.strftime('%H:%M:%S')},"
             f"{temperatura:.3f},{tendencia}\n")
    registro.write(linea)
    registro.flush()


# ---------------------------------------------------------------------------
# Socket TCP/IP (Parte C)
# ---------------------------------------------------------------------------
def crear_servidor():
    """Crea el socket servidor: escucha en el puerto PUERTO de la Raspberry."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)   # IPv4 + TCP
    # SO_REUSEADDR: permite volver a usar el puerto apenas se reinicia el
    # programa (si no, Linux lo deja "ocupado" unos segundos).
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(('', PUERTO))      # '' = escuchar en todas las interfaces de red
    s.listen(1)               # una PC por vez
    s.settimeout(1.0)         # accept() espera como máximo 1 s (ver abajo)
    return s


def atender_conexiones():
    """HILO: espera que la PC se conecte (accept) y guarda la conexión.

    accept() se queda esperando hasta que alguien se conecta. Por eso va en
    un hilo aparte: si estuviera en el hilo principal, la estación dejaría de
    medir hasta que se conecte la PC. El timeout de 1 s hace que cada segundo
    vuelva a mirar en_marcha, para poder terminar cuando se pide.
    Si la PC se desconecta y se vuelve a conectar, se toma la nueva conexión.
    """
    global conexion
    while en_marcha:
        try:
            cliente, direccion = servidor.accept()
        except socket.timeout:
            continue                  # nadie se conectó en este segundo
        except OSError:
            break                     # el servidor se cerró: terminar el hilo
        conexion = cliente
        print(f"  >> PC conectada desde {direccion[0]}")


def enviar_temperatura(temperatura):
    """Envía la temperatura a la PC, si hay una conectada.

    struct.pack('!f', T) convierte el número en 4 bytes con un formato fijo
    que la PC sabe desempaquetar con struct.unpack('!f', ...).
    Si falla el envío (la PC cerró el programa), se descarta la conexión y
    la estación sigue funcionando: medir y registrar no depende de la red.
    """
    global conexion
    if conexion is None:
        return
    try:
        conexion.sendall(struct.pack('!f', temperatura))
    except OSError:
        print("  >> La PC se desconectó (la estación sigue midiendo)")
        conexion.close()
        conexion = None


# ---------------------------------------------------------------------------
# Ciclo de medición (hilo principal)
# ---------------------------------------------------------------------------
def esperar_fin_de_ciclo(inicio_ciclo, fin_medicion):
    """Espera hasta completar 'ciclo' segundos desde 'inicio_ciclo'.

    En pasos de 50 ms, mirando en cada paso las variables que cambia el
    pulsador: corta la espera si hay que terminar (en_marcha) o si se soltó
    el pulsador con un ciclo nuevo DURANTE esta espera, para medir
    "inmediatamente a la nueva frecuencia" como pide la consigna.

    Corrección de estacion3 (condición de carrera): antes el pulsador ponía
    un aviso en True y el hilo principal lo volvía a False al empezar cada
    ciclo. Si el pulsador se soltaba mientras se estaba leyendo el sensor
    (la lectura dura ~0.8 s), esa lectura ya era la "inmediata", pero al
    terminarla se veía el aviso y se medía OTRA VEZ (en la Raspberry: dos
    lecturas a 0.86 s). El resultado dependía de qué hilo llegaba primero.
    Ahora se compara CUÁNDO se soltó (instante_cambio) contra cuándo
    terminó la medición (fin_medicion):
      - soltado durante la medición -> esa medición cuenta como la
        inmediata; el ciclo sigue, ya con la duración nueva;
      - soltado durante la espera   -> se corta la espera y se mide ya.
    Así no importa el orden en que los hilos tocan las variables.
    """
    while en_marcha and instante_cambio <= fin_medicion:
        restante = ciclo - (time.monotonic() - inicio_ciclo)
        if restante <= 0:
            break
        time.sleep(min(PASO_ESPERA, restante))


def medir_una_vez():
    """Un ciclo: lee, calcula tendencia, guarda, muestra, registra, destella."""
    global tendencia
    temperatura = leer_temperatura()
    momento = datetime.now()
    hora = momento.strftime('%H:%M:%S.%f')[:-3]

    if temperatura is None:
        print(f"[{hora}] ERROR: no se pudo leer el sensor, se saltea el ciclo")
        return

    tendencia = calcular_tendencia(temperatura)   # ANTES de agregarla
    agregar_lectura(temperatura)
    prom = promedio(ultimas)
    print(f"[{hora}] Temperatura: {temperatura:6.3f} °C | "
          f"Promedio últimas {len(ultimas)}: {prom:6.3f} °C | "
          f"Tendencia: {tendencia}")
    registrar(momento, temperatura)
    enviar_temperatura(temperatura)     # Parte C: a la PC, si está conectada
    destellar()


def main():
    global registro, servidor
    try:
        configurar_gpio()
    except RuntimeError as error:
        # En kernels nuevos, add_event_detect de RPi.GPIO puede fallar.
        print(f"ERROR al activar la interrupción del pulsador: {error}")
        print("Posible solución (reemplaza RPi.GPIO por una versión compatible):")
        print("    sudo apt install python3-rpi-lgpio")
        GPIO.cleanup()
        return

    registro = abrir_registro()
    servidor = crear_servidor()
    threading.Thread(target=atender_conexiones, daemon=True).start()
    print(f"Estación de monitoreo CON RED (Parte C) iniciada. Ciclo: {ciclo} s, N = {N}, X = {X} %.")
    print(f"Registrando en: {ARCHIVO_REGISTRO}")
    print("Pulsador: menos de 1 s = terminar | 1 s o más = nuevo ciclo (2.5 a 10 s)")
    print(f"Servidor esperando a la PC en el puerto {PUERTO} (desde la PC: python grafico.py)\n")
    try:
        while en_marcha:
            inicio_ciclo = time.monotonic()
            medir_una_vez()
            esperar_fin_de_ciclo(inicio_ciclo, time.monotonic())
    except KeyboardInterrupt:
        print("\nEstación detenida con Ctrl+C.")
    finally:
        # Cierre ordenado de los recursos, del más "activo" al más pasivo:
        GPIO.remove_event_detect(PULSADOR)   # 1) no más interrupciones nuevas
        time.sleep(ANTIRREBOTE * 2)          # 2) dejar terminar un callback en curso
        if conexion is not None:             # 3) cerrar la red: conexión y servidor
            conexion.close()
        servidor.close()
        registro.close()                     # 4) cerrar el archivo (vacía el buffer)
        GPIO.cleanup()                       # 5) apagar LEDs y liberar los pines
        print("Red, archivo y pines liberados. Fin.")


if __name__ == '__main__':
    main()
