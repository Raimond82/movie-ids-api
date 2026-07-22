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

# --- NUEVA FUNCIÓN: Generadora de URLs ---
def generar_urls_desde_ids(media_type: str, row) -> list:
    urls_generadas = []
    
    # 1. IMDb
    if row["imdb"]:
        urls_generadas.append(f"https://www.imdb.com/title/{row['imdb']}/")
        
    # 2. TMDB (cambia a /tv o /movie según el tipo)
    if row["tmdb"]:
        tipo_tmdb = "tv" if media_type == "series" else "movie"
        urls_generadas.append(f"https://www.themoviedb.org/{tipo_tmdb}/{row['tmdb']}")
        
    # 3. Filmaffinity (Asumimos que tu ID en la DB ya lleva "film" si es necesario, ej: film226427)
    if row["filmaffinity"]:
        urls_generadas.append(f"https://www.filmaffinity.com/es/{row['filmaffinity']}.html")
        
    # 4. Cine.com (Asumimos que tu campo 'slug' es el ID de cine.com)
    if row["cine_com"]:
        urls_generadas.append(f"https://www.cine.com/pelicula/{row['cine_com']}") 
        
    return urls_generadas
# ----------------------------------------

@app.get("/v1/resolve")
def resolve_id(
    type: str = Query(..., description="movie o series"), 
    source: str = Query(..., description="imdb, tmdb, filmaffinity, sensacine, cine_com"), 
    id: str = Query(...),
    fields: str = Query("all", description="Qué devolver: 'all' (todo), 'ids' (solo IDs) o 'links' (solo URLs)")
):
    
    valid_sources = ["imdb", "tmdb", "filmaffinity", "sensacine", "cine_com"]
    if source not in valid_sources:
        raise HTTPException(status_code=400, detail="Fuente no válida")
    
    if type not in ["movie", "series"]:
        raise HTTPException(status_code=400, detail="Tipo no válido")
        
    if fields not in ["all", "ids", "links"]:
        raise HTTPException(status_code=400, detail="El parámetro 'fields' debe ser: all, ids o links")

    db = get_db()
    cursor = db.cursor()
    query = f"SELECT * FROM media WHERE type = ? AND {source} = ?"
    cursor.execute(query, (type, id))
    row = cursor.fetchone()
    db.close()

    if not row:
        raise HTTPException(status_code=404, detail="No encontrada")

    # 1. Preparar el bloque de IDs
    identifiers = {
        "imdb": row["imdb"],
        "tmdb": row["tmdb"],
        "filmaffinity": row["filmaffinity"],
        "sensacine": row["sensacine"],
        "cine_com": row["cine_com"],
        "rotten_tomatoes": row["rotten_tomatoes"],
        "tvinsider": row["tvinsider"]
    }

    # 2. Preparar el bloque de Links (Generados + Extra)
    urls_generadas = generar_urls_desde_ids(type, row)
    
    # Leer los links extra de la base de datos
    extra_links = []
    if row["extra"]:
        try:
            extra_links = json.loads(row["extra"])
            if not isinstance(extra_links, list):
                extra_links = []
        except:
            extra_links = []
            
    # Unir y eliminar duplicados por si acaso (usamos set)
    all_links = list(set(urls_generadas + extra_links))

    # 3. Construir la respuesta final filtrando según el parámetro 'fields'
    response = {
        "success": True,
        "query": {"type": type, "source": source, "id": id}
    }

    if fields == "all":
        response["title"] = row["title"]
        response["identifiers"] = identifiers
        response["reference_links"] = all_links
    elif fields == "ids":
        response["title"] = row["title"] # Mantenemos el título para contexto
        response["identifiers"] = identifiers
    elif fields == "links":
        response["reference_links"] = all_links

    return response