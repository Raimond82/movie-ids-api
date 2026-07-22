from fastapi import FastAPI, HTTPException, Query
import sqlite3
import json

app = FastAPI(title="Multi-ID Resolver API", version="1.0.0")

def get_db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn

@app.get("/v1/resolve")
def resolve_id(type: str = Query(..., description="movie o series"), source: str = Query(..., description="imdb, tmdb, filmaffinity, sensacine, cine_com"), id: str = Query(...)):
    
    valid_sources = ["imdb", "tmdb", "filmaffinity", "sensacine", "cine_com"]
    if source not in valid_sources:
        raise HTTPException(status_code=400, detail="Fuente no válida")
    
    if type not in ["movie", "series"]:
        raise HTTPException(status_code=400, detail="Tipo no válido")

    db = get_db()
    cursor = db.cursor()
    query = f"SELECT * FROM media WHERE type = ? AND {source} = ?"
    cursor.execute(query, (type, id))
    row = cursor.fetchone()
    db.close()

    if not row:
        raise HTTPException(status_code=404, detail="No encontrada")

    # Si el campo extra tiene algo, lo convertimos de texto a lista de Python.
    # Si está vacío, dejamos una lista vacía []
    links = []
    if row["extra"]:
        try:
            links = json.loads(row["extra"])
            if not isinstance(links, list): # Por seguridad, nos aseguramos de que es una lista
                links = []
        except:
            links = []

    return {
        "success": True,
        "query": {"type": type, "source": source, "id": id},
        "title": row["title"],
        "identifiers": {
            "imdb": row["imdb"],
            "tmdb": row["tmdb"],
            "filmaffinity": row["filmaffinity"],
            "sensacine": row["sensacine"],
            "cine_com": row["cine_com"]
        },
        "reference_links": links # <-- Aquí devolvemos la lista de URLs
    }