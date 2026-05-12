from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
import pyodbc
import os #os lee variables del sistema
from dotenv import load_dotenv #carga datos secretos.
from datetime import datetime, timedelta #Me imagino que para la hora

load_dotenv() #carga variables ocultas (servidor, usuario, contraseña, etc) desde el archivo .env

app = Flask(__name__)

#agrego a continuación porque necesita "session" para cifrar los logins
app.secret_key = os.getenv('SECRET_KEY', "Passwort")

 #conexión a la base de datos, cambiar los datos en el archivo .env (esto cambia por maquina)   
def get_db_connection():
    driver = os.getenv('DB_DRIVER')
    server = os.getenv('DB_SERVER')
    database = os.getenv('DB_NAME')

    conn_str = (
        f"DRIVER={{{driver}}};"
        f"SERVER={server};"
        f"DATABASE={database};"
        "Trusted_Connection=yes;"
        "TrustServerCertificate=yes;"
    )

    print(f"Intentando conectar con: {conn_str}")

    return pyodbc.connect(conn_str)

#página de home
@app.route('/')
def home():
    # Si "usuario" NO está en la sesión, lo mandamos al login
    if 'usuario' not in session:
        return redirect(url_for('login'))
    
    return render_template('home.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

#página de login
@app.route("/login", methods=["POST", "GET"])
def login():
    if request.method == "POST":
        user = request.form["usuario"]
        carnet = request.form["carnet_us"]
        cohorte = request.form["cohorte"] # en variable local

        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            # Verificar si el usuario ya existe por carnet (campo UNIQUE)
            cursor.execute("SELECT usuario FROM Usuarios WHERE carnet_us = ?", (carnet,))
            usuario_existente = cursor.fetchone()

            if usuario_existente:
                # El usuario ya estaba registrado: recuperar su nombre de la BD
                user = usuario_existente[0]
                print(f"Usuario '{user}' ya registrado, iniciando sesión.")
            else:
                # Usuario nuevo: insertarlo en la BD
                cursor.execute(
                    "INSERT INTO Usuarios (usuario, carnet_us, cohorte_sel) VALUES (?, ?, ?)",
                    (user, carnet, cohorte)
                )
                conn.commit()
                print("Nuevo usuario guardado exitosamente.")

            # Registrar el ingreso con fecha y hora actual
            cursor.execute(
                "INSERT INTO LogsIngreso (carnet_us, fecha_hora_ingreso) VALUES (?, GETDATE())",
                (carnet,)
            )
            conn.commit()

            cursor.close()
            conn.close()
            print("Datos guardados exitosamente")

            # Crear la sesión
            session['usuario'] = user
            return redirect(url_for('home'))

        except Exception as e:
            print(f"Error al conectar o insertar: {e}")
            return render_template("login.html", error=f"Error al iniciar sesión: {e}")
    else:
        return render_template("login.html") #muestra el formulario de login

# página para mostrar las salas
@app.route('/salas')
def lista_salas():
    if 'usuario' not in session:
        return redirect(url_for('login'))

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id_sala, nombre, capacidad_max, disponible
            FROM Salas
            WHERE disponible = 1
        """)

        filas = cursor.fetchall()

        salas = []
        for fila in filas:
            salas.append({
                'id_sala': fila.id_sala,
                'nombre': fila.nombre,
                'capacidad_max': fila.capacidad_max,
                'disponible': fila.disponible
            })

        cursor.close()
        conn.close()

        return render_template('salas.html', salas=salas)

    except Exception as e:
        return f"Error al cargar salas: {e}", 500

#Página salas
@app.route('/reservar_sala', methods=['POST'])
def reservar_sala():
    if 'usuario' not in session:
        return redirect(url_for('login'))

    # 1. Recolección de datos del formulario
    id_sala = request.form['id_sala']
    hora_inicio_str = request.form['hora_inicio'] # Formato HH:MM
    hora_fin_str = request.form['hora_fin']
    cantidad_personas = int(request.form['cantidad_personas']) 

    # Datos de acompañantes
    acomp_nombre = request.form['acomp_nombre']
    acomp_carnet = request.form['acomp_carnet']
    acomp_cohorte = request.form['acomp_cohorte']

    # 2. Conversión a objetos de tiempo para validar
    h_inicio = datetime.strptime(hora_inicio_str, '%H:%M').time()
    h_fin = datetime.strptime(hora_fin_str, '%H:%M').time() 
    
    # 3. VALIDACIONES
    # A. Horario permitido (6:00 AM a 6:00 PM)
    limite_inf = datetime.strptime("06:00", "%H:%M").time()
    limite_sup = datetime.strptime("18:00", "%H:%M").time()

    if h_inicio < limite_inf or h_fin > limite_sup:
        return "Error: El horario permitido es de 6:00 AM a 6:00 PM.", 400

    # B. Duración máxima (2 horas)
    # Convertimos a datetime para restar
    dt_inicio = datetime.combine(datetime.today(), h_inicio)
    dt_fin = datetime.combine(datetime.today(), h_fin)
    duracion = dt_fin - dt_inicio

    if duracion.total_seconds() > 7200: # 7200 segundos = 2 horas
        return "Error: La reserva no puede exceder las 2 horas.", 400
    
    if duracion.total_seconds() <= 0:
        return "Error: La hora de fin debe ser posterior a la de inicio.", 400

    # C. Cantidad de personas (Mín 2, Máx 6)
    if cantidad_personas < 2 or cantidad_personas > 6:
        return "Error: La capacidad debe ser de 2 a 6 personas.", 400

    # 4. Proceso de Inserción (Si todo es válido)
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT id_usuario FROM Usuarios WHERE usuario = ?", (session['usuario'],))
                user_id = cursor.fetchone()[0]
                # Insertar reserva
                query_reserva = """
                    INSERT INTO ReservasSalas (id_usuario, id_sala, fecha, hora_inicio, hora_fin, cantidad_personas, estado)
                    OUTPUT INSERTED.id_reserva
                    VALUES (?, ?, GETDATE(), ?, ?, ?, 'Activa')
                """
                cursor.execute(query_reserva, (user_id, id_sala, hora_inicio_str, hora_fin_str, cantidad_personas))
                id_nueva_reserva = cursor.fetchone()[0]

                # Insertar acompañante
                query_acomp = "INSERT INTO AcompañantesReserva (id_reserva, nombre_completo, carnet, cohorte) VALUES (?, ?, ?, ?)"
                cursor.execute(query_acomp, (id_nueva_reserva, acomp_nombre, acomp_carnet, acomp_cohorte))

                # Marcar sala como ocupada
                cursor.execute("UPDATE Salas SET disponible = 0 WHERE id_sala = ?", (id_sala,))
                conn.commit()
        
        return redirect(url_for('lista_salas'))
    except Exception as e:
        return f"Error en la base de datos: {e}", 500

# ============================================================
# KITE - Página principal de selección
# ============================================================

@app.route('/kite')
def kite():
    if 'usuario' not in session:
        return redirect(url_for('login'))
    return render_template('kite.html')


# ---- IMPRESORAS 3D ----

@app.route('/kite/impresoras')
def kite_impresoras():
    if 'usuario' not in session:
        return redirect(url_for('login'))
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Obtener impresoras disponibles
        cursor.execute("SELECT id_impresora, nombre, codigo FROM Impresoras3D WHERE disponible = 1")
        impresoras = [{'id': f[0], 'nombre': f[1], 'codigo': f[2]} for f in cursor.fetchall()]

        # Calcular gramos usados en el ciclo activo por el usuario actual
        cursor.execute("""
            SELECT ISNULL(SUM(ri.gramos), 0)
            FROM ReservasImpresora3D ri
            JOIN Usuarios u ON ri.id_usuario = u.id_usuario
            JOIN CiclosAcademicos ca ON ri.fecha BETWEEN ca.fecha_inicio AND DATEADD(day,1,ca.fecha_fin)
            WHERE u.usuario = ? AND ca.activo = 1
        """, (session['usuario'],))
        gramos_usados = cursor.fetchone()[0]

        cursor.close()
        conn.close()
        return render_template('kite_impresoras.html', impresoras=impresoras, gramos_usados=gramos_usados)
    except Exception as e:
        return f"Error al cargar impresoras: {e}", 500


@app.route('/reservar_impresora', methods=['POST'])
def reservar_impresora():
    if 'usuario' not in session:
        return redirect(url_for('login'))

    id_impresora = request.form['id_impresora']
    tiempo_uso   = request.form['tiempo_uso']
    tipo_trabajo = request.form['tipo_trabajo']
    filamento    = request.form['filamento']
    gramos       = int(request.form['gramos'])

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Obtener id_usuario de la sesión
        cursor.execute("SELECT id_usuario FROM Usuarios WHERE usuario = ?", (session['usuario'],))
        id_usuario = cursor.fetchone()[0]

        # Verificar gramos acumulados en el ciclo activo
        cursor.execute("""
            SELECT ISNULL(SUM(ri.gramos), 0)
            FROM ReservasImpresora3D ri
            JOIN CiclosAcademicos ca ON ri.fecha BETWEEN ca.fecha_inicio AND DATEADD(day,1,ca.fecha_fin)
            WHERE ri.id_usuario = ? AND ca.activo = 1
        """, (id_usuario,))
        gramos_usados = cursor.fetchone()[0]

        # Validar que no exceda el límite de 750g por ciclo
        if gramos_usados + gramos > 750:
            cursor.execute("SELECT id_impresora, nombre, codigo FROM Impresoras3D WHERE disponible = 1")
            impresoras = [{'id': f[0], 'nombre': f[1], 'codigo': f[2]} for f in cursor.fetchall()]
            cursor.close()
            conn.close()
            return render_template('kite_impresoras.html',
                impresoras=impresoras,
                gramos_usados=gramos_usados,
                error=f"No puedes reservar {gramos}g. Llevas {gramos_usados}g usados este ciclo (límite: 750g).")

        # Obtener nombre de impresora para el mensaje de éxito
        cursor.execute("SELECT nombre FROM Impresoras3D WHERE id_impresora = ?", (id_impresora,))
        nombre_imp = cursor.fetchone()[0]

        # Insertar reserva
        cursor.execute("""
            INSERT INTO ReservasImpresora3D (id_usuario, id_impresora, tiempo_uso, tipo_trabajo, filamento, gramos)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (id_usuario, id_impresora, tiempo_uso, tipo_trabajo, filamento, gramos))

        # Marcar impresora como no disponible
        cursor.execute("UPDATE Impresoras3D SET disponible = 0 WHERE id_impresora = ?", (id_impresora,))
        conn.commit()
        cursor.close()
        conn.close()

        flash(f"Se ha prestado con éxito {nombre_imp}", 'success')
        return redirect(url_for('kite_impresoras'))
    except Exception as e:
        return f"Error: {e}", 500


