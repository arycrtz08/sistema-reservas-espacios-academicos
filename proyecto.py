from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
import pyodbc
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
from functools import wraps

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'Passwort')

# ─── Conexión BD ────────────────────────────────────────────────────────────
def get_db_connection():
    conn_str = (
        f"DRIVER={{{os.getenv('DB_DRIVER')}}};"
        f"SERVER={os.getenv('DB_SERVER')};"
        f"DATABASE={os.getenv('DB_NAME')};"
        "Trusted_Connection=yes;TrustServerCertificate=yes;"
    )
    return pyodbc.connect(conn_str)

# ─── Decoradores ────────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'usuario' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(*tipos):
    """Si tipos está vacío, acepta cualquier admin. Si se especifican, solo esos tipos (y gral siempre)."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if 'admin' not in session:
                flash('Acceso restringido a administradores.', 'danger')
                return redirect(url_for('login_admin'))
            t = session.get('admin_tipo', '')
            if tipos and t not in tipos and t != 'gral':
                flash('No tienes permisos para esta sección.', 'danger')
                return redirect(url_for('admin_dashboard'))
            return f(*args, **kwargs)
        return decorated
    return decorator

# ─── Helpers de lógica ──────────────────────────────────────────────────────
def get_limite_pla(id_usuario, cohorte):
    """Límite de PLA: persona > cohorte > global 750g."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT limite_gramos FROM LimiteFilamento WHERE tipo='persona' AND id_usuario=?",
            (id_usuario,))
        row = cursor.fetchone()
        if row:
            cursor.close(); conn.close(); return row[0]
        cursor.execute(
            "SELECT limite_gramos FROM LimiteFilamento WHERE tipo='cohorte' AND cohorte=?",
            (cohorte,))
        row = cursor.fetchone()
        cursor.close(); conn.close()
        return row[0] if row else 750
    except Exception:
        return 750

def check_bloqueo_kite(id_usuario, cohorte):
    """Retorna mensaje de bloqueo del KITE, o None si sin bloqueo."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT TOP 1 mensaje FROM BloqueoKite
            WHERE activo=1 AND (
                (tipo='persona' AND id_usuario=?) OR
                (tipo='cohorte' AND cohorte=?)
            )
        """, (id_usuario, cohorte))
        row = cursor.fetchone()
        cursor.close(); conn.close()
        return row[0] if row else None
    except Exception:
        return None

def get_session_usuario():
    """Devuelve id_usuario, carnet y cohorte del usuario en sesión."""
    return (session.get('id_usuario'), session.get('carnet', ''), session.get('cohorte', ''))

