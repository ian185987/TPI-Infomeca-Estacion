# Estación de monitoreo de temperatura — TPI Infomeca

Trabajo Final Integrador de **Informática y Programación**, modalidad **Raspberry Pi**.

Una Raspberry Pi mide la temperatura con un sensor DS18B20, muestra la tendencia con un semáforo de 3 LEDs, registra cada lectura en un archivo CSV y la envía por red a una PC, que la grafica en tiempo real. Un programa en C hace la estadística del registro.

| Parte | Lenguaje | Archivo | Corre en |
|---|---|---|---|
| A — Estación de monitoreo | Python | `raspberry/estacion.py` + `raspberry/sensor.py` | Raspberry Pi |
| B — Estadística del registro | C | `raspberry/estadistica.c` | Raspberry Pi |
| C — Gráfico en tiempo real (TCP/IP) | Python | `pc/grafico.py` (y la parte de red de `estacion.py`) | PC + Raspberry Pi |

## Estructura del repositorio

```
raspberry/
  sensor.py                   lectura del DS18B20 desde /sys/bus/w1/devices
  estacion.py                 Partes A y C (lado Raspberry: cliente TCP)
  estadistica.c               Parte B
  registro_temperaturas.csv   datos reales registrados por la estación
pc/
  grafico.py                  Parte C (lado PC: servidor TCP + matplotlib)
historial/                    versiones anteriores, para mostrar la evolución
capturas/                     capturas y fotos usadas en el informe
informe/                      informe final (PDF)
```

## Hardware

- Raspberry Pi 3 Model B con Raspberry Pi OS (64 bits), protoboard y Pi Cobbler.
- Sensor de temperatura digital **DS18B20** (1-Wire) con resistencia de 4.7 kΩ.
- 3 LEDs (rojo, amarillo, verde) y un pulsador con resistencia de 10 kΩ.

| Componente | GPIO (BCM) | Lógica |
|---|---|---|
| LED rojo | 22 | HIGH = prendido |
| LED amarillo | 17 | HIGH = prendido |
| LED verde | 27 | HIGH = prendido |
| Pulsador | 3 | pull-up: suelto = 1, apretado = 0 |
| DS18B20 (datos) | 4 | 1-Wire |

El bus 1-Wire se activa en `/boot/firmware/config.txt` con:

```
dtoverlay=w1-gpio,gpiopin=4
```

## Cómo se usa

### Parte A — solo la estación (sin red)

En la Raspberry:

```bash
cd raspberry
python3 sensor.py        # prueba del sensor: 5 lecturas
python3 estacion.py      # estación sin red
```

- El ciclo arranca en **3.5 s**. En cada ciclo muestra la lectura, el promedio de las últimas 5 y la tendencia, y la guarda en `registro_temperaturas.csv` (`fecha,hora,temperatura,tendencia`).
- **Pulsador:** menos de 1 s termina el programa. De 1 a 2.5 s el ciclo pasa a 2.5 s; de 2.5 a 10 s el ciclo es igual al tiempo apretado; 10 s o más, el ciclo es 10 s.
- **Semáforo:** rojo = ALTA (más de 1 % sobre el promedio), amarillo = ESTABLE, verde = BAJA, los 3 prendidos = SIN_DATOS (menos de 5 lecturas).

### Parte C — estación + gráfico

1. En la PC, **primero**, abrir el servidor y el gráfico (necesita Python de 64 bits con matplotlib):

   ```powershell
   py -3.13 grafico.py
   ```

   La primera vez Windows pregunta por el firewall: permitir en **Redes privadas**.

2. En la Raspberry, correr la estación con la IP de la PC:

   ```bash
   python3 estacion.py 192.168.137.1
   ```

   (`192.168.137.1` es la IP habitual de una notebook con Windows cuando comparte su conexión como zona con cobertura inalámbrica; si no, usar la que muestre `ipconfig`.)

La estación se conecta al puerto **30103** y envía cada temperatura como 4 bytes (`struct.pack('!f', T)`). Si la PC cierra el gráfico, la estación sigue midiendo y se vuelve a conectar sola cuando el gráfico se abre de nuevo.

### Parte B — estadística

En la Raspberry, en la carpeta donde está el CSV:

```bash
gcc -Wall -o estadistica estadistica.c -lm
./estadistica
```

Muestra la cantidad de lecturas, la mínima y la máxima con su fecha y hora, la media, la mediana, la moda y el desvío estándar.

## Decisiones de diseño principales

- **Tendencia:** cada lectura se compara con el promedio de las 5 **anteriores** (sin incluirla), para que no se compare consigo misma. Umbral X = 1 %.
- **Pulsador por interrupciones** (`GPIO.add_event_detect`) con antirrebote por software: el nivel tiene que quedar estable 50 ms.
- **Hilos:** el principal mide; RPi.GPIO atiende las interrupciones en su propio hilo; otro hilo destella cada segundo mientras el pulsador está apretado; otro se conecta a la PC. Un `threading.Lock` evita que dos destellos se mezclen y un `threading.Event` despierta al hilo principal al soltar el pulsador, para medir enseguida con el ciclo nuevo.
- **Cierre ordenado** en un bloque `finally`: se quitan las interrupciones, se cierra la red y el archivo, y se liberan los pines.
- **Red:** la PC es el **servidor** y la Raspberry el **cliente**, como en el apunte de sockets de la cátedra. TCP es un chorro de bytes, así que la PC acumula lo que recibe y lo usa de a 4 bytes.
- **Parte B:** las lecturas se cargan en un arreglo de `struct` con memoria dinámica (`malloc` / `realloc` / `free`). Como medida de dispersión se eligió el **desvío estándar muestral** (n − 1), porque está en la misma unidad que los datos (°C) y usa todas las lecturas.

## Autores

Grupo N.º __ — Informática y Programación 2026

- Nombre Apellido (legajo)
- Nombre Apellido (legajo)