# ---- CNC ----

@app.route('/kite/cnc')
def kite_cnc():
    if 'usuario' not in session:
        return redirect(url_for('login'))
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id_cnc, nombre, codigo FROM MaquinasCNC WHERE disponible = 1")
        maquinas = [{'id': f[0], 'nombre': f[1], 'codigo': f[2]} for f in cursor.fetchall()]
        cursor.close()
        conn.close()
        return render_template('kite_cnc.html', maquinas=maquinas)
    except Exception as e:
        return f"Error al cargar CNC: {e}", 500


@app.route('/reservar_cnc', methods=['POST'])
def reservar_cnc():
    if 'usuario' not in session:
        return redirect(url_for('login'))

    id_cnc       = request.form['id_cnc']
    tiempo_uso   = request.form['tiempo_uso']
    tipo_trabajo = request.form['tipo_trabajo']
    material     = request.form['material']

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT id_usuario FROM Usuarios WHERE usuario = ?", (session['usuario'],))
        id_usuario = cursor.fetchone()[0]

        cursor.execute("SELECT nombre FROM MaquinasCNC WHERE id_cnc = ?", (id_cnc,))
        nombre_cnc = cursor.fetchone()[0]

        cursor.execute("""
            INSERT INTO ReservasCNC (id_usuario, id_cnc, tiempo_uso, tipo_trabajo, material)
            VALUES (?, ?, ?, ?, ?)
        """, (id_usuario, id_cnc, tiempo_uso, tipo_trabajo, material))

        cursor.execute("UPDATE MaquinasCNC SET disponible = 0 WHERE id_cnc = ?", (id_cnc,))
        conn.commit()
        cursor.close()
        conn.close()

        flash(f"Se ha reservado con éxito {nombre_cnc}", 'success')
        return redirect(url_for('kite_cnc'))
    except Exception as e:
        return f"Error: {e}", 500