# ─── Evitar cache del navegador ─────────────────────────────────────────────
@app.after_request
def add_no_cache_headers(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


# ─── Home / Logout ───────────────────────────────────────────────────────────
@app.route('/')
def home():

    # SI ES ADMIN → ADMIN
    if 'admin' in session:
        return redirect(url_for('admin_dashboard'))

    # SI NO HAY USUARIO → LOGIN
    if 'usuario' not in session:
        return redirect(url_for('login'))

    return render_template(
        'home.html',
        usuario=session['usuario']
    )


@app.route('/logout')
def logout():

    # BORRAR TODA LA SESIÓN
    session.clear()

    return redirect(url_for('login'))


# ─── Login Estudiante ────────────────────────────────────────────────────────
@app.route('/login', methods=['GET', 'POST'])
def login():

    if request.method == 'POST':

        # LIMPIAR SESIÓN COMPLETA
        session.clear()

        user    = request.form.get('usuario', '').strip()
        carnet  = request.form.get('carnet_us', '').strip()
        cohorte = request.form.get('cohorte', '').strip()

        # Validar formato carnet
        import re

        if not re.match(r'^KEY_000\d{3}$', carnet):
            return render_template(
                'login.html',
                error='El carnet debe tener el formato KEY_000### (ej: KEY_000123).',
                usuario=user, carnet_us=carnet, cohorte=cohorte
            )

        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT id_usuario, usuario, cohorte_sel
                FROM Usuarios
                WHERE carnet_us=?
                """,
                (carnet,)
            )

            existing = cursor.fetchone()

            # ─── Usuario ya existe ─────────────────────────────
            if existing:

                # Verificar que el nombre coincida
                if existing[1].strip().lower() != user.strip().lower():

                    cursor.close()
                    conn.close()

                    return render_template(
                        'login.html',
                        error='El carnet ya está registrado con otro nombre.',
                        usuario=user, carnet_us=carnet, cohorte=cohorte
                    )

                id_usuario = existing[0]
                user       = existing[1]
                cohorte    = existing[2]

            # ─── Usuario nuevo ─────────────────────────────────
            else:

                cursor.execute(
                    """
                    INSERT INTO Usuarios
                    (usuario, carnet_us, cohorte_sel)

                    OUTPUT INSERTED.id_usuario

                    VALUES (?, ?, ?)
                    """,
                    (user, carnet, cohorte)
                )

                id_usuario = cursor.fetchone()[0]

                conn.commit()

            # ─── Guardar log de ingreso ────────────────────────
            cursor.execute(
                """
                INSERT INTO LogsIngreso (carnet_us)
                VALUES (?)
                """,
                (carnet,)
            )

            conn.commit()

            cursor.close()
            conn.close()

            # ─── Crear nueva sesión ────────────────────────────
            session['usuario']    = user
            session['carnet']     = carnet
            session['cohorte']    = cohorte
            session['id_usuario'] = id_usuario

            return redirect(url_for('home'))

        except Exception as e:

            return render_template(
                'login.html',
                error=f"Error al iniciar sesión: {e}",
                usuario=user, carnet_us=carnet, cohorte=cohorte
            )

    return render_template('login.html')

# ─── Login Administrador ─────────────────────────────────────────────────────
@app.route('/login_admin', methods=['GET', 'POST'])
def login_admin():

    if request.method == 'POST':
        session.clear()

        usuario    = request.form.get('usuario', '').strip()
        contrasena = request.form.get('contrasena', '').strip()

        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            cursor.execute(
                "SELECT tipo, contrasena FROM Administradores WHERE usuario=?",
                (usuario,)
            )

            row = cursor.fetchone()

            cursor.close()
            conn.close()

            if row and row[1] == contrasena:
                session['admin']      = usuario
                session['admin_tipo'] = row[0]

                tipo = session.get('admin_tipo', '')

                if tipo == 'kite':
                    return redirect(url_for('admin_kite'))
                if tipo == 'compu':
                    return redirect(url_for('admin_compu'))
                if tipo == 'salas':
                    return redirect(url_for('admin_salas'))

                return redirect(url_for('admin_gral'))

            return render_template('admin_login.html', error='Usuario o contraseña incorrectos.')

        except Exception as e:
            return render_template('admin_login.html', error=f"Error: {e}")

    return render_template('admin_login.html')


@app.route('/admin')
def admin_dashboard():

    if 'admin' not in session:
        return redirect(url_for('login_admin'))

    tipo = session.get('admin_tipo', '')

    if tipo == 'kite':
        return redirect(url_for('admin_kite'))
    if tipo == 'compu':
        return redirect(url_for('admin_compu'))
    if tipo == 'salas':
        return redirect(url_for('admin_salas'))

    return redirect(url_for('admin_gral'))

# ─── Perfil ──────────────────────────────────────────────────────────────────
@app.route('/perfil')
@login_required
def perfil():
    return render_template('perfil.html',
        usuario=session['usuario'],
        carnet=session.get('carnet', ''),
        cohorte=session.get('cohorte', ''))

# ─── Mis Reservas ─────────────────────────────────────────────────────────────
@app.route('/mis_reservas')
@login_required
def mis_reservas():
    id_usuario = session['id_usuario']
    tipo       = request.args.get('tipo', 'todas')
    periodo    = request.args.get('periodo', '')
    fecha_esp  = request.args.get('fecha', '')

    def filtro(campo):
        if periodo == 'hoy':
            return f"AND CAST({campo} AS DATE) = CAST(GETDATE() AS DATE)"
        if periodo == 'semana':
            return f"AND {campo} >= DATEADD(day,-7,GETDATE())"
        if periodo == 'mes':
            return f"AND {campo} >= DATEADD(month,-1,GETDATE())"
        if periodo == 'especifica' and fecha_esp:
            return f"AND CAST({campo} AS DATE) = '{fecha_esp}'"
        return ''

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        salas_r = imp_r = herr_r = comp_r = []

        if tipo in ('todas', 'salas'):
            cursor.execute(f"""
                SELECT rs.id_reserva, s.nombre, rs.fecha, rs.hora_inicio, rs.hora_fin, rs.estado
                FROM ReservasSalas rs JOIN Salas s ON rs.id_sala=s.id_sala
                WHERE rs.id_usuario=? {filtro('rs.fecha')}
                ORDER BY rs.fecha DESC, rs.hora_inicio DESC
            """, (id_usuario,))
            salas_r = [{'id':r[0],'sala':r[1],'fecha':r[2],'inicio':str(r[3]),'fin':str(r[4]),'estado':r[5]}
                       for r in cursor.fetchall()]

        if tipo in ('todas', 'kite', 'impresoras'):
            cursor.execute(f"""
                SELECT ri.id_reserva, i.nombre, ri.fecha, ri.filamento, ri.gramos, ri.estado
                FROM ReservasImpresora3D ri JOIN Impresoras3D i ON ri.id_impresora=i.id_impresora
                WHERE ri.id_usuario=? {filtro('ri.fecha')}
                ORDER BY ri.fecha DESC
            """, (id_usuario,))
            imp_r = [{'id':r[0],'impresora':r[1],'fecha':r[2],'filamento':r[3],'gramos':r[4],'estado':r[5]}
                     for r in cursor.fetchall()]



        if tipo in ('todas', 'kite', 'herramientas'):
            cursor.execute(f"""
                SELECT ph.id_prestamo, ph.fecha_prestamo, ph.estado,
                       STUFF((SELECT ', ' + h2.nombre
                              FROM DetallePrestamo dp2 JOIN Herramientas h2 ON dp2.id_herramienta=h2.id_herramienta
                              WHERE dp2.id_prestamo=ph.id_prestamo FOR XML PATH('')), 1,2,'') AS herrs
                FROM PrestamosHerramienta ph
                WHERE ph.id_usuario=? {filtro('ph.fecha_prestamo')}
                ORDER BY ph.fecha_prestamo DESC
            """, (id_usuario,))
            herr_r = [{'id':r[0],'fecha':r[1],'estado':r[2],'herramientas':r[3] or ''}
                      for r in cursor.fetchall()]

        if tipo in ('todas', 'computadoras'):
            cursor.execute(f"""
                SELECT rc.id_reserva, c.codigo, c.nombre, rc.razon, rc.hora_inicio, rc.estado
                FROM ReservasComputadora rc JOIN Computadoras c ON rc.id_computadora=c.id_computadora
                WHERE rc.id_usuario=? {filtro('rc.hora_inicio')}
                ORDER BY rc.hora_inicio DESC
            """, (id_usuario,))
            comp_r = [{'id':r[0],'codigo':r[1],'nombre':r[2],'razon':r[3],'inicio':r[4],'estado':r[5]}
                      for r in cursor.fetchall()]

        cursor.close(); conn.close()
        return render_template('mis_reservas.html',
            salas=salas_r, impresoras=imp_r,
            herramientas=herr_r, computadoras=comp_r,
            tipo=tipo, periodo=periodo, fecha_esp=fecha_esp)
    except Exception as e:
        return f"Error: {e}", 500

# ─── API: buscar usuario por carnet (autocompletado acompañantes) ─────────────
@app.route('/api/buscar_usuario_por_carnet')
@login_required
def api_buscar_usuario_por_carnet():
    carnet = request.args.get('carnet', '').strip()
    if not carnet:
        return jsonify({})
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT usuario, cohorte_sel FROM Usuarios WHERE carnet_us=?", (carnet,))
        row = cursor.fetchone()
        cursor.close(); conn.close()
        return jsonify({'nombre': row[0], 'cohorte': row[1]}) if row else jsonify({})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ─── Salas ───────────────────────────────────────────────────────────────────
@app.route('/salas')
@login_required
def lista_salas():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id_sala, nombre, capacidad_max, disponible FROM Salas WHERE disponible=1")
        salas = [{'id_sala':r[0],'nombre':r[1],'capacidad_max':r[2],'disponible':r[3]}
                 for r in cursor.fetchall()]
        cursor.close(); conn.close()
        return render_template('salas.html', salas=salas)
    except Exception as e:
        return f"Error: {e}", 500

@app.route('/reservar_sala', methods=['POST'])
@login_required
def reservar_sala():
    id_sala           = request.form['id_sala']
    hora_inicio_str   = request.form['hora_inicio']
    hora_fin_str      = request.form['hora_fin']
    cantidad_personas = int(request.form['cantidad_personas'])

    h_inicio = datetime.strptime(hora_inicio_str, '%H:%M').time()
    h_fin    = datetime.strptime(hora_fin_str, '%H:%M').time()
    lim_inf  = datetime.strptime('06:00', '%H:%M').time()
    lim_sup  = datetime.strptime('18:00', '%H:%M').time()

    if h_inicio < lim_inf or h_fin > lim_sup:
        flash('El horario permitido es de 6:00 AM a 6:00 PM.', 'danger')
        return redirect(url_for('lista_salas'))
    dt_i = datetime.combine(datetime.today(), h_inicio)
    dt_f = datetime.combine(datetime.today(), h_fin)
    dur  = dt_f - dt_i
    if dur.total_seconds() > 7200:
        flash('La reserva no puede exceder las 2 horas.', 'danger')
        return redirect(url_for('lista_salas'))
    if dur.total_seconds() <= 0:
        flash('La hora de fin debe ser posterior a la de inicio.', 'danger')
        return redirect(url_for('lista_salas'))
    if cantidad_personas < 2 or cantidad_personas > 6:
        flash('La capacidad debe ser de 2 a 6 personas.', 'danger')
        return redirect(url_for('lista_salas'))

    # Recopilar acompañantes (cantidad_personas - 1 campos)
    acompanantes = []
    for i in range(cantidad_personas - 1):
        nombre  = request.form.get(f'acomp_nombre_{i}', '').strip()
        carnet  = request.form.get(f'acomp_carnet_{i}', '').strip()
        cohorte = request.form.get(f'acomp_cohorte_{i}', '').strip()
        if nombre and carnet:
            acompanantes.append((nombre, carnet, cohorte))

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO ReservasSalas
                (id_usuario, id_sala, fecha, hora_inicio, hora_fin, cantidad_personas, estado)
            OUTPUT INSERTED.id_reserva
            VALUES (?, ?, CAST(GETDATE() AS DATE), ?, ?, ?, 'Activa')
        """, (session['id_usuario'], id_sala, hora_inicio_str, hora_fin_str, cantidad_personas))
        id_reserva = cursor.fetchone()[0]
        for (nombre, carnet, cohorte) in acompanantes:
            cursor.execute("""
                INSERT INTO AcompañantesReserva (id_reserva, nombre_completo, carnet, cohorte)
                VALUES (?, ?, ?, ?)
            """, (id_reserva, nombre, carnet, cohorte))
        cursor.execute("UPDATE Salas SET disponible=0 WHERE id_sala=?", (id_sala,))
        conn.commit()
        cursor.close(); conn.close()
        flash('Sala reservada exitosamente.', 'success')
        return redirect(url_for('lista_salas'))
    except Exception as e:
        return f"Error en BD: {e}", 500

