from __future__ import annotations

import hmac
import logging
import os
import re
import secrets
from datetime import date, datetime, time
from functools import wraps

import pyodbc
from dotenv import load_dotenv
from flask import Flask, abort, flash, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
secret_key = os.getenv("SECRET_KEY")
if not secret_key:
    raise RuntimeError("Falta SECRET_KEY en el archivo .env. Genera una clave segura antes de iniciar la app.")
app.secret_key = secret_key
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")

CARNET_RE = re.compile(r"^KEY_000\d{3}$")
FILAMENTOS = {"PLA", "PETG", "TPU", "Otro"}
TIPOS_TRABAJO = {"Individual", "Grupal"}


def get_db_connection():
    driver = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")
    server = os.getenv("DB_SERVER")
    db_name = os.getenv("DB_NAME", "InformationUSR")
    if not server:
        raise RuntimeError("Falta DB_SERVER en .env")
    conn_str = (
        f"DRIVER={{{driver}}};SERVER={server};DATABASE={db_name};"
        "Trusted_Connection=yes;TrustServerCertificate=yes;"
    )
    return pyodbc.connect(conn_str)


def csrf_token() -> str:
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


app.jinja_env.globals["csrf_token"] = csrf_token


@app.before_request
def proteger_post_y_actualizar_recursos():
    if request.method == "POST":
        esperado = session.get("_csrf_token", "")
        recibido = request.form.get("_csrf_token", "")
        if not esperado or not hmac.compare_digest(esperado, recibido):
            abort(400, description="Solicitud inválida. Recarga la página e inténtalo nuevamente.")
    if request.endpoint not in {"static", "login", "login_admin", "logout"}:
        sincronizar_recursos_expirados()


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "id_usuario" not in session:
            flash("Inicia sesión para continuar.", "warning")
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper


def admin_required(*tipos):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if "admin" not in session:
                flash("Acceso restringido a administradores.", "danger")
                return redirect(url_for("login_admin"))
            actual = session.get("admin_tipo")
            if tipos and actual not in tipos and actual != "gral":
                flash("No tienes permisos para esta sección.", "danger")
                return redirect(url_for("admin_dashboard"))
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def parse_entero(valor, minimo=None, maximo=None):
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        return None
    if minimo is not None and numero < minimo:
        return None
    if maximo is not None and numero > maximo:
        return None
    return numero


def sincronizar_recursos_expirados():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE ReservasSalas
            SET estado='Finalizada'
            WHERE estado='Activa'
              AND (
                  fecha < CAST(GETDATE() AS DATE)
                  OR (
                      fecha = CAST(GETDATE() AS DATE)
                      AND hora_fin <= CAST(GETDATE() AS TIME)
                  )
              )
        """)
        cur.execute("UPDATE ReservasImpresora3D SET estado='Finalizada' WHERE estado='Activa' AND hora_fin <= GETDATE()")
        cur.execute("UPDATE ReservasCNC SET estado='Finalizada' WHERE estado='Activa' AND hora_fin <= GETDATE()")
        cur.execute("""
            UPDATE i SET disponible=1 FROM Impresoras3D i
            WHERE NOT EXISTS (SELECT 1 FROM ReservasImpresora3D r
                              WHERE r.id_impresora=i.id_impresora AND r.estado='Activa' AND r.hora_fin > GETDATE())
        """)
        cur.execute("""
            UPDATE m SET disponible=1 FROM MaquinasCNC m
            WHERE NOT EXISTS (SELECT 1 FROM ReservasCNC r
                              WHERE r.id_cnc=m.id_cnc AND r.estado='Activa' AND r.hora_fin > GETDATE())
        """)
        conn.commit()
        cur.close(); conn.close()
    except Exception:
        logger.exception("No se pudo sincronizar disponibilidad automática")


def get_limite_pla(id_usuario: int, cohorte: str) -> int:
    try:
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute("SELECT TOP 1 limite_gramos FROM LimiteFilamento WHERE tipo='persona' AND id_usuario=?", id_usuario)
        row = cur.fetchone()
        if not row:
            cur.execute("SELECT TOP 1 limite_gramos FROM LimiteFilamento WHERE tipo='cohorte' AND cohorte=?", cohorte)
            row = cur.fetchone()
        cur.close(); conn.close()
        return int(row[0]) if row else 750
    except Exception:
        logger.exception("No se pudo leer límite PLA")
        return 750


def get_bloqueo_kite(id_usuario: int, cohorte: str):
    try:
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute("""
            SELECT TOP 1 mensaje FROM BloqueoKite
            WHERE activo=1 AND ((tipo='persona' AND id_usuario=?) OR (tipo='cohorte' AND cohorte=?))
        """, id_usuario, cohorte)
        row = cur.fetchone(); cur.close(); conn.close()
        return row[0] if row else None
    except Exception:
        logger.exception("No se pudo verificar bloqueo KITE")
        return None


def validar_acceso_kite():
    mensaje = get_bloqueo_kite(session["id_usuario"], session.get("cohorte", ""))
    return render_template("kite_bloqueado.html", mensaje=mensaje) if mensaje else None


@app.errorhandler(400)
def error_400(error):
    return render_template("error.html", titulo="Solicitud inválida", mensaje=str(error.description)), 400


@app.errorhandler(404)
def error_404(error):
    return render_template("error.html", titulo="Página no encontrada", mensaje="La página solicitada no existe."), 404


@app.errorhandler(500)
def error_500(error):
    return render_template("error.html", titulo="Error interno", mensaje="Ocurrió un error. Intenta de nuevo."), 500


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        carnet = request.form.get("carnet_us", "").strip().upper()
        cohorte = request.form.get("cohorte", "").strip()
        if not usuario or not CARNET_RE.fullmatch(carnet) or not cohorte:
            return render_template("login.html", error="Completa los datos. El carnet debe ser KEY_000###.")
        try:
            conn = get_db_connection(); cur = conn.cursor()
            cur.execute("SELECT id_usuario, usuario, cohorte_sel FROM Usuarios WHERE carnet_us=?", carnet)
            existente = cur.fetchone()
            if existente:
                if existente[1].strip().lower() != usuario.lower():
                    cur.close(); conn.close()
                    return render_template("login.html", error="El carnet ya está registrado con otro nombre.")
                id_usuario, usuario, cohorte = existente[0], existente[1], existente[2]
            else:
                cur.execute("""
                    INSERT INTO Usuarios(usuario, carnet_us, cohorte_sel)
                    OUTPUT INSERTED.id_usuario VALUES (?, ?, ?)
                """, usuario, carnet, cohorte)
                id_usuario = cur.fetchone()[0]
            cur.execute("INSERT INTO LogsIngreso(carnet_us) VALUES (?)", carnet)
            conn.commit(); cur.close(); conn.close()
            session.clear(); csrf_token()
            session.update(id_usuario=id_usuario, usuario=usuario, carnet=carnet, cohorte=cohorte)
            return redirect(url_for("home"))
        except Exception:
            logger.exception("Error en login de estudiante")
            return render_template("login.html", error="No se pudo iniciar sesión. Revisa la conexión a la base de datos.")
    return render_template("login.html")


@app.route("/login_admin", methods=["GET", "POST"])
def login_admin():
    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        password = request.form.get("contrasena", "")
        try:
            conn = get_db_connection(); cur = conn.cursor()
            cur.execute("SELECT tipo, contrasena FROM Administradores WHERE usuario=?", usuario)
            row = cur.fetchone()
            valido = False
            if row:
                almacenada = str(row[1])
                if almacenada.startswith(("scrypt:", "pbkdf2:")):
                    valido = check_password_hash(almacenada, password)
                elif hmac.compare_digest(almacenada, password):
                    # Migración automática de instalaciones antiguas: el siguiente inicio ya queda con hash.
                    valido = True
                    cur.execute("UPDATE Administradores SET contrasena=? WHERE usuario=?", generate_password_hash(password), usuario)
                    conn.commit()
            cur.close(); conn.close()
            if valido:
                session.clear(); csrf_token()
                session.update(admin=usuario, admin_tipo=row[0])
                return redirect(url_for("admin_dashboard"))
            return render_template("admin_login.html", error="Usuario o contraseña incorrectos.")
        except Exception:
            logger.exception("Error en login administrador")
            return render_template("admin_login.html", error="No se pudo iniciar sesión.")
    return render_template("admin_login.html")


@app.route("/logout")
def logout():
    session.clear()
    resp = redirect(url_for("login"))
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    return resp


@app.route("/")
@login_required
def home():
    try:
        conn = get_db_connection(); cur = conn.cursor()
        proximas = []
        cur.execute("""SELECT TOP 3 s.nombre, r.fecha, r.hora_inicio, 'Sala' FROM ReservasSalas r
                       JOIN Salas s ON s.id_sala=r.id_sala
                       WHERE r.id_usuario=? AND r.estado='Activa' AND r.fecha>=CAST(GETDATE() AS DATE)
                       ORDER BY r.fecha, r.hora_inicio""", session["id_usuario"])
        proximas += [{"recurso": r[0], "fecha": r[1], "hora": r[2], "tipo": r[3]} for r in cur.fetchall()]
        cur.execute("""SELECT TOP 3 i.nombre, ri.fecha, ri.hora_fin, 'Impresora 3D' FROM ReservasImpresora3D ri
                       JOIN Impresoras3D i ON i.id_impresora=ri.id_impresora
                       WHERE ri.id_usuario=? AND ri.estado='Activa' ORDER BY ri.fecha DESC""", session["id_usuario"])
        proximas += [{"recurso": r[0], "fecha": r[1], "hora": r[2], "tipo": r[3]} for r in cur.fetchall()]
        cur.close(); conn.close()
        return render_template("home.html", proximas=proximas[:5])
    except Exception:
        logger.exception("Error cargando dashboard")
        return render_template("home.html", proximas=[])


@app.route("/perfil")
@login_required
def perfil():
    return render_template("perfil.html")


@app.route("/salas")
@login_required
def lista_salas():
    try:
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute("SELECT id_sala, nombre, capacidad_max FROM Salas ORDER BY nombre")
        salas = [{"id_sala": r[0], "nombre": r[1], "capacidad_max": r[2]} for r in cur.fetchall()]
        cur.close(); conn.close()
        return render_template("salas.html", salas=salas, hoy=date.today().isoformat())
    except Exception:
        logger.exception("Error listando salas")
        abort(500)


@app.route("/api/salas/<int:id_sala>/disponibilidad")
@login_required
def api_disponibilidad_sala(id_sala):
    fecha_texto = request.args.get("fecha", "").strip()
    try:
        fecha_consulta = date.fromisoformat(fecha_texto)
    except ValueError:
        return jsonify({"error": "Fecha inválida.", "intervalos": []}), 400

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT hora_inicio, hora_fin, 'Reservada' AS tipo
            FROM ReservasSalas
            WHERE id_sala=? AND fecha=? AND estado='Activa'
            UNION ALL
            SELECT hora_inicio, hora_fin, 'Bloqueada' AS tipo
            FROM BloqueoSalas
            WHERE id_sala=? AND fecha=?
            ORDER BY hora_inicio
        """, id_sala, fecha_consulta, id_sala, fecha_consulta)
        intervalos = [
            {
                "inicio": fila[0].strftime("%H:%M"),
                "fin": fila[1].strftime("%H:%M"),
                "tipo": fila[2]
            }
            for fila in cur.fetchall()
        ]
        cur.close()
        conn.close()
        return jsonify({"intervalos": intervalos})
    except Exception:
        logger.exception("Error consultando disponibilidad de sala")
        return jsonify({"error": "No se pudo consultar disponibilidad.", "intervalos": []}), 500