# ---- HERRAMIENTAS ----

@app.route('/kite/herramientas')
def kite_herramientas():
    if 'usuario' not in session:
        return redirect(url_for('login'))
    return render_template('kite_herramientas.html')


@app.route('/api/buscar_herramienta')
def buscar_herramienta():
    """Endpoint JSON para autocompletado de herramientas disponibles."""
    if 'usuario' not in session:
        return jsonify([]), 401
    q = request.args.get('q', '').strip()
    if len(q) < 1:
        return jsonify([])
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT h.id_herramienta, h.nombre, h.codigo, h.cantidad_disponible, c.nombre AS categoria
            FROM Herramientas h
            JOIN CategoriasHerramienta c ON h.id_categoria = c.id_categoria
            WHERE h.cantidad_disponible > 0 AND (h.nombre LIKE ? OR h.codigo LIKE ?)
        """, (f'%{q}%', f'%{q}%'))
        resultados = [{'id': f[0], 'nombre': f[1], 'codigo': f[2],
                       'disponible': f[3], 'categoria': f[4]}
                      for f in cursor.fetchall()]
        cursor.close()
        conn.close()
        return jsonify(resultados)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/prestar_herramienta', methods=['POST'])
def prestar_herramienta():
    if 'usuario' not in session:
        return redirect(url_for('login'))

    # ids_herramientas viene como lista de valores del form
    ids_herramientas = request.form.getlist('herramientas[]')
    confirmacion     = request.form.get('confirmacion_responsabilidad')

    if not ids_herramientas:
        flash('Debes seleccionar al menos una herramienta.', 'danger')
        return redirect(url_for('kite_herramientas'))
    if not confirmacion:
        flash('Debes aceptar la responsabilidad sobre las herramientas.', 'danger')
        return redirect(url_for('kite_herramientas'))

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT id_usuario FROM Usuarios WHERE usuario = ?", (session['usuario'],))
        id_usuario = cursor.fetchone()[0]

        # Crear el registro de préstamo y obtener su ID
        cursor.execute("""
            INSERT INTO PrestamosHerramienta (id_usuario)
            OUTPUT INSERTED.id_prestamo
            VALUES (?)
        """, (id_usuario,))
        id_prestamo = cursor.fetchone()[0]

        nombres = []
        for id_h in ids_herramientas:
            # Insertar detalle
            cursor.execute("""
                INSERT INTO DetallePrestamo (id_prestamo, id_herramienta) VALUES (?, ?)
            """, (id_prestamo, int(id_h)))
            # Descontar una unidad disponible
            cursor.execute("""
                UPDATE Herramientas SET cantidad_disponible = cantidad_disponible - 1
                WHERE id_herramienta = ? AND cantidad_disponible > 0
            """, (int(id_h),))
            # Obtener nombre para el mensaje
            cursor.execute("SELECT nombre FROM Herramientas WHERE id_herramienta = ?", (int(id_h),))
            nombres.append(cursor.fetchone()[0])

        conn.commit()
        cursor.close()
        conn.close()

        nombres_str = ', '.join(nombres)
        flash(f"Se ha prestado con éxito: {nombres_str}", 'success')
        return redirect(url_for('kite_herramientas'))
    except Exception as e:
        return f"Error: {e}", 500


# ============================================================
# COMPUTADORAS - Sistema de Gestión
# ============================================================

def _get_rol_usuario():
    """Devuelve el rol del usuario en sesión ('estudiante' o 'guardian')."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT rol FROM Usuarios WHERE usuario = ?", (session['usuario'],))
        fila = cursor.fetchone()
        cursor.close()
        conn.close()
        return fila[0] if fila else 'estudiante'
    except Exception:
        return 'estudiante'


