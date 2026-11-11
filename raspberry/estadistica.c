/*
 * estadistica.c - TPI Infomeca - Parte B: estadística de las lecturas
 *
 * Lee registro_temperaturas.csv (lo genera la estación) y muestra:
 * cantidad de lecturas, mínima y máxima con fecha y hora, media, mediana,
 * moda y desvío estándar.
 *
 * Compilar:  gcc -Wall -o estadistica estadistica.c -lm
 * Correr:    ./estadistica
 */

#include <stdio.h>      /* fopen, fgets, sscanf, printf, fclose */
#include <stdlib.h>     /* malloc, realloc, free, qsort         */
#include <math.h>       /* sqrt (por eso se compila con -lm)    */

#define ARCHIVO "registro_temperaturas.csv"

/* Una lectura = una línea del CSV, por ejemplo:
   2026-11-09,01:50:24,26.875,ALTA
   Cada texto tiene un lugar más para el '\0' que marca su fin. */
typedef struct {
    char fecha[11];         /* "2026-11-09" = 10 caracteres + '\0' */
    char hora[9];           /* "01:50:24"   =  8 caracteres + '\0' */
    double temperatura;
    char tendencia[10];     /* "SIN_DATOS"  =  9 caracteres + '\0' */
} Lectura;

/* qsort necesita una función que compare dos elementos:
   devuelve negativo si a < b, positivo si a > b y 0 si son iguales. */
int comparar(const void *a, const void *b)
{
    double x = *(const double *)a;
    double y = *(const double *)b;
    if (x < y) return -1;
    if (x > y) return 1;
    return 0;
}

int main(void)
{
    FILE *archivo = fopen(ARCHIVO, "r");
    if (archivo == NULL) {
        printf("No se pudo abrir %s\n", ARCHIVO);
        return 1;
    }

    /* ---------- 1. Cargar el archivo en un arreglo dinámico ---------- */
    /* No se sabe cuántas lecturas hay: se empieza con lugar para 16 y,
       cuando se llena, se duplica con realloc (16, 32, 64...). */
    int capacidad = 16;
    int n = 0;
    Lectura *lecturas = malloc(capacidad * sizeof(Lectura));
    if (lecturas == NULL) {
        printf("No hay memoria\n");
        fclose(archivo);
        return 1;
    }

    char linea[128];
    fgets(linea, sizeof(linea), archivo);       /* saltear el encabezado */

    while (fgets(linea, sizeof(linea), archivo) != NULL) {
        if (n == capacidad) {
            capacidad = capacidad * 2;
            /* Se usa un puntero auxiliar: si realloc falla devuelve NULL,
               y así no se pierde el arreglo original. */
            Lectura *nuevo = realloc(lecturas, capacidad * sizeof(Lectura));
            if (nuevo == NULL) {
                printf("No hay memoria\n");
                free(lecturas);
                fclose(archivo);
                return 1;
            }
            lecturas = nuevo;
        }
        /* sscanf separa la línea por las comas. %10[^,] = hasta 10
           caracteres que no sean coma; los límites evitan escribir fuera
           de los arreglos. Devuelve cuántos campos leyó: si no son 4, la
           línea está mal (por ejemplo, vacía) y no se cuenta. */
        Lectura l;
        if (sscanf(linea, "%10[^,],%8[^,],%lf,%9s",
                   l.fecha, l.hora, &l.temperatura, l.tendencia) == 4) {
            lecturas[n] = l;
            n++;
        }
    }
    fclose(archivo);

    if (n == 0) {
        printf("El archivo no tiene lecturas\n");
        free(lecturas);
        return 1;
    }

    /* ---------- 2. Mínima, máxima y media ---------- */
    int pmin = 0, pmax = 0;         /* posiciones de la mínima y la máxima */
    double suma = 0;
    for (int i = 0; i < n; i++) {
        if (lecturas[i].temperatura < lecturas[pmin].temperatura) pmin = i;
        if (lecturas[i].temperatura > lecturas[pmax].temperatura) pmax = i;
        suma += lecturas[i].temperatura;
    }
    double media = suma / n;

    /* ---------- 3. Desvío estándar (muestral) ---------- */
    /* Raíz del promedio de las distancias a la media al cuadrado. Se divide
       por n - 1 y no por n porque las lecturas son una MUESTRA del ambiente. */
    double suma_cuadrados = 0;
    for (int i = 0; i < n; i++) {
        double d = lecturas[i].temperatura - media;
        suma_cuadrados += d * d;
    }
    double desvio = (n > 1) ? sqrt(suma_cuadrados / (n - 1)) : 0;

    /* ---------- 4. Mediana y moda: necesitan los valores ordenados ---------- */
    /* Se copian las temperaturas a otro arreglo dinámico para ordenarlas
       sin desordenar 'lecturas', que guarda las fechas. */
    double *t = malloc(n * sizeof(double));
    if (t == NULL) {
        printf("No hay memoria\n");
        free(lecturas);
        return 1;
    }
    for (int i = 0; i < n; i++) {
        t[i] = lecturas[i].temperatura;
    }
    qsort(t, n, sizeof(double), comparar);

    /* Mediana: el valor del medio. Si n es par, el promedio de los dos centrales. */
    double mediana;
    if (n % 2 == 1) {
        mediana = t[n / 2];
    } else {
        mediana = (t[n / 2 - 1] + t[n / 2]) / 2;
    }

    /* Moda: ordenados, los valores iguales quedan juntos. Se cuenta cada
       "racha" de iguales y se guarda la más larga. Si hay empate, queda la
       primera (la menor). Se puede comparar con == porque todos vienen del
       mismo formato de texto con 3 decimales: textos iguales dan el mismo double. */
    double moda = t[0];
    int veces_moda = 1;
    int racha = 1;
    for (int i = 1; i < n; i++) {
        if (t[i] == t[i - 1]) {
            racha++;
        } else {
            racha = 1;
        }
        if (racha > veces_moda) {
            veces_moda = racha;
            moda = t[i];
        }
    }

    /* ---------- 5. Resultados ---------- */
    printf("\n=== Estadística de %s ===\n\n", ARCHIVO);
    printf("Cantidad de lecturas: %d\n", n);
    printf("Mínima:  %.3f °C  (%s %s)\n",
           lecturas[pmin].temperatura, lecturas[pmin].fecha, lecturas[pmin].hora);
    printf("Máxima:  %.3f °C  (%s %s)\n",
           lecturas[pmax].temperatura, lecturas[pmax].fecha, lecturas[pmax].hora);
    printf("Media:   %.3f °C\n", media);
    printf("Mediana: %.3f °C\n", mediana);
    if (veces_moda == 1) {
        printf("Moda:    no hay (ningún valor se repite)\n");
    } else {
        printf("Moda:    %.3f °C  (%d veces)\n", moda, veces_moda);
    }
    printf("Desvío estándar: %.3f °C\n\n", desvio);

    /* Devolver toda la memoria pedida con malloc/realloc */
    free(t);
    free(lecturas);
    return 0;
}