@app.route("/reservar_sala", methods=["POST"])
@login_required
def reservar_sala():
    id_sala = parse_entero(request.form.get("id_sala"), 1)
    cantidad = parse_entero(request.form.get("cantidad_personas"), 2, 6)
    try:
        fecha = date.fromisoformat(request.form.get("fecha", ""))
        inicio = time.fromisoformat(request.form.get("hora_inicio", ""))
        fin = time.fromisoformat(request.form.get("hora_fin", ""))
    except ValueError:
        fecha = inicio = fin = None
    if not id_sala or not cantidad or not fecha or not inicio or not fin:
        flash("Datos de reserva inválidos.", "danger"); return redirect(url_for("lista_salas"))
    ahora = datetime.now()
    if fecha < ahora.date() or inicio < time(6, 0) or fin > time(18, 0) or fin <= inicio:
        flash("La reserva debe ser futura y estar dentro del horario 6:00 AM - 6:00 PM.", "danger")
        return redirect(url_for("lista_salas"))
    if fecha == ahora.date() and inicio <= ahora.time():
        flash("No puedes reservar una hora que ya pasó el día de hoy.", "danger")
        return redirect(url_for("lista_salas"))
    duracion = datetime.combine(fecha, fin) - datetime.combine(fecha, inicio)
    if duracion.total_seconds() > 7200:
        flash("La reserva no puede exceder 2 horas.", "danger"); return redirect(url_for("lista_salas"))
    try:
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
        cur.execute("SELECT capacidad_max FROM Salas WITH (UPDLOCK, HOLDLOCK) WHERE id_sala=?", id_sala)
        sala = cur.fetchone()
        if not sala or cantidad > int(sala[0]):
            flash("La cantidad excede la capacidad de la sala.", "danger"); cur.close(); conn.close(); return redirect(url_for("lista_salas"))
        cur.execute("""SELECT COUNT(*) FROM BloqueoSalas WHERE id_sala=? AND fecha=?
                       AND hora_inicio < ? AND hora_fin > ?""", id_sala, fecha, fin, inicio)
        if cur.fetchone()[0]:
            flash("La sala está bloqueada en ese horario.", "danger"); cur.close(); conn.close(); return redirect(url_for("lista_salas"))
        cur.execute("""SELECT COUNT(*) FROM ReservasSalas WHERE id_sala=? AND fecha=? AND estado='Activa'
                       AND hora_inicio < ? AND hora_fin > ?""", id_sala, fecha, fin, inicio)
        if cur.fetchone()[0]:
            flash("Ya existe una reserva que coincide con ese horario.", "danger"); cur.close(); conn.close(); return redirect(url_for("lista_salas"))
        cur.execute("""INSERT INTO ReservasSalas(id_usuario,id_sala,fecha,hora_inicio,hora_fin,cantidad_personas,estado)
                       OUTPUT INSERTED.id_reserva VALUES (?,?,?,?,?,?,'Activa')""",
                    session["id_usuario"], id_sala, fecha, inicio, fin, cantidad)
        id_reserva = cur.fetchone()[0]
        for i in range(cantidad - 1):
            nombre = request.form.get(f"acomp_nombre_{i}", "").strip()
            carnet = request.form.get(f"acomp_carnet_{i}", "").strip().upper()
            cohorte = request.form.get(f"acomp_cohorte_{i}", "").strip()
            if not nombre or not CARNET_RE.fullmatch(carnet) or not cohorte:
                conn.rollback(); cur.close(); conn.close()
                flash("Completa correctamente todos los acompañantes.", "danger")
                return redirect(url_for("lista_salas"))
            cur.execute("INSERT INTO AcompañantesReserva(id_reserva,nombre_completo,carnet,cohorte) VALUES (?,?,?,?)",
                        id_reserva, nombre, carnet, cohorte)
        conn.commit(); cur.close(); conn.close()
        flash("Sala reservada correctamente.", "success")
    except Exception:
        logger.exception("Error reservando sala")
        flash("No se pudo completar la reserva.", "danger")
    return redirect(url_for("lista_salas"))