@app.route('/computadoras')
def computadoras():
    if 'usuario' not in session:
        return redirect(url_for('login'))
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Todas las computadoras con su estado actual
        cursor.execute("""
            SELECT id_computadora, codigo, nombre, tiene_cargador, tiene_mouse, disponible
            FROM Computadoras
        """)
        lista = [{'id': f[0], 'codigo': f[1], 'nombre': f[2],
                  'tiene_cargador': f[3], 'tiene_mouse': f[4], 'disponible': f[5]}
                 for f in cursor.fetchall()]

        cursor.close()
        conn.close()
        rol = _get_rol_usuario()
        return render_template('computadoras.html', computadoras=lista, rol=rol)
    except Exception as e:
        return f"Error al cargar computadoras: {e}", 500


@app.route('/api/buscar_computadora')
def buscar_computadora():
    """Endpoint JSON: busca computadoras disponibles por código o nombre."""
    if 'usuario' not in session:
        return jsonify([]), 401
    q = request.args.get('q', '').strip()
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id_computadora, codigo, nombre, tiene_cargador, tiene_mouse
            FROM Computadoras
            WHERE disponible = 1 AND (codigo LIKE ? OR nombre LIKE ?)
        """, (f'%{q}%', f'%{q}%'))
        resultados = [{'id': f[0], 'codigo': f[1], 'nombre': f[2],
                       'tiene_cargador': bool(f[3]), 'tiene_mouse': bool(f[4])}
                      for f in cursor.fetchall()]
        cursor.close()
        conn.close()
        return jsonify(resultados)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/reservar_computadora', methods=['POST'])
def reservar_computadora():
    if 'usuario' not in session:
        return redirect(url_for('login'))

    id_computadora = request.form['id_computadora']
    razon          = request.form['razon']

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT id_usuario FROM Usuarios WHERE usuario = ?", (session['usuario'],))
        id_usuario = cursor.fetchone()[0]

        # Verificar que la computadora sigue disponible
        cursor.execute("SELECT disponible, codigo FROM Computadoras WHERE id_computadora = ?", (id_computadora,))
        comp = cursor.fetchone()
        if not comp or not comp[0]:
            flash('Esa computadora ya no está disponible. Selecciona otra.', 'danger')
            cursor.close()
            conn.close()
            return redirect(url_for('computadoras'))

        codigo_comp = comp[1]

        # Insertar reserva (estado = 'Pendiente', espera confirmación del guardian)
        cursor.execute("""
            INSERT INTO ReservasComputadora (id_usuario, id_computadora, razon)
            VALUES (?, ?, ?)
        """, (id_usuario, id_computadora, razon))

        # Marcar computadora como no disponible
        cursor.execute("UPDATE Computadoras SET disponible = 0 WHERE id_computadora = ?", (id_computadora,))
        conn.commit()
        cursor.close()
        conn.close()

        flash(f"Se ha reservado con éxito la Computadora {codigo_comp}. Espera la confirmación del guardian.", 'success')
        return redirect(url_for('computadoras'))
    except Exception as e:
        return f"Error: {e}", 500


# ---- GUARDIAN: Confirmación de reserva ----

@app.route('/computadoras/confirmacion')
def comp_confirmacion():
    if 'usuario' not in session:
        return redirect(url_for('login'))
    if _get_rol_usuario() != 'guardian':
        flash('Acceso restringido a guardianes.', 'danger')
        return redirect(url_for('computadoras'))
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # Traer reservas en estado Pendiente con datos del usuario y computadora
        cursor.execute("""
            SELECT rc.id_reserva, c.codigo, c.nombre AS comp_nombre,
                   u.usuario, u.carnet_us, u.cohorte_sel,
                   rc.razon, rc.hora_inicio, c.tiene_cargador, c.tiene_mouse
            FROM ReservasComputadora rc
            JOIN Computadoras c ON rc.id_computadora = c.id_computadora
            JOIN Usuarios u ON rc.id_usuario = u.id_usuario
            WHERE rc.estado = 'Pendiente'
            ORDER BY rc.hora_inicio
        """)
        reservas = []
        for f in cursor.fetchall():
            reservas.append({
                'id_reserva': f[0], 'codigo': f[1], 'comp_nombre': f[2],
                'usuario': f[3], 'carnet': f[4], 'cohorte': f[5],
                'razon': f[6], 'hora_inicio': f[7],
                'tiene_cargador': bool(f[8]), 'tiene_mouse': bool(f[9])
            })
        cursor.close()
        conn.close()
        return render_template('comp_confirmacion.html', reservas=reservas)
    except Exception as e:
        return f"Error: {e}", 500


@app.route('/computadoras/confirmar_reserva', methods=['POST'])
def confirmar_reserva_computadora():
    if 'usuario' not in session or _get_rol_usuario() != 'guardian':
        return redirect(url_for('login'))
    id_reserva = request.form['id_reserva']
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE ReservasComputadora SET estado = 'Confirmada' WHERE id_reserva = ?
        """, (id_reserva,))
        conn.commit()
        cursor.close()
        conn.close()
        flash('Reserva confirmada exitosamente.', 'success')
        return redirect(url_for('comp_confirmacion'))
    except Exception as e:
        return f"Error: {e}", 500