# ─── KITE: Impresoras 3D ───────────────────────────────────────────────────────
@app.route('/kite')
@login_required
def kite():
    return render_template('kite.html')

@app.route('/kite/impresoras')
@login_required
def kite_impresoras():
    id_usuario = session['id_usuario']
    cohorte    = session.get('cohorte', '')
    # Verificar si está bloqueado
    msg_bloqueo = check_bloqueo_kite(id_usuario, cohorte)
    if msg_bloqueo:
        return render_template('kite_bloqueado.html', mensaje=msg_bloqueo)

    limite_pla = get_limite_pla(id_usuario, cohorte)

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id_impresora, nombre, codigo FROM Impresoras3D WHERE disponible=1")
        impresoras = [{'id':r[0],'nombre':r[1],'codigo':r[2]} for r in cursor.fetchall()]

        # Gramos usados en el ciclo activo por tipo de filamento
        cursor.execute("""
            SELECT filamento, ISNULL(SUM(gramos),0)
            FROM ReservasImpresora3D ri
            JOIN CiclosAcademicos ca ON ri.fecha BETWEEN ca.fecha_inicio AND DATEADD(day,1,ca.fecha_fin)
            WHERE ri.id_usuario=? AND ca.activo=1 AND ri.estado='Activa'
            GROUP BY filamento
        """, (id_usuario,))
        usos = cursor.fetchall()
        cursor.close(); conn.close()

        usos_dict = {row[0]: row[1] for row in usos}
        gramos_pla  = usos_dict.get('PLA', 0)
        gramos_tpu  = usos_dict.get('TPU', 0)
        gramos_petg = usos_dict.get('PETG', 0)
        gramos_otro = usos_dict.get('Otro', 0)

        return render_template('kite_impresoras.html',
            impresoras=impresoras,
            gramos_pla=gramos_pla,
            gramos_tpu=gramos_tpu,
            gramos_petg=gramos_petg,
            gramos_otro=gramos_otro,
            limite_pla=limite_pla
        )
    except Exception as e:
        return f"Error: {e}", 500

