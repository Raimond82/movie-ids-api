import sqlite3
import json

def importar_datos(archivo_json, archivo_db):
    with open(archivo_json, 'r', encoding='utf-8') as f:
        datos = json.load(f)

    conn = sqlite3.connect(archivo_db)
    cursor = conn.cursor()

    # 1. Crear tabla principal
    cursor.execute("DROP TABLE IF EXISTS media")
    cursor.execute('''
        CREATE TABLE media (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT,
            title TEXT,
            year TEXT,
            year_end TEXT,
            imdb TEXT,
            tmdb TEXT,
            filmaffinity TEXT,
            sensacine TEXT,
            cine_com TEXT,
            rotten_tomatoes TEXT,
            metacritic TEXT,
            extra TEXT,
            redes TEXT
        )
    ''')

    # 2. Crear tabla de AKAs
    cursor.execute("DROP TABLE IF EXISTS akas")
    cursor.execute('''
        CREATE TABLE akas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            media_id INTEGER,
            title TEXT,
            FOREIGN KEY (media_id) REFERENCES media(id) ON DELETE CASCADE
        )
    ''')

    # 3. Crear índices clave
    cursor.execute("CREATE INDEX idx_type_imdb ON media(type, imdb)")
    cursor.execute("CREATE INDEX idx_type_tmdb ON media(type, tmdb)")
    cursor.execute("CREATE INDEX idx_type_fa ON media(type, filmaffinity)")
    cursor.execute("CREATE INDEX idx_type_sensacine ON media(type, sensacine)")
    cursor.execute("CREATE INDEX idx_type_cinecom ON media(type, cine_com)")
    cursor.execute("CREATE INDEX idx_akas_media_id ON akas(media_id)")
    cursor.execute("CREATE INDEX idx_akas_title ON akas(title)")

    # 4. Insertar datos
    registros_insertados = 0
    akas_a_insertar = []

    for item in datos:
        # Insertar en Media
        cursor.execute('''
            INSERT INTO media (type, title, year, year_end, imdb, tmdb, filmaffinity, sensacine, cine_com, rotten_tomatoes, metacritic, extra, redes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            item['type'], item['title'], item['year'], item['year_end'], 
            item['imdb'], item['tmdb'], item['filmaffinity'], item['sensacine'],
            item['cine_com'], item['rotten_tomatoes'], item['metacritic'], 
            item['extra'], item['redes']
        ))
        
        # Obtener el ID que acaba de generar SQLite
        current_media_id = cursor.lastrowid
        registros_insertados += 1

        # Preparar AKAs para insertar en bloque
        akas_list = item.get('akas', [])
        if isinstance(akas_list, str):
            akas_list = json.loads(akas_list)
            
        for titulo_aka in akas_list:
            if titulo_aka: # Que no esté vacío
                akas_a_insertar.append((current_media_id, titulo_aka))

    # 5. Insertar todos los AKAs de golpe (más rápido)
    if akas_a_insertar:
        cursor.executemany("INSERT INTO akas (media_id, title) VALUES (?, ?)", akas_a_insertar)

    conn.commit()
    conn.close()
    print(f"¡Éxito! {registros_insertados} registros y {len(akas_a_insertar)} AKAs importados en {archivo_db}")

if __name__ == "__main__":
    importar_datos("datos_api_export.json", "database.db")