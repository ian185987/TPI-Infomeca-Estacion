/*
 * estadistica.c - TPI Infomeca - Parte B: análisis estadístico de las lecturas
 *
 * Lee el archivo que genera la estación (Parte A):
 *     fecha,hora,temperatura,tendencia          <- encabezado (se saltea)
 *     2026-11-09,01:50:24,26.875,ALTA           <- una línea por ciclo
 * y muestra:
 *   - la cantidad de lecturas,
 *   - la menor y la mayor temperatura, con su fecha y hora,
 *   - media, mediana, moda,
 *   - varianza, desvío estándar y rango (medidas de dispersión).
 *
 * Requisitos de la consigna:
 *   - una estructura (struct) que modela cada lectura,
 *   - memoria dinámica para guardarlas (no se sabe de antemano cuántas son),
 *   - sin librerías externas: solo la biblioteca estándar de C.
 *
 * Compilar (en la Raspberry, dentro de ~/tpi):
 *     gcc -Wall -o estadistica estadistica.c -lm
 * Ejecutar:
 *     ./estadistica                          (usa registro_temperaturas.csv)
 *     ./estadistica otro_archivo.csv         (o el archivo que se indique)
 */

#include <stdio.h>    /* fopen, fgets, sscanf, printf, fclose            */
#include <stdlib.h>   /* malloc, realloc, free, qsort                    */
#include <string.h>   /* strcpy                                          */
#include <math.h>     /* sqrt, lround (por eso se compila con -lm)       */

#define ARCHIVO_POR_DEFECTO "registro_temperaturas.csv"
#define CAPACIDAD_INICIAL 16    /* lugares que se reservan al principio  */
#define LARGO_LINEA 128         /* una línea del CSV mide ~40 caracteres */

/* ------------------------------------------------------------------------
 * Estructura que modela UNA lectura de la estación (una línea del CSV).
 * Los tamaños de los textos incluyen el '\0' que marca el fin del string:
 *   "2026-11-09" = 10 caracteres + 1  ->  fecha[11]
 *   "01:50:24"   =  8 caracteres + 1  ->  hora[9]
 *   "SIN_DATOS"  =  9 caracteres + 1  ->  tendencia[10]  (la más larga)
 * ---------------------------------------------------------------------- */
typedef struct {
    char fecha[11];
    char hora[9];
    double temperatura;     /* en °C */
    char tendencia[10];
} Lectura;


/* ------------------------------------------------------------------------
 * cargar_lecturas: lee el CSV completo y devuelve un arreglo DINÁMICO de
 * Lectura. En *cantidad deja cuántas lecturas cargó.
 * Devuelve NULL si no pudo abrir el archivo o si no hay memoria.
 *
 * Memoria dinámica: arranca con lugar para 16 lecturas (malloc). Cuando se
 * llena, DUPLICA la capacidad con realloc. Duplicar (y no sumar de a uno)
 * hace que haya pocas llamadas a realloc aunque el archivo tenga miles de
 * líneas: para 1000 lecturas son solo 6 ampliaciones (16->32->...->1024).
 * ---------------------------------------------------------------------- */