@app.route("/api/buscar_usuario_por_carnet")
@login_required
def api_buscar_usuario_por_carnet():
    carnet = request.args.get("carnet", "").strip().upper()
    if not CARNET_RE.fullmatch(carnet):
        return jsonify({})
    try:
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute("SELECT usuario, cohorte_sel FROM Usuarios WHERE carnet_us=?", carnet)
        row = cur.fetchone(); cur.close(); conn.close()
        return jsonify({"nombre": row[0], "cohorte": row[1]}) if row else jsonify({})
    except Exception:
        return jsonify({}), 500


@app.route("/kite")
@login_required
def kite():
    return render_template("kite.html")


@app.route("/kite/impresoras")
@login_required
def kite_impresoras():
    bloqueado = validar_acceso_kite()
    if bloqueado: return bloqueado
    limite = get_limite_pla(session["id_usuario"], session.get("cohorte", ""))
    try:
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute("SELECT id_impresora, nombre, codigo FROM Impresoras3D WHERE disponible=1 ORDER BY codigo")
        impresoras = [{"id": r[0], "nombre": r[1], "codigo": r[2]} for r in cur.fetchall()]
        cur.execute("""SELECT filamento, ISNULL(SUM(gramos),0) FROM ReservasImpresora3D r
                       JOIN CiclosAcademicos c ON CAST(r.fecha AS DATE) BETWEEN c.fecha_inicio AND c.fecha_fin
                       WHERE r.id_usuario=? AND c.activo=1 AND r.estado IN ('Activa','Finalizada') GROUP BY filamento""", session["id_usuario"])
        uso = {r[0]: r[1] for r in cur.fetchall()}; cur.close(); conn.close()
        return render_template("kite_impresoras.html", impresoras=impresoras, limite_pla=limite,
                               gramos_pla=uso.get("PLA", 0), gramos_petg=uso.get("PETG", 0),
                               gramos_tpu=uso.get("TPU", 0), gramos_otro=uso.get("Otro", 0))
    except Exception:
        logger.exception("Error impresoras")
        abort(500)


@app.route("/reservar_impresora", methods=["POST"])
@login_required
def reservar_impresora():
    if validar_acceso_kite():
        flash("No tienes permitido reservar recursos KITE.", "danger"); return redirect(url_for("kite"))
    id_imp = parse_entero(request.form.get("id_impresora"), 1)
    horas = parse_entero(request.form.get("horas"), 0, 24)
    minutos = parse_entero(request.form.get("minutos"), 0, 59)
    gramos = parse_entero(request.form.get("gramos"), 1, 10000)
    filamento = request.form.get("filamento", "")
    trabajo = request.form.get("tipo_trabajo", "")
    if not id_imp or horas is None or minutos is None or not gramos or filamento not in FILAMENTOS or trabajo not in TIPOS_TRABAJO:
        flash("Datos de impresora inválidos.", "danger"); return redirect(url_for("kite_impresoras"))
    total = horas * 60 + minutos
    if total <= 0:
        flash("El tiempo debe ser mayor a cero.", "danger"); return redirect(url_for("kite_impresoras"))
    otro = request.form.get("filamento_otro", "").strip() if filamento == "Otro" else None
    if filamento == "Otro" and not otro:
        flash("Especifica el filamento utilizado.", "danger"); return redirect(url_for("kite_impresoras"))
    try:
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute("UPDATE Impresoras3D SET disponible=0 WHERE id_impresora=? AND disponible=1", id_imp)
        if cur.rowcount != 1:
            conn.rollback(); flash("La impresora ya no está disponible.", "danger"); cur.close(); conn.close(); return redirect(url_for("kite_impresoras"))
        if filamento == "PLA":
            limite = get_limite_pla(session["id_usuario"], session.get("cohorte", ""))
            cur.execute("""SELECT ISNULL(SUM(r.gramos),0) FROM ReservasImpresora3D r
                           JOIN CiclosAcademicos c ON CAST(r.fecha AS DATE) BETWEEN c.fecha_inicio AND c.fecha_fin
                           WHERE r.id_usuario=? AND c.activo=1 AND r.filamento='PLA' AND r.estado IN ('Activa','Finalizada')""", session["id_usuario"])
            usado = int(cur.fetchone()[0])
            if usado + gramos > limite:
                conn.rollback()
                flash(f"Superas tu límite PLA: llevas {usado}g de {limite}g.", "danger")
                cur.close(); conn.close()
                return redirect(url_for("kite_impresoras"))
        cur.execute("""INSERT INTO ReservasImpresora3D(id_usuario,id_impresora,tiempo_minutos,hora_fin,tipo_trabajo,filamento,filamento_otro,gramos,estado)
                       VALUES (?,?,?,DATEADD(minute,?,GETDATE()),?,?,?,?,'Activa')""",
                    session["id_usuario"], id_imp, total, total, trabajo, filamento, otro, gramos)
        conn.commit(); cur.close(); conn.close(); flash("Impresora reservada.", "success")
    except Exception:
        logger.exception("Error reservando impresora"); flash("No se pudo reservar la impresora.", "danger")
    return redirect(url_for("kite_impresoras"))


@app.route("/kite/cnc")
@login_required
def kite_cnc():
    bloqueado = validar_acceso_kite()
    if bloqueado: return bloqueado
    try:
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute("SELECT id_cnc,nombre,codigo FROM MaquinasCNC WHERE disponible=1 ORDER BY codigo")
        maquinas = [{"id": r[0], "nombre": r[1], "codigo": r[2]} for r in cur.fetchall()]
        cur.close(); conn.close(); return render_template("kite_cnc.html", maquinas=maquinas)
    except Exception:
        abort(500)