@app.route('/reservar_impresora', methods=['POST'])
@login_required
def reservar_impresora():
    id_usuario   = session['id_usuario']
    cohorte      = session.get('cohorte', '')
    id_impresora = request.form['id_impresora']
    horas        = int(request.form.get('horas', 0))
    minutos      = int(request.form.get('minutos', 0))
    tipo_trabajo = request.form['tipo_trabajo']
    filamento    = request.form['filamento']
    filamento_o  = request.form.get('filamento_otro', '') if filamento == 'Otro' else None
    gramos       = int(request.form['gramos'])

    tiempo_total_minutos = (horas * 60) + minutos
    if tiempo_total_minutos <= 0:
        flash('El tiempo de uso debe ser mayor a 0.', 'danger')
        return redirect(url_for('kite_impresoras'))

    if filamento == 'PLA':
        limite_pla = get_limite_pla(id_usuario, cohorte)
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT ISNULL(SUM(gramos),0) FROM ReservasImpresora3D ri
                JOIN CiclosAcademicos ca ON ri.fecha BETWEEN ca.fecha_inicio AND DATEADD(day,1,ca.fecha_fin)
                WHERE ri.id_usuario=? AND ca.activo=1 AND ri.filamento='PLA' AND ri.estado='Activa'
            """, (id_usuario,))
            gramos_usados = cursor.fetchone()[0]
            cursor.close(); conn.close()
            if (gramos_usados + gramos) > limite_pla:
                flash(f"No puedes reservar {gramos}g. Llevas {gramos_usados}g usados este ciclo (límite PLA: {limite_pla}g).", "danger")
                return redirect(url_for('kite_impresoras'))
        except Exception as e:
            return f"Error: {e}", 500

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO ReservasImpresora3D
            (id_usuario, id_impresora, tiempo_minutos, hora_fin, tipo_trabajo, filamento, filamento_otro, gramos, estado)
            VALUES (?, ?, ?, DATEADD(minute, ?, GETDATE()), ?, ?, ?, ?, 'Activa')
        """, (id_usuario, id_impresora, tiempo_total_minutos, tiempo_total_minutos, tipo_trabajo, filamento, filamento_o, gramos))
        cursor.execute("UPDATE Impresoras3D SET disponible=0 WHERE id_impresora=?", (id_impresora,))
        conn.commit()
        cursor.close(); conn.close()
        flash("Impresora reservada con éxito.", "success")
        return redirect(url_for('kite_impresoras'))
    except Exception as e:
        return f"Error: {e}", 500