Lectura *cargar_lecturas(const char *nombre, int *cantidad)
{
    FILE *archivo = fopen(nombre, "r");          /* "r" = solo lectura */
    if (archivo == NULL) {
        printf("No se pudo abrir el archivo '%s'.\n", nombre);
        return NULL;
    }

    int capacidad = CAPACIDAD_INICIAL;
    int n = 0;
    Lectura *lecturas = malloc(capacidad * sizeof(Lectura));
    if (lecturas == NULL) {
        printf("No hay memoria suficiente.\n");
        fclose(archivo);
        return NULL;
    }

    char linea[LARGO_LINEA];
    int numero_linea = 0;
    int descartadas = 0;

    while (fgets(linea, sizeof(linea), archivo) != NULL) {
        numero_linea++;
        if (numero_linea == 1) {
            continue;       /* la primera línea es el encabezado: se saltea */
        }

        /* Si el arreglo está lleno, se duplica su capacidad */
        if (n == capacidad) {
            capacidad = capacidad * 2;
            /* realloc puede mover el bloque a otro lugar de la memoria:
               se guarda el resultado en un puntero auxiliar para no perder
               el original si realloc falla (devuelve NULL). */
            Lectura *ampliado = realloc(lecturas, capacidad * sizeof(Lectura));
            if (ampliado == NULL) {
                printf("No hay memoria suficiente.\n");
                free(lecturas);
                fclose(archivo);
                return NULL;
            }
            lecturas = ampliado;
        }

        /* sscanf separa la línea por comas:
             %10[^,]  -> hasta 10 caracteres que no sean coma (la fecha)
             %8[^,]   -> hasta 8 caracteres que no sean coma (la hora)
             %lf      -> un número real (double): la temperatura
             %9s      -> hasta 9 caracteres: la tendencia
           Los límites (10, 8, 9) evitan escribir fuera de los arreglos.
           Devuelve cuántos campos pudo leer: si no son 4, la línea está mal. */
        Lectura l;
        int campos = sscanf(linea, "%10[^,],%8[^,],%lf,%9s",
                            l.fecha, l.hora, &l.temperatura, l.tendencia);
        if (campos == 4) {
            lecturas[n] = l;        /* se copia la estructura completa */
            n++;
        } else {
            descartadas++;          /* línea vacía o con formato incorrecto */
        }
    }

    fclose(archivo);
    if (descartadas > 0) {
        printf("Aviso: se descartaron %d líneas con formato incorrecto.\n",
               descartadas);
    }
    *cantidad = n;
    return lecturas;
}


/* Devuelve la posición de la lectura con menor temperatura.
   Si hay empate, se queda con la primera (la más antigua). */
int posicion_minima(const Lectura *lecturas, int n)
{
    int pos = 0;
    for (int i = 1; i < n; i++) {
        if (lecturas[i].temperatura < lecturas[pos].temperatura) {
            pos = i;
        }
    }
    return pos;
}

/* Devuelve la posición de la lectura con mayor temperatura (la primera si hay empate). */
int posicion_maxima(const Lectura *lecturas, int n)
{
    int pos = 0;
    for (int i = 1; i < n; i++) {
        if (lecturas[i].temperatura > lecturas[pos].temperatura) {
            pos = i;
        }
    }
    return pos;
}

/* Media aritmética: suma de todos los valores dividida por la cantidad. */
double calcular_media(const double *valores, int n)
{
    double suma = 0.0;
    for (int i = 0; i < n; i++) {
        suma += valores[i];
    }
    return suma / n;
}

/* Función de comparación que necesita qsort para ordenar doubles de menor a
   mayor. Recibe punteros genéricos (void *) y devuelve negativo, cero o
   positivo según a sea menor, igual o mayor que b. */
int comparar_double(const void *a, const void *b)
{
    double x = *(const double *)a;
    double y = *(const double *)b;
    if (x < y) return -1;
    if (x > y) return 1;
    return 0;
}

/* Mediana: el valor del medio del arreglo ORDENADO. Con cantidad par no hay
   un único "medio": se promedian los dos centrales. */
double calcular_mediana(const double *ordenados, int n)
{
    if (n % 2 == 1) {
        return ordenados[n / 2];
    }
    return (ordenados[n / 2 - 1] + ordenados[n / 2]) / 2.0;
}

/* Moda: el valor que más se repite. Se recorre el arreglo ORDENADO, donde
   los valores iguales quedan juntos, contando cada "racha".
   Los valores se comparan en milésimas de grado como enteros (lround), no
   como double: comparar reales con == puede fallar por errores de redondeo
   (26.187 podría guardarse como 26.18699999...). En el CSV la temperatura
   tiene 3 decimales, así que pasar a milésimas no pierde nada.
   Imprime TODAS las modas si hay empate. Devuelve la frecuencia máxima. */