@app.route("/reservar_cnc", methods=["POST"])
@login_required
def reservar_cnc():
    if validar_acceso_kite():
        flash("No tienes permitido reservar recursos KITE.", "danger"); return redirect(url_for("kite"))
    id_cnc = parse_entero(request.form.get("id_cnc"), 1)
    horas = parse_entero(request.form.get("horas"), 0, 24)
    minutos = parse_entero(request.form.get("minutos"), 0, 59)
    trabajo = request.form.get("tipo_trabajo", "")
    material = request.form.get("material", "").strip()
    if not id_cnc or horas is None or minutos is None or trabajo not in TIPOS_TRABAJO or not material or horas * 60 + minutos <= 0:
        flash("Datos de CNC inválidos.", "danger"); return redirect(url_for("kite_cnc"))
    total = horas * 60 + minutos
    try:
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute("UPDATE MaquinasCNC SET disponible=0 WHERE id_cnc=? AND disponible=1", id_cnc)
        if cur.rowcount != 1:
            conn.rollback(); flash("La CNC ya no está disponible.", "danger"); cur.close(); conn.close(); return redirect(url_for("kite_cnc"))
        cur.execute("""INSERT INTO ReservasCNC(id_usuario,id_cnc,tiempo_minutos,hora_fin,tipo_trabajo,material,estado)
                       VALUES (?,?,?,DATEADD(minute,?,GETDATE()),?,?,'Activa')""", session["id_usuario"], id_cnc, total, total, trabajo, material)
        conn.commit(); cur.close(); conn.close(); flash("CNC reservada.", "success")
    except Exception:
        logger.exception("Error reservando CNC"); flash("No se pudo reservar la CNC.", "danger")
    return redirect(url_for("kite_cnc"))


@app.route("/kite/herramientas")
@login_required
def kite_herramientas():
    bloqueado = validar_acceso_kite()
    if bloqueado: return bloqueado
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("SELECT TOP 1 id_prestamo FROM PrestamosHerramienta WHERE id_usuario=? AND estado='Prestado' ORDER BY fecha_prestamo DESC", session["id_usuario"])
    row = cur.fetchone(); cur.close(); conn.close()
    return render_template("kite_herramientas.html", prestamo_activo=row[0] if row else None)


@app.route("/api/buscar_herramienta")
@login_required
def api_buscar_herramienta():
    q = request.args.get("q", "").strip()
    if not q: return jsonify([])
    try:
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute("""SELECT h.id_herramienta,h.nombre,h.codigo,h.cantidad_disponible,c.nombre
                       FROM Herramientas h JOIN CategoriasHerramienta c ON c.id_categoria=h.id_categoria
                       WHERE h.activa=1 AND h.cantidad_disponible>0 AND (h.nombre LIKE ? OR h.codigo LIKE ?)""", f"%{q}%", f"%{q}%")
        data = [{"id": r[0], "nombre": r[1], "codigo": r[2], "disponible": r[3], "categoria": r[4]} for r in cur.fetchall()]
        for h in data:
            cur.execute("SELECT equipo FROM EPPHerramienta WHERE id_herramienta=?", h["id"])
            h["epp"] = [row[0] for row in cur.fetchall()]
        cur.close(); conn.close(); return jsonify(data)
    except Exception:
        logger.exception("Error API herramienta"); return jsonify([]), 500


@app.route("/prestar_herramienta", methods=["POST"])
@login_required
def prestar_herramienta():
    if validar_acceso_kite():
        flash("No tienes permitido reservar recursos KITE.", "danger")
        return redirect(url_for("kite"))

    ids_texto = list(dict.fromkeys(request.form.getlist("herramientas[]")))
    ids = [parse_entero(valor, 1) for valor in ids_texto]
    if not ids or any(valor is None for valor in ids) or request.form.get("confirmacion_responsabilidad") != "1":
        flash("Selecciona herramientas válidas y acepta la responsabilidad.", "danger")
        return redirect(url_for("kite_herramientas"))

    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM PrestamosHerramienta WHERE id_usuario=? AND estado='Prestado'",
            session["id_usuario"]
        )
        if cur.fetchone()[0]:
            flash("Primero devuelve tu préstamo activo.", "danger")
            cur.close(); conn.close()
            return redirect(url_for("kite_herramientas"))

        for hid in ids:
            cur.execute("""
                UPDATE Herramientas
                SET cantidad_disponible=cantidad_disponible-1
                WHERE id_herramienta=? AND activa=1 AND cantidad_disponible>0
            """, hid)
            if cur.rowcount != 1:
                conn.rollback()
                cur.close(); conn.close()
                flash("Una herramienta ya no está disponible. Actualiza tu selección.", "danger")
                return redirect(url_for("kite_herramientas"))

        cur.execute(
            "INSERT INTO PrestamosHerramienta(id_usuario,estado) "
            "OUTPUT INSERTED.id_prestamo VALUES (?,'Prestado')",
            session["id_usuario"]
        )
        prestamo = cur.fetchone()[0]
        for hid in ids:
            cur.execute(
                "INSERT INTO DetallePrestamo(id_prestamo,id_herramienta) VALUES (?,?)",
                prestamo, hid
            )

        conn.commit()
        cur.close(); conn.close()
        flash("Herramientas prestadas correctamente.", "success")
    except Exception:
        if conn:
            conn.rollback()
        if cur:
            cur.close()
        if conn:
            conn.close()
        logger.exception("Error prestando herramientas")
        flash("No se pudo registrar el préstamo.", "danger")
    return redirect(url_for("kite_herramientas"))

@app.route("/kite/herramientas/devolver/<int:id_prestamo>", methods=["GET", "POST"])
@login_required
def devolver_herramienta(id_prestamo):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT estado FROM PrestamosHerramienta WHERE id_prestamo=? AND id_usuario=?",
        id_prestamo, session["id_usuario"]
    )
    estado = cur.fetchone()
    if not estado or estado[0] != "Prestado":
        cur.close(); conn.close()
        flash("Préstamo no encontrado o ya devuelto.", "danger")
        return redirect(url_for("kite_herramientas"))

    cur.execute("""
        SELECT h.id_herramienta,h.nombre,h.codigo
        FROM DetallePrestamo d
        JOIN Herramientas h ON h.id_herramienta=d.id_herramienta
        WHERE d.id_prestamo=?
    """, id_prestamo)
    herramientas = [{"id": r[0], "nombre": r[1], "codigo": r[2]} for r in cur.fetchall()]

    if request.method == "POST":
        hubo_dano = request.form.get("hubo_dano") == "si"
        ids_validos = {h["id"] for h in herramientas}
        ids_danadas = {
            valor for valor in [
                parse_entero(item, 1) for item in request.form.getlist("herramientas_danadas[]")
            ] if valor is not None
        }

        if hubo_dano and (not ids_danadas or not ids_danadas.issubset(ids_validos)):
            cur.close(); conn.close()
            flash("Selecciona al menos una herramienta dañada válida.", "danger")
            return redirect(request.url)
        if not hubo_dano:
            ids_danadas = set()

        for herramienta in herramientas:
            hid = herramienta["id"]
            if hid in ids_danadas:
                nota = request.form.get(f"nota_dano_{hid}", "").strip()
                cur.execute(
                    "UPDATE DetallePrestamo SET danada=1, nota_dano=? "
                    "WHERE id_prestamo=? AND id_herramienta=?",
                    nota, id_prestamo, hid
                )
                cur.execute("UPDATE Herramientas SET activa=0 WHERE id_herramienta=?", hid)
            else:
                cur.execute(
                    "UPDATE Herramientas SET cantidad_disponible=cantidad_disponible+1 "
                    "WHERE id_herramienta=?",
                    hid
                )

        cur.execute(
            "UPDATE PrestamosHerramienta SET estado='Devuelto',fecha_devolucion=GETDATE() "
            "WHERE id_prestamo=?",
            id_prestamo
        )
        conn.commit()
        cur.close(); conn.close()
        flash("Devolución registrada.", "success")
        return redirect(url_for("kite_herramientas"))

    cur.close(); conn.close()
    return render_template(
        "kite_herramientas_devolver.html",
        prestamo_id=id_prestamo,
        herramientas=herramientas
    )

