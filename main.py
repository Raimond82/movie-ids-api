from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import json

app = FastAPI(title="Multi-ID Resolver API", version="1.1.0") # Subimos versión

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- SISTEMA DE CACHÉ ---
cache_dict = {}
CACHE_LIMIT = 500

def get_cache_key(query_params):
    return json.dumps(query_params, sort_keys=True)

def get_from_cache(key):
    return cache_dict.get(key)

def set_in_cache(key, value):
    if len(cache_dict) >= CACHE_LIMIT:
        cache_dict.pop(next(iter(cache_dict)))
    cache_dict[key] = value

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

# --- FUNCIÓN: Formateador dinámico ---
def formatear_resultado(type: str, row, fields_set: set) -> dict:
    def limpiar(val):
        if val is None or val == "None" or val == "":
            return None
        return val

    # Base de la respuesta (siempre se devuelve)
    response = {
        "type": type,
        "title": limpiar(row["title"]),
        "year": limpiar(row["year"]),
        "year_end": limpiar(row["year_end"])
    }

    # Si el set está vacío, significa que no se pasó el parámetro (devolver todo)
    devolver_todo = len(fields_set) == 0

    # 1. IDENTIFIERS
    if devolver_todo or 'ids' in fields_set:
        response["identifiers"] = {
            "imdb": limpiar(row["imdb"]),
            "tmdb": limpiar(row["tmdb"]),
            "filmaffinity": limpiar(row["filmaffinity"]),
            "sensacine": limpiar(row["sensacine"]),
            "cine_com": limpiar(row["cine_com"]),
            "rotten_tomatoes": limpiar(row["rotten_tomatoes"]),
            "metacritic": limpiar(row["metacritic"])
        }

    # 2. REFERENCE LINKS (URLs de webs + campo extra)
    if devolver_todo or 'links' in fields_set:
        urls_generadas = generar_urls_desde_ids(type, row)
        extra_links = []
        if row["extra"]:
            try:
                parsed = json.loads(row["extra"])
                if isinstance(parsed, list): extra_links.extend(parsed)
            except: pass
        response["reference_links"] = list(set(urls_generadas + extra_links))

    # 3. SOCIAL LINKS (Campo redes)
    if devolver_todo or 'social' in fields_set:
        social_links = []
        if row["redes"]:
            try:
                parsed = json.loads(row["redes"])
                if isinstance(parsed, list): social_links = parsed
            except: pass
        response["social_links"] = social_links

    return response

# =========================================================
@app.get("/")
def health_check():
    return {"status": "ok", "message": "Multi-ID Resolver API is running"}

# =========================================================
@app.get("/v1/resolve")
def resolve_id(
    type: str = Query(..., description="movie o series"), 
    source: str = Query(..., description="imdb, tmdb, filmaffinity, sensacine, cine_com, rotten_tomatoes, metacritic"), 
    id: str = Query(...),
    fields: str = Query("", description="Lista separada por comas: 'ids,links,social'. Vacío devuelve todo.")
):
    valid_sources = ["imdb", "tmdb", "filmaffinity", "sensacine", "cine_com", "rotten_tomatoes", "metacritic"]
    if source not in valid_sources: raise HTTPException(status_code=400, detail="Fuente no válida")
    if type not in ["movie", "series"]: raise HTTPException(status_code=400, detail="Tipo no válido")

    # NUEVA LÓGICA DE VALIDACIÓN DE FIELDS
    valid_fields = {"ids", "links", "social"}
    fields_list = [f.strip().lower() for f in fields.split(',') if f.strip()]
    invalid = set(fields_list) - valid_fields
    if invalid:
        raise HTTPException(status_code=400, detail=f"Campos no válidos en 'fields': {', '.join(invalid)}. Opciones: ids, links, social")
    fields_set = set(fields_list)

    cache_key = get_cache_key(locals())
    cached_data = get_from_cache(cache_key)
    if cached_data: return cached_data

    db = get_db()
    cursor = db.cursor()
    query = f"SELECT * FROM media WHERE type = ? AND {source} = ?"
    cursor.execute(query, (type, id))
    row = cursor.fetchone()
    db.close()

    if not row: raise HTTPException(status_code=404, detail="No encontrada")

    response = {
        "success": True,
        "query": {"type": type, "source": source, "id": id},
        "data": formatear_resultado(type, row, fields_set)
    }
    set_in_cache(cache_key, response)
    return response

# =========================================================
@app.get("/v1/search")
def search_by_title(
    title: str = Query(..., description="Título a buscar (busca en akas)"),
    type: str = Query(None, description="Opcional: 'movie' o 'series'"),
    year: int = Query(None, description="Opcional: año de referencia (margen +-1)"),
    fields: str = Query("", description="Lista separada por comas: 'ids,links,social'. Vacío devuelve todo."),
    limit: int = Query(10, description="Resultados por página (máx 50)"),
    offset: int = Query(0, description="Para paginar: 0, 10, 20...")
):
    # NUEVA LÓGICA DE VALIDACIÓN DE FIELDS
    valid_fields = {"ids", "links", "social"}
    fields_list = [f.strip().lower() for f in fields.split(',') if f.strip()]
    invalid = set(fields_list) - valid_fields
    if invalid:
        raise HTTPException(status_code=400, detail=f"Campos no válidos en 'fields': {', '.join(invalid)}. Opciones: ids, links, social")
    fields_set = set(fields_list)
    
    limit = min(limit, 50)

    cache_key = get_cache_key(locals())
    cached_data = get_from_cache(cache_key)
    if cached_data: return cached_data

    db = get_db()
    cursor = db.cursor()
    
    query = """
        SELECT DISTINCT media.* FROM media 
        JOIN akas ON media.id = akas.media_id 
        WHERE akas.title LIKE ?
    """
    params = [f"%{title}%"]

    if type:
        if type not in ["movie", "series"]: raise HTTPException(status_code=400, detail="Tipo no válido")
        query += " AND media.type = ?"
        params.append(type)
        
    if year:
        year_min = year - 1
        year_max = year + 1
        if type == "movie":
            query += " AND media.year BETWEEN ? AND ?"
            params.extend([year_min, year_max])
        elif type == "series":
            query += " AND media.year <= ? AND (media.year_end IS NULL OR media.year_end >= ?)"
            params.extend([year_max, year_min])
        else:
            query += " AND ( (media.type='movie' AND media.year BETWEEN ? AND ?) OR (media.type='series' AND media.year <= ? AND (media.year_end IS NULL OR media.year_end >= ?)) )"
            params.extend([year_min, year_max, year_max, year_min])

    query += " LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    cursor.execute(query, params)
    rows = cursor.fetchall()
    db.close()

    if not rows:
        raise HTTPException(status_code=404, detail="No se encontraron resultados")

    resultados = []
    for row in rows:
        resultados.append(formatear_resultado(row["type"], row, fields_set))

    response = {
        "success": True,
        "query": {"title": title, "type": type, "year": year, "limit": limit, "offset": offset},
        "total_results": len(resultados),
        "data": resultados
    }
    set_in_cache(cache_key, response)
    return response