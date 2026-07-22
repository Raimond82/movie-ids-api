from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import json

app = FastAPI(title="Multi-ID Resolver API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn

# --- FUNCIÓN: Generadora de URLs ---
def generar_urls_desde_ids(media_type: str, row) -> list:
    urls_generadas = []
    if row["imdb"]:
        urls_generadas.append(f"https://www.imdb.com/title/{row['imdb']}/")
    if row["tmdb"]:
        tipo_tmdb = "tv" if media_type == "series" else "movie"
        urls_generadas.append(f"https://www.themoviedb.org/{tipo_tmdb}/{row['tmdb']}")
    if row["filmaffinity"]:
        urls_generadas.append(f"https://www.filmaffinity.com/es/{row['filmaffinity']}.html")
    if row["cine_com"]:
        urls_generadas.append(f"https://www.cine.com/pelicula/{row['cine_com']}") 
    return urls_generadas

# --- FUNCIÓN NUEVA: Formateador de resultados (Para no repetir código) ---
def formatear_resultado(type: str, row, fields: str) -> dict:
    identifiers = {
        "imdb": row["imdb"],
        "tmdb": row["tmdb"],
        "filmaffinity": row["filmaffinity"],
        "sensacine": row["sensacine"],
        "cine_com": row["cine_com"],
        "rotten_tomatoes": row["rotten_tomatoes"],
        "tvinsider": row["tvinsider"]
    }

    urls_generadas = generar_urls_desde_ids(type, row)
    extra_links = []
    if row["extra"]:
        try:
            extra_links = json.loads(row["extra"])
            if not isinstance(extra_links, list): extra_links = []
        except: extra_links = []
            
    all_links = list(set(urls_generadas + extra_links))

    response = {
        "type": type,
        "title": row["title"],
        "year": row["year"],
        "year_end": row["year_end"]
    }

    if fields == "all":
        response["identifiers"] = identifiers
        response["reference_links"] = all_links
    elif fields == "ids":
        response["identifiers"] = identifiers
    elif fields == "links":
        response["reference_links"] = all_links

    return response

# =========================================================
# ENDPOINT 1: RESOLVER POR ID (El que ya teníamos)
# =========================================================
@app.get("/v1/resolve")
def resolve_id(
    type: str = Query(..., description="movie o series"), 
    source: str = Query(..., description="imdb, tmdb, filmaffinity, sensacine, cine_com"), 
    id: str = Query(...),
    fields: str = Query("all", description="Qué devolver: 'all', 'ids' o 'links'")
):
    valid_sources = ["imdb", "tmdb", "filmaffinity", "sensacine", "cine_com"]
    if source not in valid_sources: raise HTTPException(status_code=400, detail="Fuente no válida")
    if type not in ["movie", "series"]: raise HTTPException(status_code=400, detail="Tipo no válido")
    if fields not in ["all", "ids", "links"]: raise HTTPException(status_code=400, detail="El parámetro 'fields' debe ser: all, ids o links")

    db = get_db()
    cursor = db.cursor()
    query = f"SELECT * FROM media WHERE type = ? AND {source} = ?"
    cursor.execute(query, (type, id))
    row = cursor.fetchone()
    db.close()

    if not row: raise HTTPException(status_code=404, detail="No encontrada")

    return {
        "success": True,
        "query": {"type": type, "source": source, "id": id},
        "data": formatear_resultado(type, row, fields)
    }

# =========================================================
# ENDPOINT 2: BUSCAR POR TÍTULO Y AÑO (Actualizado)
# =========================================================
@app.get("/v1/search")
def search_by_title(
    title: str = Query(..., description="Título a buscar (coincidencias parciales)"),
    type: str = Query(None, description="Opcional: filtrar por 'movie' o 'series'"),
    year: int = Query(None, description="Opcional: año de referencia (aplica margen +-1)"),
    fields: str = Query("all", description="Qué devolver: 'all', 'ids' o 'links'"),
    limit: int = Query(10, description="Máximo número de resultados a devolver")
):
    if fields not in ["all", "ids", "links"]: raise HTTPException(status_code=400, detail="El parámetro 'fields' debe ser: all, ids o links")

    db = get_db()
    cursor = db.cursor()
    
    query = "SELECT * FROM media WHERE title LIKE ?"
    params = [f"%{title}%"]

    if type:
        if type not in ["movie", "series"]: raise HTTPException(status_code=400, detail="Tipo no válido")
        query += " AND type = ?"
        params.append(type)
        
    if year:
        year_min = year - 1
        year_max = year + 1
        
        if type == "movie":
            # Películas: el año debe estar dentro del margen
            query += " AND year BETWEEN ? AND ?"
            params.extend([year_min, year_max])
            
        elif type == "series":
            # Series: el rango de búsqueda (year_min - year_max) debe solaparse con el rango de la serie (year - year_end)
            # Lógica: La serie empieza antes o en year_max, Y (termina después o en year_min, O sigue emitiéndose)
            query += " AND year <= ? AND (year_end IS NULL OR year_end >= ?)"
            params.extend([year_max, year_min])
            
        else:
            # Si NO se especificó el tipo, mezclamos ambas lógicas con un OR
            query += " AND ( (type='movie' AND year BETWEEN ? AND ?) OR (type='series' AND year <= ? AND (year_end IS NULL OR year_end >= ?)) )"
            params.extend([year_min, year_max, year_max, year_min])

    query += " LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    db.close()

    if not rows:
        raise HTTPException(status_code=404, detail="No se encontraron resultados para esa búsqueda")

    resultados = []
    for row in rows:
        resultados.append(formatear_resultado(row["type"], row, fields))

    return {
        "success": True,
        "query": {"title": title, "type": type, "year": year},
        "total_results": len(resultados),
        "data": resultados
    }