@app.route("/computadoras")
@login_required
def computadoras():
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("SELECT id_computadora,codigo,nombre,tiene_cargador,tiene_mouse,disponible FROM Computadoras ORDER BY codigo")
    items = [{"id": r[0], "codigo": r[1], "nombre": r[2], "tiene_cargador": r[3], "tiene_mouse": r[4], "disponible": r[5]} for r in cur.fetchall()]
    cur.close(); conn.close(); return render_template("computadoras.html", computadoras=items)


@app.route("/api/buscar_computadora")
@login_required
def api_buscar_computadora():
    q = request.args.get("q", "").strip()
    if not q: return jsonify([])
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("SELECT id_computadora,codigo,nombre,tiene_cargador,tiene_mouse FROM Computadoras WHERE disponible=1 AND (codigo LIKE ? OR nombre LIKE ?)", f"%{q}%", f"%{q}%")
    data = [{"id": r[0], "codigo": r[1], "nombre": r[2], "tiene_cargador": r[3], "tiene_mouse": r[4]} for r in cur.fetchall()]
    cur.close(); conn.close(); return jsonify(data)


@app.route("/reservar_computadora", methods=["POST"])
@login_required
def reservar_computadora():
    id_comp = parse_entero(request.form.get("id_computadora"), 1)
    razon = request.form.get("razon", "").strip()
    otro = request.form.get("razon_otro", "").strip() if razon == "Otro" else None
    if not id_comp or not razon or (razon == "Otro" and not otro):
        flash("Selecciona una computadora y especifica la razón.", "danger"); return redirect(url_for("computadoras"))
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("SELECT codigo FROM Computadoras WHERE id_computadora=?", id_comp); row = cur.fetchone()
    if not row:
        cur.close(); conn.close(); flash("No se encontró esa computadora.", "danger"); return redirect(url_for("computadoras"))
    cur.execute("UPDATE Computadoras SET disponible=0 WHERE id_computadora=? AND disponible=1", id_comp)
    if cur.rowcount != 1:
        conn.rollback(); cur.close(); conn.close(); flash("Esa computadora ya no está disponible.", "danger"); return redirect(url_for("computadoras"))
    cur.execute("INSERT INTO ReservasComputadora(id_usuario,id_computadora,razon,razon_otro,estado) VALUES (?,?,?,?,'Pendiente')", session["id_usuario"], id_comp, razon, otro)
    conn.commit(); cur.close(); conn.close(); flash(f"Solicitud registrada para {row[0]}.", "success")
    return redirect(url_for("computadoras"))


@app.route("/mis_reservas")
@login_required
def mis_reservas():
    tipo = request.args.get("tipo", "todas")
    periodo = request.args.get("periodo", "")
    fecha_texto = request.args.get("fecha", "")
    valores = [session["id_usuario"]]
    condicion = ""
    if periodo == "hoy": condicion = " AND CAST({campo} AS DATE)=CAST(GETDATE() AS DATE)"
    elif periodo == "semana": condicion = " AND {campo}>=DATEADD(day,-7,GETDATE())"
    elif periodo == "mes": condicion = " AND {campo}>=DATEADD(month,-1,GETDATE())"
    elif periodo == "especifica":
        try: fecha_sel = date.fromisoformat(fecha_texto); condicion = " AND CAST({campo} AS DATE)=?"; valores.append(fecha_sel)
        except ValueError: condicion = ""
    data = {"salas": [], "impresoras": [], "cnc": [], "herramientas": [], "computadoras": []}
    conn = get_db_connection(); cur = conn.cursor()
    def params(): return tuple(valores)
    if tipo in ("todas", "salas"):
        cur.execute(f"SELECT r.id_reserva,s.nombre,r.fecha,r.hora_inicio,r.hora_fin,r.estado FROM ReservasSalas r JOIN Salas s ON s.id_sala=r.id_sala WHERE r.id_usuario=?{condicion.format(campo='r.fecha')} ORDER BY r.fecha DESC", params())
        data["salas"] = [{"id": r[0], "sala": r[1], "fecha": r[2], "inicio": r[3], "fin": r[4], "estado": r[5]} for r in cur.fetchall()]
    if tipo in ("todas", "impresoras"):
        cur.execute(f"SELECT r.id_reserva,i.nombre,r.fecha,r.filamento,r.gramos,r.estado FROM ReservasImpresora3D r JOIN Impresoras3D i ON i.id_impresora=r.id_impresora WHERE r.id_usuario=?{condicion.format(campo='r.fecha')} ORDER BY r.fecha DESC", params())
        data["impresoras"] = [{"id": r[0], "impresora": r[1], "fecha": r[2], "filamento": r[3], "gramos": r[4], "estado": r[5]} for r in cur.fetchall()]
    if tipo in ("todas", "cnc"):
        cur.execute(f"SELECT r.id_reserva,m.nombre,r.fecha,r.material,r.estado FROM ReservasCNC r JOIN MaquinasCNC m ON m.id_cnc=r.id_cnc WHERE r.id_usuario=?{condicion.format(campo='r.fecha')} ORDER BY r.fecha DESC", params())
        data["cnc"] = [{"id": r[0], "cnc": r[1], "fecha": r[2], "material": r[3], "estado": r[4]} for r in cur.fetchall()]
    if tipo in ("todas", "herramientas"):
        cur.execute(f"SELECT p.id_prestamo,p.fecha_prestamo,p.estado FROM PrestamosHerramienta p WHERE p.id_usuario=?{condicion.format(campo='p.fecha_prestamo')} ORDER BY p.fecha_prestamo DESC", params())
        data["herramientas"] = [{"id": r[0], "fecha": r[1], "estado": r[2]} for r in cur.fetchall()]
    if tipo in ("todas", "computadoras"):
        cur.execute(f"SELECT r.id_reserva,c.codigo,c.nombre,r.razon,r.hora_inicio,r.estado FROM ReservasComputadora r JOIN Computadoras c ON c.id_computadora=r.id_computadora WHERE r.id_usuario=?{condicion.format(campo='r.hora_inicio')} ORDER BY r.hora_inicio DESC", params())
        data["computadoras"] = [{"id": r[0], "codigo": r[1], "nombre": r[2], "razon": r[3], "inicio": r[4], "estado": r[5]} for r in cur.fetchall()]
    cur.close(); conn.close()
    return render_template("mis_reservas.html", **data, tipo=tipo, periodo=periodo, fecha_esp=fecha_texto)


