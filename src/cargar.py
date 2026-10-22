"""
Carga idempotente de un informe de Biable a Postgres (Neon).

Uso:
  python src/cargar.py --archivo "Informe Centro de Costos Enero 2025.xls"
  python src/cargar.py --todos            # los 12 en orden cronologico
  python src/cargar.py --todos --dry-run  # solo parsea y valida, sin tocar la BD
  python src/cargar.py --init-schema      # ejecuta sql/schema.sql

Cada archivo carga SOLO su periodo mas reciente (modo incremental).
"""
import argparse
import glob
import os
import sys
from decimal import Decimal

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.dirname(__file__))
import etl_biable as etl

RAW = os.path.join("data", "raw")
CATS_CSV = os.path.join("data", "processed", "centro_categoria.csv")
SIN_CAT = "Sin categoría"
TOL = Decimal("0.01")
C = etl.COLUMNAS_CONCEPTO
ORDEN = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7,
         "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}


def archivos_ordenados():
    fs = [f for f in glob.glob(os.path.join(RAW, "*.xls")) if "copia" not in f.lower()]
    return sorted(fs, key=lambda f: next((n for m, n in ORDEN.items() if m in os.path.basename(f).lower()), 99))


def get_engine():
    load_dotenv()
    url = os.getenv("DATABASE_URL")
    if not url:
        sys.exit("Falta DATABASE_URL en .env")
    url = url.strip().strip("'\"")
    if url.startswith("psql "):
        url = url[5:].strip().strip("'\"")
    # forzar el driver psycopg2 (instalado), sea cual sea el esquema pegado
    url = "postgresql+psycopg2://" + url.split("://", 1)[1]
    return create_engine(url, pool_pre_ping=True)


def validar(df, total):
    """Compara suma de centros vs TOTAL. Devuelve (sumas, totales, difs, estado)."""
    sumas = {k: Decimal(str(round(df[k].sum(), 2))) for k in C}
    if total is None:
        return sumas, {k: None for k in C}, {k: None for k in C}, "SIN_TOTAL"
    tot = {k: Decimal(str(round(total[k], 2))) for k in C}
    dif = {k: sumas[k] - tot[k] for k in C}
    estado = "OK" if all(abs(d) <= TOL for d in dif.values()) else "DIFERENCIA"
    return sumas, tot, dif, estado


AJUSTES_CSV = os.path.join("config", "ajustes_manuales.csv")


def aplicar_ajustes(df, periodo):
    """Aplica correcciones documentadas de config/ajustes_manuales.csv.
    Solo si el valor de la fuente coincide con valor_original (si Biable corrige el dato, no se toca).
    Devuelve (df, lista de textos para carga_control.detalle)."""
    if not os.path.exists(AJUSTES_CSV):
        return df, []
    notas = []
    aj = pd.read_csv(AJUSTES_CSV, dtype={"codigo": str})
    for r in aj[aj.periodo == periodo].itertuples():
        m = df.centro_costo_codigo == r.codigo
        if not m.any():
            continue
        actual = float(df.loc[m, r.campo].iloc[0])
        if abs(actual - float(r.valor_original)) > 0.01:
            notas.append(f"AJUSTE OMITIDO {r.codigo}.{r.campo}: la fuente trae {actual}, se esperaba {r.valor_original}")
            continue
        df.loc[m, r.campo] = float(r.valor_nuevo)
        notas.append(f"AJUSTE {r.codigo}.{r.campo}: {r.valor_original} -> {r.valor_nuevo} ({r.motivo})")
    return df, notas


