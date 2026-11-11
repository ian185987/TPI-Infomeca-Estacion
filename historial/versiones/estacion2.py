#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
estacion2.py - TPI Infomeca - Parte A: estación de monitoreo de temperatura

Etapa 3d: ciclo de medición + promedio + tendencia + semáforo + destello
          + registro de cada ciclo en un archivo CSV.
(Falta: pulsador en un hilo (3e).)

Cómo se corre (en la Raspberry, dentro de ~/tpi):
    python3 estacion2.py
Para ver el registro:
    cat registro_temperaturas.csv
Por ahora se corta con Ctrl+C (más adelante será con el pulsador).
"""

import os                             # rutas de archivos
import time                           # time.monotonic() y time.sleep()
from datetime import datetime         # fecha y hora "de reloj" para mostrar
import RPi.GPIO as GPIO               # manejo de los pines (LEDs)
from sensor import leer_temperatura   # nuestro módulo de la etapa 3a

# ---------------------------------------------------------------------------
# Parámetros (constantes): se escriben en MAYÚSCULAS por convención
# ---------------------------------------------------------------------------
CICLO_INICIAL = 3.5     # segundos entre lecturas al arrancar (consigna)
N = 5                   # cantidad de lecturas para el promedio (consigna)
X = 1.0                 # umbral de tendencia, en % del promedio (supuesto)
PASO_ESPERA = 0.05      # la espera se hace en pasos de 50 ms
DURACION_DESTELLO = 0.05    # 50 ms (consigna)

# Archivo de registro: se guarda en la MISMA carpeta que este programa,
# aunque se lo ejecute desde otra carpeta. __file__ es la ruta de este .py.
CARPETA = os.path.dirname(os.path.abspath(__file__))
ARCHIVO_REGISTRO = os.path.join(CARPETA, 'registro_temperaturas.csv')
ENCABEZADO = 'fecha,hora,temperatura,tendencia\n'

# Pines (numeración BCM), confirmados con prueba_hw.py
LED_ROJO = 22           # tendencia en ALTA
LED_AMARILLO = 17       # temperatura ESTABLE
LED_VERDE = 27          # tendencia en BAJA
LEDS = [LED_ROJO, LED_AMARILLO, LED_VERDE]

# Los 4 estados posibles de la tendencia (texto, así se leen fácil en el
# archivo de registro y en la consola)
ALTA = 'ALTA'
ESTABLE = 'ESTABLE'
BAJA = 'BAJA'
SIN_DATOS = 'SIN_DATOS'

# Qué LEDs prende cada estado: un diccionario estado -> lista de pines.
# Tenerlo en una tabla evita una cadena de if/elif y deja la regla
# "cuando uno prende, los otros se apagan" en un solo lugar.
LEDS_POR_TENDENCIA = {
    ALTA: [LED_ROJO],
    ESTABLE: [LED_AMARILLO],
    BAJA: [LED_VERDE],
    SIN_DATOS: [LED_ROJO, LED_AMARILLO, LED_VERDE],   # los 3 (consigna)
}

# ---------------------------------------------------------------------------
# Estado del programa (variables que se recuerdan entre ciclos)
# ---------------------------------------------------------------------------
# Son globales porque en la etapa 3e el hilo del pulsador también las va a
# leer y modificar (cambiar 'ciclo', poner 'en_marcha' en False, y destellar
# los LEDs mostrando después la 'tendencia' actual).
ciclo = CICLO_INICIAL   # duración actual del ciclo, en segundos
ultimas = []            # últimas N temperaturas (la más vieja primero)
tendencia = SIN_DATOS   # tendencia actual
en_marcha = True        # mientras sea True, la estación sigue midiendo
registro = None         # el archivo CSV abierto (se abre en main)


# ---------------------------------------------------------------------------
# Cálculos
# ---------------------------------------------------------------------------
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


def calcular_tendencia(temperatura):
    """Compara la lectura nueva contra el promedio de las N ANTERIORES.

    Se llama ANTES de agregar la lectura a 'ultimas', así el promedio no
    incluye a la lectura que se está evaluando (supuesto del análisis: si la
    incluyera, se compararía en parte consigo misma y la tendencia se
    atenuaría).

    Con P = promedio anterior:
      ALTA     si T > P * (1 + X/100)    (supera en más de X% al promedio)
      BAJA     si T < P * (1 - X/100)    (está más de X% debajo)
      ESTABLE  en otro caso              (dentro de ±X%)
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


# ---------------------------------------------------------------------------
# LEDs
# ---------------------------------------------------------------------------
def configurar_gpio():
    """Configura los 3 LEDs como salidas y los prende (estado SIN_DATOS)."""
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    for pin in LEDS:
        GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)
    mostrar_tendencia()


def mostrar_tendencia():
    """Prende los LEDs de la tendencia actual y apaga el resto."""
    prender = LEDS_POR_TENDENCIA[tendencia]
    for pin in LEDS:
        # (pin in prender) da True o False: True prende, False apaga
        GPIO.output(pin, pin in prender)


