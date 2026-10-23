# -*- coding: utf-8 -*-
"""
R1-01.5 · Perfilar cada tabla de los CCPC.

Uso (desde la raíz del repositorio):
    python src/catalogar.py                      # usa data/raw/ccpc
    python src/catalogar.py "D:\\ruta\\a\\ccpc"   # otra carpeta

Genera dos archivos en docs/:
    catalogo_esquemas.csv   una fila por columna × archivo (× hoja)
    inventario_archivos.csv una fila por archivo encontrado (nada se omite en silencio)
"""
import codecs
import csv
import re
import sys
from pathlib import Path

import pandas as pd

MUESTRA = 50_000                                  # filas que se leen para perfilar
ENCODINGS = ("utf-8-sig", "cp1252", "latin-1")    # se prueban en este orden
TABULAR = {".csv", ".txt", ".tsv"}
EXCEL = {".xlsx", ".xlsm", ".xls"}


def detectar_encoding(ruta):
    """Prueba cada encoding leyendo TODO el archivo por bloques. Devuelve (encoding, líneas)."""
    for enc in ENCODINGS:
        dec = codecs.getincrementaldecoder(enc)()
        lineas = 0
        try:
            with open(ruta, "rb") as f:
                while True:
                    bloque = f.read(8 * 1024 * 1024)
                    if not bloque:
                        break
                    dec.decode(bloque)
                    lineas += bloque.count(b"\n")
            dec.decode(b"", final=True)
            return enc, lineas
        except UnicodeDecodeError:
            continue
    return "latin-1", 0


def detectar_separador(ruta, enc):
    with open(ruta, "r", encoding=enc, errors="replace", newline="") as f:
        muestra = f.read(65536)
    try:
        return csv.Sniffer().sniff(muestra, delimiters=",;|\t").delimiter
    except csv.Error:
        primera = muestra.splitlines()[0] if muestra else ""
        return max(",;|\t", key=primera.count)


def detectar_anio(ruta, raiz):
    rel = str(ruta.relative_to(raiz)).lower()
    m = re.search(r"(20\d\d)", rel)
    anio = m.group(1) if m else "?"
    if "anticip" in rel:
        anio += "_anticipado"
    elif "prision" in rel or "prisión" in rel:
        anio += "_prision"
    return anio


def perfilar(df, base):
    """Una fila de catálogo por columna del DataFrame (leído todo como texto)."""
    filas = []
    n = len(df)
    for pos, col in enumerate(df.columns, 1):
        s = df[col]
        nulos = int(s.isna().sum())
        filas.append({**base, "posicion": pos, "columna": str(col), "filas_muestra": n,
                      "nulos_muestra": nulos,
                      "pct_nulos_muestra": round(100 * nulos / n, 2) if n else 0,
                      "unicos_muestra": int(s.nunique()),
                      "ejemplos": " | ".join(str(x) for x in s.dropna().unique()[:5])})
    return filas


def main():
    raiz = Path(sys.argv[1] if len(sys.argv) > 1 else "data/raw/ccpc").resolve()
    if not raiz.exists():
        sys.exit(f"No existe la carpeta: {raiz}\nEjecuta el script desde la raíz del repositorio o pasa la ruta.")

    catalogo, inventario, errores = [], [], []
    archivos = sorted(p for p in raiz.rglob("*") if p.is_file())
    print(f"Carpeta: {raiz}\nArchivos encontrados: {len(archivos)}\n")

    for ruta in archivos:
        rel = str(ruta.relative_to(raiz))
        ext = ruta.suffix.lower()
        anio = detectar_anio(ruta, raiz)
        info = {"anio": anio, "archivo": rel, "extension": ext, "tamano_mb": round(ruta.stat().st_size / 1e6, 2),
                "perfilado": "no", "nota": ""}
        try:
            if ext in TABULAR:
                enc, lineas = detectar_encoding(ruta)
                sep = detectar_separador(ruta, enc)
                df = pd.read_csv(ruta, sep=sep, encoding=enc, dtype=str, nrows=MUESTRA, engine="c",
                                 keep_default_na=False, na_values=[""], on_bad_lines="skip")
                base = {"anio": anio, "archivo": rel, "hoja": "", "encoding": enc,
                        "separador": "TAB" if sep == "\t" else sep, "filas_aprox": max(lineas - 1, 0)}
                catalogo += perfilar(df, base)
                info.update(perfilado="si", nota=f"{len(df.columns)} columnas, ~{max(lineas - 1, 0)} filas, {enc}, sep '{base['separador']}'")
            elif ext in EXCEL:
                xl = pd.ExcelFile(ruta)
                for hoja in xl.sheet_names:
                    df = xl.parse(hoja, dtype=str, nrows=MUESTRA)
                    base = {"anio": anio, "archivo": rel, "hoja": hoja, "encoding": "xlsx",
                            "separador": "", "filas_aprox": len(df)}
                    catalogo += perfilar(df, base)
                info.update(perfilado="si", nota=f"{len(xl.sheet_names)} hojas: {', '.join(map(str, xl.sheet_names))}")
            elif ext == ".zip":
                info["nota"] = "zip sin descomprimir: descomprímelo (R1-01.4) y vuelve a correr"
            else:
                info["nota"] = "tipo no tabular (documentación u otro): revisar a mano"
        except Exception as e:                    # un archivo malo no debe tumbar todo el proceso
            info["nota"] = f"ERROR: {type(e).__name__}: {e}"
            errores.append((rel, info["nota"]))
        inventario.append(info)
        print(f"[{info['perfilado']:>2}] {rel}  ->  {info['nota']}")

    docs = Path("docs")
    docs.mkdir(exist_ok=True)
    pd.DataFrame(catalogo).to_csv(docs / "catalogo_esquemas.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(inventario).to_csv(docs / "inventario_archivos.csv", index=False, encoding="utf-8-sig")

    print(f"\nColumnas catalogadas: {len(catalogo)}")
    print(f"Archivos perfilados: {sum(i['perfilado'] == 'si' for i in inventario)} de {len(inventario)}")
    print(f"Escrito: {(docs / 'catalogo_esquemas.csv').resolve()}")
    if errores:
        print("\nArchivos con error (pégamelos para revisarlos):")
        for r, e in errores:
            print(f"  - {r}: {e}")


if __name__ == "__main__":
    main()