def cargar(path, engine, cats, dry_run=False):
    nombre_arch = os.path.basename(path)
    df = etl.extraer_bloques(path, modo="incremental")
    periodo = int(df["periodo"].iloc[0])
    total = etl.extraer_totales(path, modo="incremental").get(periodo)
    if df.duplicated("centro_costo_codigo").any():
        d = df[df.duplicated("centro_costo_codigo", keep=False)].centro_costo_codigo.unique()
        raise ValueError(f"Codigos duplicados en {nombre_arch}: {list(d)}")

    df, notas_ajuste = aplicar_ajustes(df, periodo)
    sumas, tot, dif, estado = validar(df, total)
    cat_de = dict(zip(cats.codigo.astype(str), cats.categoria))
    sin_mapa = [c for c in df.centro_costo_codigo if c not in cat_de]
    partes = notas_ajuste + ([f"{len(sin_mapa)} centros no estaban en la asignacion -> Sin categoría: {sin_mapa}"] if sin_mapa else [])
    detalle = " | ".join(partes) or None
    resumen = {"archivo": nombre_arch, "periodo": periodo, "centros": len(df), "estado": estado,
               "dif_max": max(abs(d) for d in dif.values()) if total else None, "sin_mapa": sin_mapa,
               "ajustes": len([n for n in notas_ajuste if n.startswith("AJUSTE ")]) - len([n for n in notas_ajuste if n.startswith("AJUSTE OMITIDO")]),
               "omitidos": [n for n in notas_ajuste if n.startswith("AJUSTE OMITIDO")]}
    if dry_run:
        return resumen

    with engine.begin() as cx:  # transaccion: todo o nada
        for nom in set(list(cat_de.values()) + [SIN_CAT]):
            cx.execute(text("INSERT INTO dim_categoria(nombre) VALUES (:n) ON CONFLICT (nombre) DO NOTHING"), {"n": nom})
        ids_cat = dict(cx.execute(text("SELECT nombre, categoria_id FROM dim_categoria")).all())
        for r in df.itertuples():
            # el centro nuevo toma su categoria; uno existente NO cambia de categoria, solo de nombre
            cx.execute(text("""INSERT INTO dim_centro_costo(codigo, nombre, categoria_id)
                               VALUES (:c, :n, :k)
                               ON CONFLICT (codigo) DO UPDATE SET nombre = EXCLUDED.nombre"""),
                       {"c": r.centro_costo_codigo, "n": r.centro_costo_nombre or r.centro_costo_codigo,
                        "k": ids_cat[cat_de.get(r.centro_costo_codigo, SIN_CAT)]})
        ids_centro = dict(cx.execute(text("SELECT codigo, centro_id FROM dim_centro_costo")).all())
        filas = [{"p": periodo, "c": ids_centro[r.centro_costo_codigo], **{k: getattr(r, k) for k in C}}
                 for r in df.itertuples()]
        cols = ", ".join(C)
        vals = ", ".join(f":{k}" for k in C)
        upd = ", ".join(f"{k}=EXCLUDED.{k}" for k in C)
        cx.execute(text(f"""INSERT INTO hechos_costos(periodo, centro_id, {cols}) VALUES (:p, :c, {vals})
                            ON CONFLICT (periodo, centro_id) DO UPDATE SET {upd}, cargado_en = now()"""), filas)
        p = {"archivo": nombre_arch, "periodo": periodo, "n": len(df), "estado": estado, "detalle": detalle}
        for k in C:
            p[f"s_{k}"], p[f"t_{k}"], p[f"d_{k}"] = sumas[k], tot[k], dif[k]
        cols_ctl = ", ".join([f"suma_{k}" for k in C] + [f"total_{k}" for k in C] + [f"dif_{k}" for k in C])
        vals_ctl = ", ".join([f":s_{k}" for k in C] + [f":t_{k}" for k in C] + [f":d_{k}" for k in C])
        upd_ctl = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols_ctl.split(", "))
        cx.execute(text(f"""INSERT INTO carga_control(archivo, periodo, total_centros, estado, detalle, {cols_ctl})
                            VALUES (:archivo, :periodo, :n, :estado, :detalle, {vals_ctl})
                            ON CONFLICT (archivo, periodo) DO UPDATE SET total_centros=EXCLUDED.total_centros,
                              estado=EXCLUDED.estado, detalle=EXCLUDED.detalle, fecha_carga=now(), {upd_ctl}"""), p)
    return resumen


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--archivo")
    g.add_argument("--todos", action="store_true")
    g.add_argument("--init-schema", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if a.init_schema:
        eng = get_engine()
        with eng.begin() as cx:
            cx.connection.cursor().execute(open("sql/schema.sql", encoding="utf-8").read())
        print("Esquema aplicado.")
        return

    if not os.path.exists(CATS_CSV):
        sys.exit(f"Falta {CATS_CSV}: ejecuta primero src/generar_categorias.py")
    cats = pd.read_csv(CATS_CSV, dtype=str)
    if (cats.estado == "AMBIGUO").any() and not a.dry_run:
        sys.exit("Hay centros AMBIGUOS en la asignacion; decide y registra en data/processed/decisiones_categoria.csv")

    lista = archivos_ordenados() if a.todos else [a.archivo if os.path.exists(a.archivo) else os.path.join(RAW, a.archivo)]
    eng = None if a.dry_run else get_engine()
    for f in lista:
        try:
            r = cargar(f, eng, cats, a.dry_run)
        except Exception as e:  # nunca mostrar la URL de conexion
            msg = str(e).split("\n")[0]
            sys.exit(f"ERROR en {os.path.basename(f)}: {type(e).__name__}: {msg[:300]}")
        print(f"{r['periodo']} | {r['centros']:>3} centros | {r['estado']:<10} | dif max={r['dif_max']} | {r['archivo']}")
        if r["ajustes"]:
            print(f"      {r['ajustes']} ajuste(s) manual(es) aplicado(s) (ver config/ajustes_manuales.csv)")
        for o in r["omitidos"]:
            print("      " + o)
        if r["sin_mapa"]:
            print(f"      aviso: sin categoria asignada -> Sin categoría: {r['sin_mapa']}")


if __name__ == "__main__":
    main()