# ─── KITE: Herramientas ──────────────────────────────────────────────────────
@app.route('/kite/herramientas')
@login_required
def kite_herramientas():
    id_usuario = session['id_usuario']
    mensaje_bloqueo = check_bloqueo_kite(id_usuario, session.get('cohorte', ''))
    if mensaje_bloqueo:
        return render_template('kite_bloqueado.html', mensaje=mensaje_bloqueo)

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*)
            FROM DetallePrestamo dp
            JOIN PrestamosHerramienta ph ON ph.id_prestamo = dp.id_prestamo
            WHERE ph.id_usuario=? AND ph.estado='Prestado' AND dp.estado='Prestada'
        """, (id_usuario,))
        hay_herramientas_activas = cursor.fetchone()[0] > 0
        cursor.close(); conn.close()
        return render_template(
            'kite_herramientas.html',
            hay_herramientas_activas=hay_herramientas_activas
        )
    except Exception as e:
        return f"Error: {e}", 500


@app.route('/api/buscar_herramienta')
@login_required
def api_buscar_herramienta():
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify([])
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT h.id_herramienta, h.nombre, h.codigo, h.cantidad_disponible, c.nombre
            FROM Herramientas h
            JOIN CategoriasHerramienta c ON h.id_categoria=c.id_categoria
            WHERE h.cantidad_disponible > 0
              AND h.activa=1
              AND (h.nombre LIKE ? OR h.codigo LIKE ?)
        """, (f'%{q}%', f'%{q}%'))
        herramientas = [
            {'id': r[0], 'nombre': r[1], 'codigo': r[2], 'disponible': r[3], 'categoria': r[4]}
            for r in cursor.fetchall()
        ]
        for herramienta in herramientas:
            cursor.execute("SELECT equipo FROM EPPHerramienta WHERE id_herramienta=?", (herramienta['id'],))
            herramienta['epp'] = [row[0] for row in cursor.fetchall()]
        cursor.close(); conn.close()
        return jsonify(herramientas)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/prestar_herramienta', methods=['POST'])
@login_required
def prestar_herramienta():
    id_usuario = session['id_usuario']
    ids_h = list(dict.fromkeys(request.form.getlist('herramientas[]')))
    if not ids_h:
        flash('Debes seleccionar al menos una herramienta.', 'danger')
        return redirect(url_for('kite_herramientas'))
    if not request.form.get('confirmacion_responsabilidad'):
        flash('Debes aceptar la responsabilidad del préstamo.', 'danger')
        return redirect(url_for('kite_herramientas'))

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO PrestamosHerramienta (id_usuario, estado) OUTPUT INSERTED.id_prestamo VALUES (?,'Prestado')",
            (id_usuario,)
        )
        id_prestamo = cursor.fetchone()[0]
        for id_herramienta in ids_h:
            cursor.execute("""
                UPDATE Herramientas
                SET cantidad_disponible = cantidad_disponible - 1
                WHERE id_herramienta=? AND activa=1 AND cantidad_disponible > 0
            """, (id_herramienta,))
            if cursor.rowcount != 1:
                conn.rollback()
                cursor.close(); conn.close()
                flash('Una herramienta ya no está disponible. Intenta de nuevo.', 'danger')
                return redirect(url_for('kite_herramientas'))
            cursor.execute("""
                INSERT INTO DetallePrestamo (id_prestamo, id_herramienta, estado)
                VALUES (?, ?, 'Prestada')
            """, (id_prestamo, id_herramienta))
        conn.commit()
        cursor.close(); conn.close()
        flash('Herramientas prestadas con éxito.', 'success')
        return redirect(url_for('kite_herramientas'))
    except Exception as e:
        return f"Error: {e}", 500