# ---- GUARDIAN: Reintegración de computadora ----

@app.route('/computadoras/reintegracion')
def comp_reintegracion():
    if 'usuario' not in session:
        return redirect(url_for('login'))
    if _get_rol_usuario() != 'guardian':
        flash('Acceso restringido a guardianes.', 'danger')
        return redirect(url_for('computadoras'))
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # Traer reservas en estado Confirmada con tiempo transcurrido
        cursor.execute("""
            SELECT rc.id_reserva, c.codigo, c.nombre AS comp_nombre,
                   u.usuario, u.carnet_us, u.cohorte_sel,
                   rc.razon, rc.hora_inicio, c.tiene_cargador, c.tiene_mouse
            FROM ReservasComputadora rc
            JOIN Computadoras c ON rc.id_computadora = c.id_computadora
            JOIN Usuarios u ON rc.id_usuario = u.id_usuario
            WHERE rc.estado = 'Confirmada'
            ORDER BY rc.hora_inicio
        """)
        reservas = []
        for f in cursor.fetchall():
            hora_inicio = f[7]
            # Calcular tiempo transcurrido desde que fue confirmada
            if hora_inicio:
                delta = datetime.now() - hora_inicio
                horas, rem = divmod(int(delta.total_seconds()), 3600)
                minutos = rem // 60
                tiempo_str = f"{horas}h {minutos}min"
            else:
                tiempo_str = "Desconocido"
            reservas.append({
                'id_reserva': f[0], 'codigo': f[1], 'comp_nombre': f[2],
                'usuario': f[3], 'carnet': f[4], 'cohorte': f[5],
                'razon': f[6], 'hora_inicio': hora_inicio,
                'tiempo_prestado': tiempo_str,
                'tiene_cargador': bool(f[8]), 'tiene_mouse': bool(f[9])
            })
        cursor.close()
        conn.close()
        return render_template('comp_reintegracion.html', reservas=reservas)
    except Exception as e:
        return f"Error: {e}", 500