def destellar():
    """Destello de 50 ms de los 3 LEDs y vuelta a la tendencia actual.

    Normalmente el destello PRENDE los 3 LEDs. Pero si ya están los 3
    prendidos (SIN_DATOS), prenderlos no se vería; en ese caso el destello
    los APAGA 50 ms (supuesto del análisis: el destello siempre tiene que
    ser visible).
    """
    nivel = (tendencia != SIN_DATOS)   # True = prender, False = apagar
    for pin in LEDS:
        GPIO.output(pin, nivel)
    time.sleep(DURACION_DESTELLO)
    mostrar_tendencia()


# ---------------------------------------------------------------------------
# Registro en archivo
# ---------------------------------------------------------------------------
def abrir_registro():
    """Abre el CSV para AGREGAR líneas y lo devuelve.

    Modo 'a' (append): cada vez que arranca la estación, las lecturas
    nuevas se suman al final y no se pierden las de antes. Así la Parte B
    puede analizar todas las mediciones juntas.

    El encabezado (nombres de las columnas) se escribe solo si el archivo
    es nuevo o está vacío; si no, quedaría repetido en el medio.
    """
    es_nuevo = (not os.path.exists(ARCHIVO_REGISTRO)
                or os.path.getsize(ARCHIVO_REGISTRO) == 0)
    archivo = open(ARCHIVO_REGISTRO, 'a', encoding='utf-8')
    if es_nuevo:
        archivo.write(ENCABEZADO)
    return archivo


def registrar(momento, temperatura):
    """Escribe una línea del ciclo: fecha,hora,temperatura,tendencia.

    Ejemplo:  2026-11-09,01:50:24,26.875,ALTA

    - fecha AAAA-MM-DD y hora hh:mm:ss: formato fijo, fácil de leer desde C
      con fscanf y que además se ordena bien alfabéticamente.
    - temperatura con 3 decimales (la resolución que da el driver).
    - flush() fuerza a escribir en la SD en el momento. Sin él, Python junta
      los datos en memoria y, si se corta la luz, se perderían las últimas
      lecturas.
    """
    linea = (f"{momento.strftime('%Y-%m-%d')},{momento.strftime('%H:%M:%S')},"
             f"{temperatura:.3f},{tendencia}\n")
    registro.write(linea)
    registro.flush()


# ---------------------------------------------------------------------------
# Ciclo de medición
# ---------------------------------------------------------------------------
def esperar_fin_de_ciclo(inicio_ciclo):
    """Espera hasta que pasen 'ciclo' segundos desde 'inicio_ciclo'.

    1) Se mide desde el INICIO del ciclo, no desde que terminó la lectura
       (la lectura tarda ~0.8 s; si no, el ciclo real sería de 4.3 s).
    2) Se espera en pasos cortos (50 ms): en cada paso se vuelve a mirar
       'ciclo' y 'en_marcha', así un cambio del pulsador (etapa 3e) se
       aplica enseguida.
    3) time.monotonic() es un reloj que solo avanza: no salta si la
       Raspberry corrige la hora por internet.
    """
    while en_marcha:
        restante = ciclo - (time.monotonic() - inicio_ciclo)
        if restante <= 0:
            break
        # Duermo un paso de 50 ms, o lo que falte si es menos (sin el min(),
        # el último paso se pasaba de largo y el ciclo duraba ~3.52 s).
        time.sleep(min(PASO_ESPERA, restante))


def medir_una_vez():
    """Un ciclo completo: lee, calcula tendencia, guarda, muestra, registra, LEDs."""
    global tendencia    # sin esto, Python crearía una variable local nueva

    temperatura = leer_temperatura()
    momento = datetime.now()     # UN solo instante para consola y archivo
    hora = momento.strftime('%H:%M:%S.%f')[:-3]   # hh:mm:ss.mmm

    if temperatura is None:
        # Si el sensor falla, se avisa y se saltea este ciclo: no se guarda
        # nada, para no ensuciar el promedio con un dato inválido.
        print(f"[{hora}] ERROR: no se pudo leer el sensor, se saltea el ciclo")
        return

    tendencia = calcular_tendencia(temperatura)   # ANTES de agregarla
    agregar_lectura(temperatura)
    prom = promedio(ultimas)                      # incluye la actual (consigna)

    print(f"[{hora}] Temperatura: {temperatura:6.3f} °C | "
          f"Promedio últimas {len(ultimas)}: {prom:6.3f} °C | "
          f"Tendencia: {tendencia}")

    registrar(momento, temperatura)
    destellar()     # fin de ciclo: destello y LED de la tendencia


def main():
    global registro
    configurar_gpio()
    registro = abrir_registro()
    print(f"Estación de monitoreo iniciada. Ciclo: {ciclo} s, N = {N}, X = {X} %.")
    print(f"Registrando en: {ARCHIVO_REGISTRO}")
    print("Ctrl+C para terminar.\n")
    try:
        while en_marcha:
            inicio_ciclo = time.monotonic()   # marca de tiempo del comienzo
            medir_una_vez()
            esperar_fin_de_ciclo(inicio_ciclo)
    except KeyboardInterrupt:
        print("\nEstación detenida por el usuario.")
    finally:
        # Siempre (haya error o no): cierra el archivo, apaga los LEDs y
        # libera los pines
        registro.close()
        GPIO.cleanup()


# Solo arranca si se ejecuta este archivo directamente (igual que en sensor.py)
if __name__ == '__main__':
    main()