int mostrar_modas(const double *ordenados, int n)
{
    /* Primera pasada: buscar cuántas veces aparece el valor más repetido */
    int frecuencia_max = 0;
    int i = 0;
    while (i < n) {
        long valor = lround(ordenados[i] * 1000);
        int j = i;
        while (j < n && lround(ordenados[j] * 1000) == valor) {
            j++;                            /* avanzar mientras se repita */
        }
        if (j - i > frecuencia_max) {
            frecuencia_max = j - i;         /* largo de la racha */
        }
        i = j;
    }

    /* Si ningún valor se repite, todos serían "moda": no hay moda */
    if (frecuencia_max == 1) {
        printf("  Moda:                 no hay (ningún valor se repite)\n");
        return frecuencia_max;
    }

    /* Segunda pasada: imprimir los valores que tienen esa frecuencia */
    printf("  Moda:                 ");
    i = 0;
    while (i < n) {
        long valor = lround(ordenados[i] * 1000);
        int j = i;
        while (j < n && lround(ordenados[j] * 1000) == valor) {
            j++;
        }
        if (j - i == frecuencia_max) {
            printf("%.3f °C  ", ordenados[i]);
        }
        i = j;
    }
    printf("(%d veces)\n", frecuencia_max);
    return frecuencia_max;
}

/* Varianza MUESTRAL: promedio de los cuadrados de las distancias a la media,
   dividiendo por (n - 1) y no por n. Se usa n - 1 porque las lecturas son
   una MUESTRA de la temperatura del ambiente (no todos los valores
   posibles): dividir por n tiende a subestimar la variabilidad real.
   Con n = 1 no hay dispersión que medir y se devuelve 0. */
double calcular_varianza(const double *valores, int n, double media)
{
    if (n < 2) {
        return 0.0;
    }
    double suma = 0.0;
    for (int i = 0; i < n; i++) {
        double distancia = valores[i] - media;
        suma += distancia * distancia;
    }
    return suma / (n - 1);
}


int main(int argc, char *argv[])
{
    /* Si se pasa un nombre de archivo al ejecutar, se usa ese */
    const char *nombre = (argc > 1) ? argv[1] : ARCHIVO_POR_DEFECTO;

    int n = 0;
    Lectura *lecturas = cargar_lecturas(nombre, &n);
    if (lecturas == NULL) {
        return 1;           /* 1 = terminó con error */
    }
    if (n == 0) {
        printf("El archivo '%s' no tiene lecturas.\n", nombre);
        free(lecturas);
        return 1;
    }

    /* Arreglo dinámico con solo las temperaturas, para ordenar sin
       desordenar 'lecturas' (que guarda el orden cronológico y las fechas). */
    double *temps = malloc(n * sizeof(double));
    if (temps == NULL) {
        printf("No hay memoria suficiente.\n");
        free(lecturas);
        return 1;
    }
    for (int i = 0; i < n; i++) {
        temps[i] = lecturas[i].temperatura;
    }

    int pmin = posicion_minima(lecturas, n);
    int pmax = posicion_maxima(lecturas, n);
    double media = calcular_media(temps, n);
    double varianza = calcular_varianza(temps, n, media);
    double desvio = sqrt(varianza);
    double rango = lecturas[pmax].temperatura - lecturas[pmin].temperatura;

    qsort(temps, n, sizeof(double), comparar_double);   /* ordenar */
    double mediana = calcular_mediana(temps, n);

    printf("\n=== Análisis estadístico de '%s' ===\n\n", nombre);
    printf("  Cantidad de lecturas: %d\n", n);
    printf("  Primera lectura:      %s %s\n", lecturas[0].fecha, lecturas[0].hora);
    printf("  Última lectura:       %s %s\n\n", lecturas[n - 1].fecha, lecturas[n - 1].hora);

    printf("  Temperatura mínima:   %.3f °C  (%s %s)\n",
           lecturas[pmin].temperatura, lecturas[pmin].fecha, lecturas[pmin].hora);
    printf("  Temperatura máxima:   %.3f °C  (%s %s)\n\n",
           lecturas[pmax].temperatura, lecturas[pmax].fecha, lecturas[pmax].hora);

    printf("  Media:                %.3f °C\n", media);
    printf("  Mediana:              %.3f °C\n", mediana);
    mostrar_modas(temps, n);

    printf("\n  Dispersión:\n");
    printf("  Varianza (muestral):  %.4f °C²\n", varianza);
    printf("  Desvío estándar:      %.3f °C   <- medida elegida\n", desvio);
    printf("  Rango (máx - mín):    %.3f °C\n\n", rango);

    /* Toda memoria pedida con malloc/realloc se devuelve con free */
    free(temps);
    free(lecturas);
    return 0;           /* 0 = terminó bien */
}