@app.route("/cancelar/<tipo>/<int:id_reserva>", methods=["POST"])
@login_required
def cancelar_reserva(tipo, id_reserva):
    mapas = {
        "sala": ("ReservasSalas", "id_reserva"),
        "impresora": ("ReservasImpresora3D", "id_reserva"),
        "cnc": ("ReservasCNC", "id_reserva"),
        "computadora": ("ReservasComputadora", "id_reserva"),
    }
    if tipo not in mapas: abort(404)
    tabla, pk = mapas[tipo]
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute(f"SELECT estado FROM {tabla} WHERE {pk}=? AND id_usuario=?", id_reserva, session["id_usuario"])
    row = cur.fetchone()
    if not row or row[0] not in ("Activa", "Pendiente"):
        cur.close(); conn.close(); flash("La reserva no se puede cancelar.", "danger"); return redirect(url_for("mis_reservas"))
    cur.execute(f"UPDATE {tabla} SET estado='Cancelada' WHERE {pk}=?", id_reserva)
    if tipo == "impresora": cur.execute("UPDATE Impresoras3D SET disponible=1 WHERE id_impresora=(SELECT id_impresora FROM ReservasImpresora3D WHERE id_reserva=?)", id_reserva)
    if tipo == "cnc": cur.execute("UPDATE MaquinasCNC SET disponible=1 WHERE id_cnc=(SELECT id_cnc FROM ReservasCNC WHERE id_reserva=?)", id_reserva)
    if tipo == "computadora": cur.execute("UPDATE Computadoras SET disponible=1 WHERE id_computadora=(SELECT id_computadora FROM ReservasComputadora WHERE id_reserva=?)", id_reserva)
    conn.commit(); cur.close(); conn.close(); flash("Reserva cancelada.", "success")
    return redirect(url_for("mis_reservas"))


@app.route("/admin/historial")
@admin_required("kite", "compu", "salas", "gral")
def admin_historial():
    admin_tipo = session.get("admin_tipo", "")
    recursos_por_admin = {
        "salas": ["salas"],
        "compu": ["computadoras"],
        "kite": ["impresoras", "cnc", "herramientas"],
        "gral": ["salas", "computadoras", "impresoras", "cnc", "herramientas"],
    }
    recursos_permitidos = recursos_por_admin.get(admin_tipo, [])
    recurso = request.args.get("recurso", "todos").strip().lower()
    estado = request.args.get("estado", "").strip()
    fecha_texto = request.args.get("fecha", "").strip()
    busqueda = request.args.get("busqueda", "").strip().lower()

    if recurso != "todos" and recurso not in recursos_permitidos:
        flash("No tienes acceso al historial de ese módulo.", "danger")
        return redirect(url_for("admin_historial"))

    fecha_filtro = None
    if fecha_texto:
        try:
            fecha_filtro = date.fromisoformat(fecha_texto)
        except ValueError:
            flash("La fecha seleccionada no es válida.", "warning")

    def seleccionado(tipo_recurso):
        return tipo_recurso in recursos_permitidos and recurso in ("todos", tipo_recurso)

    def hora_corta(valor):
        return valor.strftime("%H:%M") if valor else ""

    movimientos = []
    conn = get_db_connection()
    cur = conn.cursor()

    if seleccionado("salas"):
        cur.execute("""
            SELECT TOP 250 r.id_reserva, s.nombre, u.usuario, u.carnet_us,
                   r.estado, r.fecha, r.hora_inicio, r.hora_fin
            FROM ReservasSalas r
            JOIN Salas s ON s.id_sala=r.id_sala
            JOIN Usuarios u ON u.id_usuario=r.id_usuario
            ORDER BY r.fecha DESC, r.hora_inicio DESC
        """)
        movimientos.extend([{
            "tipo": "Sala", "clave": "salas", "id": r[0], "recurso": r[1],
            "usuario": r[2], "carnet": r[3], "estado": r[4], "fecha": r[5],
            "detalle": f"{hora_corta(r[6])} - {hora_corta(r[7])}"
        } for r in cur.fetchall()])

    if seleccionado("computadoras"):
        cur.execute("""
            SELECT TOP 250 r.id_reserva, c.codigo, c.nombre, u.usuario, u.carnet_us,
                   r.estado, r.hora_inicio, r.razon, r.razon_otro
            FROM ReservasComputadora r
            JOIN Computadoras c ON c.id_computadora=r.id_computadora
            JOIN Usuarios u ON u.id_usuario=r.id_usuario
            ORDER BY r.hora_inicio DESC
        """)
        movimientos.extend([{
            "tipo": "Computadora", "clave": "computadoras", "id": r[0],
            "recurso": f"{r[1]} — {r[2]}", "usuario": r[3], "carnet": r[4],
            "estado": r[5], "fecha": r[6],
            "detalle": f"{r[7]}{(' — ' + r[8]) if r[8] else ''}"
        } for r in cur.fetchall()])

    if seleccionado("impresoras"):
        cur.execute("""
            SELECT TOP 250 r.id_reserva, i.nombre, i.codigo, u.usuario, u.carnet_us,
                   r.estado, r.fecha, r.filamento, r.gramos
            FROM ReservasImpresora3D r
            JOIN Impresoras3D i ON i.id_impresora=r.id_impresora
            JOIN Usuarios u ON u.id_usuario=r.id_usuario
            ORDER BY r.fecha DESC
        """)
        movimientos.extend([{
            "tipo": "Impresora 3D", "clave": "impresoras", "id": r[0],
            "recurso": f"{r[1]} ({r[2]})", "usuario": r[3], "carnet": r[4],
            "estado": r[5], "fecha": r[6], "detalle": f"{r[7]} — {r[8]}g"
        } for r in cur.fetchall()])

    if seleccionado("cnc"):
        cur.execute("""
            SELECT TOP 250 r.id_reserva, m.nombre, m.codigo, u.usuario, u.carnet_us,
                   r.estado, r.fecha, r.material
            FROM ReservasCNC r
            JOIN MaquinasCNC m ON m.id_cnc=r.id_cnc
            JOIN Usuarios u ON u.id_usuario=r.id_usuario
            ORDER BY r.fecha DESC
        """)
        movimientos.extend([{
            "tipo": "CNC", "clave": "cnc", "id": r[0],
            "recurso": f"{r[1]} ({r[2]})", "usuario": r[3], "carnet": r[4],
            "estado": r[5], "fecha": r[6], "detalle": f"Material: {r[7]}"
        } for r in cur.fetchall()])

    if seleccionado("herramientas"):
        cur.execute("""
            SELECT TOP 1000 p.id_prestamo, u.usuario, u.carnet_us, p.estado,
                   p.fecha_prestamo, h.nombre
            FROM PrestamosHerramienta p
            JOIN Usuarios u ON u.id_usuario=p.id_usuario
            JOIN DetallePrestamo d ON d.id_prestamo=p.id_prestamo
            JOIN Herramientas h ON h.id_herramienta=d.id_herramienta
            ORDER BY p.fecha_prestamo DESC, p.id_prestamo DESC
        """)
        prestamos = {}
        for r in cur.fetchall():
            if r[0] not in prestamos:
                prestamos[r[0]] = {
                    "tipo": "Herramientas", "clave": "herramientas", "id": r[0],
                    "recurso": f"Préstamo #{r[0]}", "usuario": r[1], "carnet": r[2],
                    "estado": r[3], "fecha": r[4], "herramientas": []
                }
            prestamos[r[0]]["herramientas"].append(r[5])
        for prestamo in prestamos.values():
            prestamo["detalle"] = ", ".join(prestamo.pop("herramientas"))
            movimientos.append(prestamo)

    cur.close()
    conn.close()

    if estado:
        movimientos = [m for m in movimientos if m["estado"] == estado]

    if fecha_filtro:
        movimientos = [
            m for m in movimientos
            if (m["fecha"].date() if isinstance(m["fecha"], datetime) else m["fecha"]) == fecha_filtro
        ]

    if busqueda:
        movimientos = [
            m for m in movimientos
            if busqueda in " ".join([
                str(m["tipo"]), str(m["recurso"]), str(m["usuario"]),
                str(m["carnet"]), str(m["detalle"]), str(m["estado"])
            ]).lower()
        ]

    def ordenar_fecha(movimiento):
        valor = movimiento["fecha"]
        return valor if isinstance(valor, datetime) else datetime.combine(valor, time.min)

    movimientos.sort(key=ordenar_fecha, reverse=True)

    return render_template(
        "admin_historial.html",
        movimientos=movimientos,
        recursos_permitidos=recursos_permitidos,
        recurso=recurso,
        estado=estado,
        fecha_filtro=fecha_texto,
        busqueda=request.args.get("busqueda", "").strip(),
        admin_tipo=admin_tipo
    )