@app.route('/computadoras/confirmar_devolucion', methods=['POST'])
def confirmar_devolucion_computadora():
    if 'usuario' not in session or _get_rol_usuario() != 'guardian':
        return redirect(url_for('login'))

    id_reserva        = request.form['id_reserva']
    en_buen_estado    = 1 if request.form.get('en_buen_estado') else 0
    cargador_devuelto = 1 if request.form.get('cargador_devuelto') else 0
    mouse_devuelto    = 1 if request.form.get('mouse_devuelto') else 0

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Obtener id_computadora desde la BD (no desde el form)
        cursor.execute("SELECT id_computadora FROM ReservasComputadora WHERE id_reserva = ?", (id_reserva,))
        fila = cursor.fetchone()
        if not fila:
            return "Reserva no encontrada.", 404
        id_computadora = fila[0]

        # Actualizar reserva: marcar como devuelta con los checks
        cursor.execute("""
            UPDATE ReservasComputadora
            SET estado = 'Devuelta', hora_fin = GETDATE(),
                en_buen_estado = ?, cargador_devuelto = ?, mouse_devuelto = ?
            WHERE id_reserva = ?
        """, (en_buen_estado, cargador_devuelto, mouse_devuelto, id_reserva))

        # Liberar computadora
        cursor.execute("UPDATE Computadoras SET disponible = 1 WHERE id_computadora = ?", (id_computadora,))
        conn.commit()
        cursor.close()
        conn.close()

        flash('Devolución registrada correctamente. Computadora disponible nuevamente.', 'success')
        return redirect(url_for('comp_reintegracion'))
    except Exception as e:
        return f"Error: {e}", 500


if __name__ == '__main__':
    app.run(debug=True)