@app.route('/kite/herramientas/devolver', methods=['GET', 'POST'])
@login_required
def devolver_herramientas():
    id_usuario = session['id_usuario']
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        if request.method == 'POST':
            seleccionadas = [int(v) for v in request.form.getlist('devolver[]') if v.isdigit()]
            if not seleccionadas:
                cursor.close(); conn.close()
                flash('Selecciona al menos una herramienta para devolver.', 'warning')
                return redirect(url_for('devolver_herramientas'))
            danadas = {int(v) for v in request.form.getlist('herramientas_danadas[]') if v.isdigit()}
            prestamos_afectados = set()
            devueltas = 0
            for id_detalle in seleccionadas:
                cursor.execute("""
                    SELECT dp.id_prestamo, dp.id_herramienta
                    FROM DetallePrestamo dp
                    JOIN PrestamosHerramienta ph ON ph.id_prestamo=dp.id_prestamo
                    WHERE dp.id_detalle=? AND ph.id_usuario=?
                      AND ph.estado='Prestado' AND dp.estado='Prestada'
                """, (id_detalle, id_usuario))
                detalle = cursor.fetchone()
                if not detalle:
                    continue
                id_prestamo, id_herramienta = detalle[0], detalle[1]
                prestamos_afectados.add(id_prestamo)
                if id_detalle in danadas:
                    nota = request.form.get(f'nota_dano_{id_detalle}', '').strip()
                    cursor.execute("""
                        UPDATE DetallePrestamo
                        SET estado='Devuelta', fecha_devolucion=GETDATE(), danada=1, nota_dano=?
                        WHERE id_detalle=? AND estado='Prestada'
                    """, (nota, id_detalle))
                else:
                    cursor.execute("""
                        UPDATE DetallePrestamo
                        SET estado='Devuelta', fecha_devolucion=GETDATE(), danada=0
                        WHERE id_detalle=? AND estado='Prestada'
                    """, (id_detalle,))
                    cursor.execute("UPDATE Herramientas SET cantidad_disponible = cantidad_disponible + 1 WHERE id_herramienta=?", (id_herramienta,))
                devueltas += 1
            for id_prestamo in prestamos_afectados:
                cursor.execute("""
                    UPDATE PrestamosHerramienta
                    SET estado='Devuelto', fecha_devolucion=GETDATE()
                    WHERE id_prestamo=? AND NOT EXISTS (
                        SELECT 1 FROM DetallePrestamo WHERE id_prestamo=? AND estado='Prestada'
                    )
                """, (id_prestamo, id_prestamo))
            conn.commit()
            cursor.close(); conn.close()
            flash('Devolución registrada exitosamente.' if devueltas else 'No se encontraron herramientas pendientes.', 'success' if devueltas else 'warning')
            return redirect(url_for('kite_herramientas'))

        cursor.execute("""
            SELECT dp.id_detalle, ph.id_prestamo, h.nombre, h.codigo, ph.fecha_prestamo
            FROM DetallePrestamo dp
            JOIN PrestamosHerramienta ph ON ph.id_prestamo=dp.id_prestamo
            JOIN Herramientas h ON h.id_herramienta=dp.id_herramienta
            WHERE ph.id_usuario=? AND ph.estado='Prestado' AND dp.estado='Prestada'
            ORDER BY ph.fecha_prestamo DESC, dp.id_detalle DESC
        """, (id_usuario,))
        herramientas = [
            {'detalle_id': r[0], 'prestamo_id': r[1], 'nombre': r[2], 'codigo': r[3], 'fecha': r[4]}
            for r in cursor.fetchall()
        ]
        cursor.close(); conn.close()
        return render_template('kite_herramientas_devolver.html', herramientas=herramientas)
    except Exception as e:
        return f"Error: {e}", 500


@app.route('/kite/herramientas/devolver/<int:id_prestamo>', methods=['GET', 'POST'])
@login_required
def devolver_herramienta(id_prestamo):
    return redirect(url_for('devolver_herramientas'))


