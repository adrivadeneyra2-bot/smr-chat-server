import sqlite3
import eventlet
import socketio
import time

sio = socketio.Server(cors_allowed_origins="*")
app = socketio.WSGIApp(sio)

usuarios_conectados = {}
admin_tricks_activos = set()
usuarios_bloqueados = {}

def init_db():
    conn = sqlite3.connect('chat_usuarios.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id TEXT PRIMARY KEY,
            ip_token TEXT NOT NULL,
            grupo TEXT DEFAULT 'usuario'
        )
    ''')
    
    try:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN grupo TEXT DEFAULT 'usuario'")
    except sqlite3.OperationalError:
        pass

    # Lista oficial de usuarios de la clase (incluyendo a Hamza)
    usuarios_autorizados = [
        ('adrian', '12', 'usuario'),
        ('javier', '11', 'usuario'),
        ('juan', '08', 'usuario'),
        ('marcos', '01', 'usuario'),
        ('noelia', '10', 'usuario'),
        ('rebeca', '09', 'usuario'),
        ('darius', '16', 'usuario'),
        ('hamza', '13', 'usuario'),       # <--- Añadido correctamente
        ('admin', '9947', 'administrador')
    ]
    
    for user_id, token, grupo in usuarios_autorizados:
        cursor.execute("""
            INSERT OR REPLACE INTO usuarios (id, ip_token, grupo) 
            VALUES (?, ?, ?)
        """, (user_id, token, grupo))
        
    conn.commit()
    conn.close()

def enviar_lista_usuarios_global():
    lista_online = list(set(info['id'] for info in usuarios_conectados.values()))
    sio.emit('actualizar_usuarios_online', lista_online)

@sio.event
def connect(sid, environ):
    print(f"[{sid}] Nueva conexión establecida (pendiente de autenticación).")

@sio.event
def autenticar(sid, data):
    user_id = data.get('id')
    user_token = data.get('ip')
    
    # 1. Verificar si el usuario ya está conectado
    for info in usuarios_conectados.values():
        if info['id'] == user_id:
            sio.emit('auth_result', {
                'success': False, 
                'message': f'El usuario "{user_id}" ya está conectado en otra sesión.'
            }, room=sid)
            return

    # 2. Verificar penalización de kick
    if user_id in usuarios_bloqueados:
        tiempo_actual = time.time()
        if tiempo_actual < usuarios_bloqueados[user_id]:
            tiempo_restante = int(usuarios_bloqueados[user_id] - tiempo_actual)
            sio.emit('auth_result', {
                'success': False, 
                'message': f'Estás expulsado por el admin. Inténtalo en {tiempo_restante} segundos.'
            }, room=sid)
            return
        else:
            del usuarios_bloqueados[user_id]

    # 3. Comprobar credenciales
    conn = sqlite3.connect('chat_usuarios.db')
    cursor = conn.cursor()
    cursor.execute("SELECT ip_token, grupo FROM usuarios WHERE id = ? AND ip_token = ?", (user_id, user_token))
    row = cursor.fetchone()
    conn.close()

    if row:
        grupo = row[1]
        print(f"[ACCESO PERMITIDO] Usuario '{user_id}' autenticado. Grupo: {grupo}")
        
        usuarios_conectados[sid] = {'id': user_id, 'grupo': grupo}
        
        sio.emit('auth_result', {
            'success': True, 
            'message': 'Acceso concedido',
            'grupo': grupo
        }, room=sid)
        
        sio.emit('nuevo_mensaje', {'user': 'SISTEMA', 'msg': f'--> El usuario [{user_id}] ({grupo}) ha entrado al chat.'})
        enviar_lista_usuarios_global()
    else:
        sio.emit('auth_result', {'success': False, 'message': 'ID o clave incorrectos'}, room=sid)

@sio.event
def mensaje_chat(sid, data):
    if sid not in usuarios_conectados:
        return

    user_info = usuarios_conectados[sid]
    user_id = user_info['id']
    grupo = user_info['grupo']
    msg = data.get('msg', '').strip()

    if grupo == 'administrador':
        if msg == '= /tricks on':
            admin_tricks_activos.add(sid)
            sio.emit('nuevo_mensaje', {'user': 'SISTEMA [LOCAL]', 'msg': '>>> Modo TRICKS ACTIVADO.'}, room=sid)
            return
        
        elif msg == '= /tricks off':
            admin_tricks_activos.discard(sid)
            sio.emit('nuevo_mensaje', {'user': 'SISTEMA [LOCAL]', 'msg': '>>> Modo TRICKS DESACTIVADO.'}, room=sid)
            return

        if sid in admin_tricks_activos:
            if msg.startswith('/kick '):
                target_user = msg.replace('/kick ', '').strip()
                target_sid = None
                for s, info in usuarios_conectados.items():
                    if info['id'] == target_user:
                        target_sid = s
                        break
                
                if target_sid:
                    usuarios_bloqueados[target_user] = time.time() + 60
                    sio.emit('kick_user', {'message': 'Has sido expulsado por el administrador. No podrás entrar en 60 segundos.'}, room=target_sid)
                    sio.emit('nuevo_mensaje', {'user': 'SISTEMA [LOCAL]', 'msg': f'>>> Usuario [{target_user}] expulsado correctamente.'}, room=sid)
                    sio.emit('nuevo_mensaje', {'user': 'SISTEMA', 'msg': f'⚡ El usuario [{target_user}] ha sido expulsado del chat por el admin.'})
                else:
                    sio.emit('nuevo_mensaje', {'user': 'SISTEMA [LOCAL]', 'msg': f'⚠️ Error: El usuario [{target_user}] no está conectado.'}, room=sid)
                return

            elif msg.startswith('/trolltext '):
                partes = msg.replace('/trolltext ', '', 1).split(' ', 1)
                if len(partes) == 2:
                    target_user = partes[0].strip()
                    texto_falso = partes[1].strip()
                    
                    conn = sqlite3.connect('chat_usuarios.db')
                    cursor = conn.cursor()
                    cursor.execute("SELECT id FROM usuarios WHERE id = ?", (target_user,))
                    existe_usuario = cursor.fetchone()
                    conn.close()
                    
                    if existe_usuario:
                        sio.emit('nuevo_mensaje', {
                            'user': target_user, 
                            'msg': texto_falso,
                            'color': '#ef4444' 
                        })
                        sio.emit('nuevo_mensaje', {'user': 'SISTEMA [LOCAL]', 'msg': f'>>> [Troll exitoso] Todos ven que [{target_user}] dijo: "{texto_falso}"'}, room=sid)
                    else:
                        sio.emit('nuevo_mensaje', {'user': 'SISTEMA [LOCAL]', 'msg': f'⚠️ Error: El usuario [{target_user}] no existe en la base de datos.'}, room=sid)
                else:
                    sio.emit('nuevo_mensaje', {'user': 'SISTEMA [LOCAL]', 'msg': '⚠️ Uso correcto: /trolltext <usuario> <mensaje>'}, room=sid)
                return

            elif msg.startswith('/comando de prueba'):
                sio.emit('nuevo_mensaje', {'user': 'ADMIN-BOT', 'msg': f'⚡ [ALERTA] El admin {user_id} ejecutó el comando de prueba.'})
                return

    sio.emit('nuevo_mensaje', data)

@sio.event
def disconnect(sid):
    if sid in admin_tricks_activos:
        admin_tricks_activos.discard(sid)

    if sid in usuarios_conectados:
        user_info = usuarios_conectados.pop(sid)
        user_id = user_info['id']
        print(f"[DESCONEXIÓN] El usuario '{user_id}' se ha desconectado.")
        sio.emit('nuevo_mensaje', {'user': 'SISTEMA', 'msg': f'<-- El usuario [{user_id}] se ha desconectado.'})
        enviar_lista_usuarios_global()

if __name__ == '__main__':
    init_db()
    print("[*] Servidor local arrancado en puerto 5000...")
    eventlet.wsgi.server(eventlet.listen(('', 5000)), app)
