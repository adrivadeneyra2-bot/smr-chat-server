import sqlite3
import eventlet
import socketio

sio = socketio.Server(cors_allowed_origins="*")
app = socketio.WSGIApp(sio)

# Diccionario para asociar cada conexión (sid) con su ID de usuario
usuarios_conectados = {}

def init_db():
    conn = sqlite3.connect('chat_usuarios.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id TEXT PRIMARY KEY,
            ip_token TEXT NOT NULL
        )
    ''')
    # Usuarios autorizados vinculados a sus respectivos números de PC de clase
    cursor.execute("INSERT OR IGNORE INTO usuarios (id, ip_token) VALUES ('adrian', '12')")
    cursor.execute("INSERT OR IGNORE INTO usuarios (id, ip_token) VALUES ('hamza', '13')")
    conn.commit()
    conn.close()

@sio.event
def connect(sid, environ):
    print(f"[{sid}] Nueva conexión establecida (pendiente de autenticación).")

@sio.event
def autenticar(sid, data):
    user_id = data.get('id')
    user_token = data.get('ip')
    
    conn = sqlite3.connect('chat_usuarios.db')
    cursor = conn.cursor()
    cursor.execute("SELECT ip_token FROM usuarios WHERE id = ? AND ip_token = ?", (user_id, user_token))
    row = cursor.fetchone()
    conn.close()

    if row:
        print(f"[ACCESO PERMITIDO] Usuario '{user_id}' autenticado.")
        usuarios_conectados[sid] = user_id
        sio.emit('auth_result', {'success': True, 'message': 'Acceso concedido'}, room=sid)
        
        # Anuncio global de que un usuario ha entrado al chat
        sio.emit('nuevo_mensaje', {'user': 'SISTEMA', 'msg': f'--> El usuario [{user_id}] ha entrado al chat.'})
    else:
        print(f"[ACCESO DENEGADO] Credenciales incorrectas para ID: '{user_id}'")
        sio.emit('auth_result', {'success': False, 'message': 'ID o clave incorrectos'}, room=sid)

@sio.event
def mensaje_chat(sid, data):
    sio.emit('nuevo_mensaje', data)

@sio.event
def disconnect(sid):
    if sid in usuarios_conectados:
        user_id = usuarios_conectados.pop(sid)
        print(f"[DESCONEXIÓN] El usuario '{user_id}' se ha desconectado.")
        # Anuncio global de que el usuario ha cerrado sesión
        sio.emit('nuevo_mensaje', {'user': 'SISTEMA', 'msg': f'<-- El usuario [{user_id}] se ha desconectado.'})
    else:
        print(f"[{sid}] Conexión cerrada sin autenticar.")

if __name__ == '__main__':
    init_db()
    print("[*] Servidor local arrancado en puerto 5000...")
    eventlet.wsgi.server(eventlet.listen(('', 5000)), app)