# ─── Computadoras ────────────────────────────────────────────────────────────
@app.route('/computadoras')
@login_required
def computadoras():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id_computadora, codigo, nombre, tiene_cargador, tiene_mouse, disponible FROM Computadoras")
        lista = [{'id':r[0],'codigo':r[1],'nombre':r[2],'tiene_cargador':r[3],'tiene_mouse':r[4],'disponible':r[5]} for r in cursor.fetchall()]
        cursor.close(); conn.close()
        return render_template('computadoras.html', computadoras=lista)
    except Exception as e:
        return f"Error: {e}", 500

@app.route('/api/buscar_computadora')
@login_required
def buscar_computadora():
    q = request.args.get('q', '').strip()
    if not q: return jsonify([])
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id_computadora, codigo, nombre, tiene_cargador, tiene_mouse FROM Computadoras WHERE disponible=1 AND (codigo LIKE ? OR nombre LIKE ?)", (f'%{q}%', f'%{q}%'))
        res = [{'id':r[0],'codigo':r[1],'nombre':r[2],'tiene_cargador':r[3],'tiene_mouse':r[4]} for r in cursor.fetchall()]
        cursor.close(); conn.close()
        return jsonify(res)
    except Exception:
        return jsonify([])

@app.route('/reservar_computadora', methods=['POST'])
@login_required
def reservar_computadora():
    id_u = session['id_usuario']
    id_c = request.form['id_computadora']
    razon = request.form['razon']
    razon_o = request.form.get('razon_otro', '') if razon == 'Otro' else None

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT disponible, codigo FROM Computadoras WHERE id_computadora=?", (id_c,))
        comp = cursor.fetchone()
        if not comp or not comp[0]:
            flash('Esa computadora ya no está disponible.', 'danger')
            cursor.close(); conn.close()
            return redirect(url_for('computadoras'))

        cursor.execute("""
            INSERT INTO ReservasComputadora (id_usuario, id_computadora, razon, razon_otro, estado)
            VALUES (?, ?, ?, ?, 'Pendiente')
        """, (id_u, id_c, razon, razon_o))
        cursor.execute("UPDATE Computadoras SET disponible=0 WHERE id_computadora=?", (id_c,))
        conn.commit()
        cursor.close(); conn.close()
        flash(f'Reservada computadora {comp[1]}. Espera confirmación del administrador.', 'success')
        return redirect(url_for('computadoras'))
    except Exception as e:
        return f"Error: {e}", 500

# ─── Paneles de Administración ───────────────────────────────────────────────
@app.route('/admin/kite')
@admin_required('kite')
def admin_kite():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # Traer límites y bloqueos
        cursor.execute("""
            SELECT l.id_limite, l.tipo, ISNULL(u.usuario, ''), ISNULL(l.cohorte, ''), l.limite_gramos
            FROM LimiteFilamento l LEFT JOIN Usuarios u ON l.id_usuario = u.id_usuario
        """)
        limites = [{'id':r[0],'tipo':r[1],'usuario':r[2],'cohorte':r[3],'limite':r[4]} for r in cursor.fetchall()]

        cursor.execute("""
            SELECT b.id_bloqueo, b.tipo, ISNULL(u.usuario, ''), ISNULL(b.cohorte, ''), b.mensaje
            FROM BloqueoKite b LEFT JOIN Usuarios u ON b.id_usuario = u.id_usuario WHERE b.activo=1
        """)
        bloqueos = [{'id':r[0],'tipo':r[1],'usuario':r[2],'cohorte':r[3],'mensaje':r[4]} for r in cursor.fetchall()]

        cursor.close(); conn.close()
        return render_template('admin_kite.html', limites=limites, bloqueos=bloqueos)
    except Exception as e:
        return f"Error: {e}", 500