@app.route("/admin")
@admin_required()
def admin_dashboard():
    tipo = session.get("admin_tipo")
    return redirect(url_for({"kite": "admin_kite", "compu": "admin_compu", "salas": "admin_salas"}.get(tipo, "admin_gral")))


@app.route("/admin/compu")
@admin_required("compu")
def admin_compu():
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("""SELECT r.id_reserva,c.codigo,u.usuario,u.carnet_us,r.razon,r.razon_otro,r.hora_inicio
                   FROM ReservasComputadora r JOIN Computadoras c ON c.id_computadora=r.id_computadora
                   JOIN Usuarios u ON u.id_usuario=r.id_usuario WHERE r.estado='Pendiente' ORDER BY r.hora_inicio""")
    pendientes = [{"id": r[0], "codigo": r[1], "usuario": r[2], "carnet": r[3], "razon": r[4], "razon_otro": r[5], "inicio": r[6]} for r in cur.fetchall()]
    cur.execute("""SELECT r.id_reserva,c.codigo,u.usuario,u.carnet_us,r.razon,r.hora_inicio,c.tiene_cargador,c.tiene_mouse
                   FROM ReservasComputadora r JOIN Computadoras c ON c.id_computadora=r.id_computadora
                   JOIN Usuarios u ON u.id_usuario=r.id_usuario WHERE r.estado='Confirmada' ORDER BY r.hora_inicio""")
    confirmadas = [{"id": r[0], "codigo": r[1], "usuario": r[2], "carnet": r[3], "razon": r[4], "inicio": r[5], "cargador": r[6], "mouse": r[7]} for r in cur.fetchall()]
    cur.close(); conn.close(); return render_template("admin_compu.html", pendientes=pendientes, confirmadas=confirmadas)


@app.route("/admin/compu/confirmar/<int:id_reserva>", methods=["POST"])
@admin_required("compu")
def admin_compu_confirmar(id_reserva):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE ReservasComputadora SET estado='Confirmada' "
        "WHERE id_reserva=? AND estado='Pendiente'",
        id_reserva
    )
    if cur.rowcount != 1:
        conn.rollback()
        cur.close(); conn.close()
        flash("La solicitud ya no está pendiente o no existe.", "warning")
        return redirect(url_for("admin_compu"))
    conn.commit()
    cur.close(); conn.close()
    flash("Entrega confirmada.", "success")
    return redirect(url_for("admin_compu"))

@app.route("/admin/compu/devolver/<int:id_reserva>", methods=["POST"])
@admin_required("compu")
def admin_compu_devolver(id_reserva):
    conn = get_db_connection(); cur = conn.cursor(); cur.execute("SELECT id_computadora FROM ReservasComputadora WHERE id_reserva=? AND estado='Confirmada'", id_reserva); row = cur.fetchone()
    if not row: cur.close(); conn.close(); flash("Préstamo no encontrado.", "danger"); return redirect(url_for("admin_compu"))
    cur.execute("UPDATE ReservasComputadora SET estado='Devuelta',hora_fin=GETDATE(),en_buen_estado=?,cargador_devuelto=?,mouse_devuelto=? WHERE id_reserva=?", 1 if request.form.get("en_buen_estado") else 0, 1 if request.form.get("cargador_devuelto") else 0, 1 if request.form.get("mouse_devuelto") else 0, id_reserva)
    cur.execute("UPDATE Computadoras SET disponible=1 WHERE id_computadora=?", row[0]); conn.commit(); cur.close(); conn.close(); flash("Devolución registrada.", "success"); return redirect(url_for("admin_compu"))


@app.route("/admin/salas")
@admin_required("salas")
def admin_salas():
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("SELECT id_sala,nombre FROM Salas ORDER BY nombre"); salas = [{"id": r[0], "nombre": r[1]} for r in cur.fetchall()]
    cur.execute("SELECT b.id_bloqueo,s.nombre,b.fecha,b.hora_inicio,b.hora_fin,b.motivo FROM BloqueoSalas b JOIN Salas s ON s.id_sala=b.id_sala ORDER BY b.fecha DESC"); bloqueos = [{"id": r[0], "sala": r[1], "fecha": r[2], "inicio": r[3], "fin": r[4], "motivo": r[5]} for r in cur.fetchall()]
    cur.close(); conn.close(); return render_template("admin_salas.html", salas=salas, bloqueos=bloqueos, hoy=date.today().isoformat())


