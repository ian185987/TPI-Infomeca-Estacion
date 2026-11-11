# sensor.py - TPI Infomeca - Lectura del sensor DS18B20
# Módulo con una sola función: leer_temperatura().
# La estación lo usa con:  from sensor import leer_temperatura

import glob     # buscar archivos con comodines, como '28-*'


def leer_temperatura():
    """Devuelve la temperatura en °C, o None si la lectura vino mal."""

    # Linux muestra cada sensor 1-Wire como una carpeta en /sys/bus/w1/devices.
    # Las de los DS18B20 empiezan con '28-' (código de familia del sensor),
    # así no hace falta escribir el número de serie a mano.
    carpetas = glob.glob('/sys/bus/w1/devices/28-*')
    if len(carpetas) == 0:
        return None                     # no se encontró el sensor

    # Al leer w1_slave, el driver le pide una medición al sensor (~800 ms).
    # El archivo trae dos líneas, por ejemplo:
    #   f5 01 4b 46 7f ff 0c 10 84 : crc=84 YES
    #   f5 01 4b 46 7f ff 0c 10 84 t=31312
    with open(carpetas[0] + '/w1_slave') as archivo:
        lineas = archivo.readlines()

    # Línea 1: termina en YES si el control de errores (CRC) dio bien
    if not lineas[0].strip().endswith('YES'):
        return None

    # Línea 2: lo que viene después de 't=' es la temperatura en milésimas de °C
    milesimas = int(lineas[1].split('t=')[1])
    return milesimas / 1000             # 31312 -> 31.312


# Prueba: este bloque corre solo con 'python3 sensor.py',
# no cuando otro programa importa el módulo.
if __name__ == '__main__':
    for i in range(5):
        print('Lectura', i + 1, ':', leer_temperatura(), '°C')