@app.route('/admin/compu')
@admin_required('compu')
def admin_compu():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT rc.id_reserva, c.codigo, u.usuario, u.carnet_us, rc.razon, rc.razon_otro, rc.hora_inicio
            FROM ReservasComputadora rc JOIN Computadoras c ON rc.id_computadora=c.id_computadora
            JOIN Usuarios u ON rc.id_usuario=u.id_usuario WHERE rc.estado='Pendiente'
        """)
        pendientes = [{'id':r[0],'codigo':r[1],'usuario':r[2],'carnet':r[3],'razon':r[4],'razon_otro':r[5],'inicio':r[6]} for r in cursor.fetchall()]

        cursor.execute("""
            SELECT rc.id_reserva, c.codigo, u.usuario, u.carnet_us, rc.razon, rc.hora_inicio
            FROM ReservasComputadora rc JOIN Computadoras c ON rc.id_computadora=c.id_computadora
            JOIN Usuarios u ON rc.id_usuario=u.id_usuario WHERE rc.estado='Confirmada'
        """)
        confirmadas = [{'id':r[0],'codigo':r[1],'usuario':r[2],'carnet':r[3],'razon':r[4],'inicio':r[5]} for r in cursor.fetchall()]

        cursor.close(); conn.close()
        return render_template('admin_compu.html', pendientes=pendientes, confirmadas=confirmadas)
    except Exception as e:
        return f"Error: {e}", 500

@app.route('/admin/compu/confirmar/<int:id_reserva>', methods=['POST'])
@admin_required('compu')
def admin_compu_confirmar(id_reserva):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE ReservasComputadora SET estado='Confirmada' WHERE id_reserva=?", (id_reserva,))
        conn.commit()
        cursor.close(); conn.close()
        flash('Reserva confirmada.', 'success')
        return redirect(url_for('admin_compu'))
    except Exception as e:
        return f"Error: {e}", 500

@app.route('/admin/compu/devolver/<int:id_reserva>', methods=['POST'])
@admin_required('compu')
def admin_compu_devolver(id_reserva):
    en_buen_estado = 1 if request.form.get('en_buen_estado') else 0
    cargador = 1 if request.form.get('cargador_devuelto') else 0
    mouse = 1 if request.form.get('mouse_devuelto') else 0
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id_computadora FROM ReservasComputadora WHERE id_reserva=?", (id_reserva,))
        row = cursor.fetchone()
        if not row: return "No encontrado", 404
        id_c = row[0]
        cursor.execute("""
            UPDATE ReservasComputadora
            SET estado='Devuelta', hora_fin=GETDATE(), en_buen_estado=?, cargador_devuelto=?, mouse_devuelto=?
            WHERE id_reserva=?
        """, (en_buen_estado, cargador, mouse, id_reserva))
        cursor.execute("UPDATE Computadoras SET disponible=1 WHERE id_computadora=?", (id_c,))
        conn.commit()
        cursor.close(); conn.close()
        flash('Devolución registrada.', 'success')
        return redirect(url_for('admin_compu'))
    except Exception as e:
        return f"Error: {e}", 500

@app.route('/admin/salas')
@admin_required('salas')
def admin_salas():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT b.id_bloqueo, s.nombre, b.fecha, b.hora_inicio, b.hora_fin, b.motivo
            FROM BloqueoSalas b JOIN Salas s ON b.id_sala=s.id_sala
        """)
        bloqueos = [{'id':r[0],'sala':r[1],'fecha':r[2],'inicio':r[3],'fin':r[4],'motivo':r[5]} for r in cursor.fetchall()]

        cursor.execute("SELECT id_sala, nombre FROM Salas")
        salas = [{'id':r[0],'nombre':r[1]} for r in cursor.fetchall()]

        cursor.close(); conn.close()
        return render_template('admin_salas.html', bloqueos=bloqueos, salas=salas)
    except Exception as e:
        return f"Error: {e}", 500

@app.route('/admin/gral')
@admin_required('gral')
def admin_gral():
    return render_template('admin_gral.html')

@app.route('/admin/restablecer_reservas', methods=['POST'])
@admin_required('gral')
def admin_restablecer_reservas():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # Cambiar estado en vez de borrar
        cursor.execute("UPDATE ReservasSalas SET estado='Finalizada' WHERE estado='Activa'")
        cursor.execute("UPDATE ReservasImpresora3D SET estado='Finalizada' WHERE estado='Activa'")
        cursor.execute("UPDATE PrestamosHerramienta SET estado='Devuelto', fecha_devolucion=GETDATE() WHERE estado='Prestado'")
        cursor.execute("UPDATE DetallePrestamo SET estado='Devuelta', fecha_devolucion=GETDATE() WHERE estado='Prestada'")
        cursor.execute("UPDATE ReservasComputadora SET estado='Devuelta', hora_fin=GETDATE() WHERE estado IN ('Pendiente','Confirmada')")
        # Restablecer disponibilidad
        cursor.execute("UPDATE Salas SET disponible = 1")
        cursor.execute("UPDATE Impresoras3D SET disponible = 1")
        cursor.execute("UPDATE Computadoras SET disponible = 1")
        cursor.execute("UPDATE Herramientas SET cantidad_disponible = cantidad_total")
        conn.commit()
        cursor.close(); conn.close()
        flash('Reservas restablecidas. El historial se ha conservado.', 'success')
        return redirect(url_for('admin_gral'))
    except Exception as e:
        flash(f'Error al restablecer: {e}', 'danger')
        return redirect(url_for('admin_gral'))
    
if __name__ == '__main__':
    app.run(debug=True) 