@app.route("/admin/salas/bloquear", methods=["POST"])
@admin_required("salas")
def admin_salas_bloquear():
    id_sala = parse_entero(request.form.get("id_sala"), 1)
    motivo = request.form.get("motivo", "").strip()
    try:
        fecha = date.fromisoformat(request.form.get("fecha", ""))
        inicio = time.fromisoformat(request.form.get("hora_inicio", ""))
        fin = time.fromisoformat(request.form.get("hora_fin", ""))
    except ValueError:
        fecha = inicio = fin = None

    ahora = datetime.now()
    if (
        not id_sala or not motivo or not fecha or not inicio or not fin
        or fecha < ahora.date() or fin <= inicio
        or inicio < time(6, 0) or fin > time(18, 0)
    ):
        flash("Datos de bloqueo inválidos.", "danger")
        return redirect(url_for("admin_salas"))
    if fecha == ahora.date() and inicio <= ahora.time():
        flash("No puedes crear un bloqueo para una hora que ya pasó.", "danger")
        return redirect(url_for("admin_salas"))

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*) FROM ReservasSalas
        WHERE id_sala=? AND fecha=? AND estado='Activa'
          AND hora_inicio < ? AND hora_fin > ?
    """, id_sala, fecha, fin, inicio)
    if cur.fetchone()[0]:
        cur.close(); conn.close()
        flash("No se puede bloquear: ya existe una reserva activa en ese horario.", "danger")
        return redirect(url_for("admin_salas"))

    cur.execute("""
        SELECT COUNT(*) FROM BloqueoSalas
        WHERE id_sala=? AND fecha=?
          AND hora_inicio < ? AND hora_fin > ?
    """, id_sala, fecha, fin, inicio)
    if cur.fetchone()[0]:
        cur.close(); conn.close()
        flash("Ya existe un bloqueo que coincide con ese horario.", "warning")
        return redirect(url_for("admin_salas"))

    cur.execute(
        "INSERT INTO BloqueoSalas(id_sala,fecha,hora_inicio,hora_fin,motivo) VALUES (?,?,?,?,?)",
        id_sala, fecha, inicio, fin, motivo
    )
    conn.commit()
    cur.close(); conn.close()
    flash("Bloqueo creado.", "success")
    return redirect(url_for("admin_salas"))

@app.route("/admin/salas/bloqueo/<int:id_bloqueo>/eliminar", methods=["POST"])
@admin_required("salas")
def admin_salas_eliminar_bloqueo(id_bloqueo):
    conn=get_db_connection(); cur=conn.cursor(); cur.execute("DELETE FROM BloqueoSalas WHERE id_bloqueo=?", id_bloqueo); conn.commit(); cur.close(); conn.close(); flash("Bloqueo eliminado.", "success"); return redirect(url_for("admin_salas"))


@app.route("/admin/kite")
@admin_required("kite")
def admin_kite():
    conn=get_db_connection(); cur=conn.cursor()
    cur.execute("SELECT l.id_limite,l.tipo,ISNULL(u.usuario,''),ISNULL(l.cohorte,''),l.limite_gramos FROM LimiteFilamento l LEFT JOIN Usuarios u ON u.id_usuario=l.id_usuario"); limites=[{"id":r[0],"tipo":r[1],"usuario":r[2],"cohorte":r[3],"limite":r[4]} for r in cur.fetchall()]
    cur.execute("SELECT b.id_bloqueo,b.tipo,ISNULL(u.usuario,''),ISNULL(b.cohorte,''),b.mensaje FROM BloqueoKite b LEFT JOIN Usuarios u ON u.id_usuario=b.id_usuario WHERE b.activo=1"); bloqueos=[{"id":r[0],"tipo":r[1],"usuario":r[2],"cohorte":r[3],"mensaje":r[4]} for r in cur.fetchall()]
    cur.execute("""SELECT h.id_herramienta,h.nombre,h.codigo,d.nota_dano FROM Herramientas h JOIN DetallePrestamo d ON d.id_herramienta=h.id_herramienta WHERE d.danada=1 AND h.activa=0"""); danadas=[{"id":r[0],"nombre":r[1],"codigo":r[2],"nota":r[3]} for r in cur.fetchall()]
    cur.close(); conn.close(); return render_template("admin_kite.html", limites=limites,bloqueos=bloqueos,danadas=danadas)


@app.route("/admin/kite/bloqueo", methods=["POST"])
@admin_required("kite")
def admin_kite_bloqueo():
    tipo=request.form.get("tipo"); destino=request.form.get("destino", "").strip(); mensaje=request.form.get("mensaje", "").strip()
    if tipo not in ("persona","cohorte") or not destino or not mensaje: flash("Completa el bloqueo.", "danger"); return redirect(url_for("admin_kite"))
    conn=get_db_connection(); cur=conn.cursor(); id_u=None; coh=None
    if tipo == "persona":
        cur.execute("SELECT id_usuario FROM Usuarios WHERE carnet_us=?", destino.upper()); row=cur.fetchone()
        if not row: cur.close(); conn.close(); flash("No se encontró ese carnet.", "danger"); return redirect(url_for("admin_kite"))
        id_u=row[0]
    else: coh=destino
    cur.execute("INSERT INTO BloqueoKite(tipo,id_usuario,cohorte,mensaje,activo) VALUES (?,?,?,?,1)", tipo,id_u,coh,mensaje); conn.commit(); cur.close(); conn.close(); flash("Bloqueo agregado.", "success"); return redirect(url_for("admin_kite"))


@app.route("/admin/kite/bloqueo/<int:id_bloqueo>/quitar", methods=["POST"])
@admin_required("kite")
def admin_kite_quitar_bloqueo(id_bloqueo):
    conn=get_db_connection(); cur=conn.cursor(); cur.execute("UPDATE BloqueoKite SET activo=0 WHERE id_bloqueo=?", id_bloqueo); conn.commit(); cur.close(); conn.close(); flash("Bloqueo retirado.", "success"); return redirect(url_for("admin_kite"))


@app.route("/admin/kite/limite", methods=["POST"])
@admin_required("kite")
def admin_kite_limite():
    tipo=request.form.get("tipo"); destino=request.form.get("destino", "").strip(); gramos=parse_entero(request.form.get("limite"), 1)
    if tipo not in ("persona","cohorte") or not destino or not gramos: flash("Completa el límite.", "danger"); return redirect(url_for("admin_kite"))
    conn=get_db_connection(); cur=conn.cursor(); id_u=None; coh=None
    if tipo == "persona":
        cur.execute("SELECT id_usuario FROM Usuarios WHERE carnet_us=?", destino.upper()); row=cur.fetchone()
        if not row: cur.close(); conn.close(); flash("No se encontró ese carnet.", "danger"); return redirect(url_for("admin_kite"))
        id_u=row[0]
    else: coh=destino
    cur.execute("INSERT INTO LimiteFilamento(tipo,id_usuario,cohorte,limite_gramos) VALUES (?,?,?,?)", tipo,id_u,coh,gramos); conn.commit(); cur.close(); conn.close(); flash("Límite agregado.", "success"); return redirect(url_for("admin_kite"))


@app.route("/admin/kite/herramienta/<int:id_herramienta>/reparar", methods=["POST"])
@admin_required("kite")
def admin_kite_reparar(id_herramienta):
    conn=get_db_connection(); cur=conn.cursor(); cur.execute("UPDATE Herramientas SET activa=1,cantidad_disponible=cantidad_disponible+1 WHERE id_herramienta=? AND activa=0", id_herramienta); conn.commit(); cur.close(); conn.close(); flash("Herramienta habilitada de nuevo.", "success"); return redirect(url_for("admin_kite"))


@app.route("/admin/gral")
@admin_required("gral")
def admin_gral():
    conn=get_db_connection(); cur=conn.cursor(); stats={}
    for nombre, tabla, estado in [("salas","ReservasSalas","Activa"),("impresoras","ReservasImpresora3D","Activa"),("cnc","ReservasCNC","Activa"),("herramientas","PrestamosHerramienta","Prestado"),("computadoras","ReservasComputadora","Confirmada")]:
        cur.execute(f"SELECT COUNT(*) FROM {tabla} WHERE estado=?", estado); stats[nombre]=cur.fetchone()[0]
    cur.close(); conn.close(); return render_template("admin_gral.html", stats=stats)


@app.route("/admin/restablecer_reservas", methods=["POST"])
@admin_required("gral")
def admin_restablecer_reservas():
    conn=get_db_connection(); cur=conn.cursor()
    cur.execute("UPDATE ReservasSalas SET estado='Finalizada' WHERE estado='Activa'"); cur.execute("UPDATE ReservasImpresora3D SET estado='Finalizada' WHERE estado='Activa'"); cur.execute("UPDATE ReservasCNC SET estado='Finalizada' WHERE estado='Activa'"); cur.execute("UPDATE PrestamosHerramienta SET estado='Devuelto',fecha_devolucion=GETDATE() WHERE estado='Prestado'"); cur.execute("UPDATE ReservasComputadora SET estado='Devuelta',hora_fin=GETDATE() WHERE estado IN ('Pendiente','Confirmada')"); cur.execute("UPDATE Impresoras3D SET disponible=1"); cur.execute("UPDATE MaquinasCNC SET disponible=1"); cur.execute("UPDATE Computadoras SET disponible=1"); cur.execute("UPDATE Herramientas SET cantidad_disponible=cantidad_total WHERE activa=1"); conn.commit(); cur.close(); conn.close(); flash("Reservas activas finalizadas y recursos liberados.", "success"); return redirect(url_for("admin_gral"))


if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "0") == "1")
