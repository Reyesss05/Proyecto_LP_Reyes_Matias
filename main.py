import datetime
from pathlib import Path
from typing import Literal

import jwt
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

# ------------------------------------------------------------
# Configuración del token
# ------------------------------------------------------------
SECRET_KEY = "clave_secreta_super_segura_ucalp_2026_mesa_ayuda"
ALGORITHM = "HS256"
EXPIRACION_MINUTOS = 60

app = FastAPI(title="Mejoremos la UCALP - Mesa de ayuda")
seguridad = HTTPBearer()

# Roles que atienden reportes; alumno y docente solo reportan y apoyan
ROLES_STAFF = {"responsable", "admin"}

# ------------------------------------------------------------
# "Base de datos" en memoria (con datos de ejemplo para la demo)
# ------------------------------------------------------------
usuarios: dict[str, dict[str, str]] = {
    "admin": {"password": "admin123", "rol": "admin"},
    "mantenimiento": {"password": "resp123", "rol": "responsable"},
    "sistemas": {"password": "resp123", "rol": "responsable"},
    "alumno_demo": {"password": "1234", "rol": "alumno"},
    "docente_demo": {"password": "1234", "rol": "docente"},
}
tickets: dict[int, dict] = {}
proximo_id = 1


# ------------------------------------------------------------
# Modelos de entrada (cuerpo JSON)
# ------------------------------------------------------------
class UsuarioAlta(BaseModel):
    username: str
    password: str
    rol: str


class UsuarioLogin(BaseModel):
    username: str
    password: str


class UsuarioRol(BaseModel):
    username: str
    rol: str


class UsuarioBaja(BaseModel):
    username: str


Prioridad = Literal["baja", "media", "alta"]
Estado = Literal["abierto", "en_progreso", "resuelto", "cerrado"]
Categoria = Literal["aulas", "wifi", "campus_virtual", "tramites", "biblioteca", "banos", "otra"]
Tipo = Literal["problema", "mejora"]


class TicketAlta(BaseModel):
    titulo: str
    descripcion: str
    categoria: Categoria
    tipo: Tipo = "problema"
    prioridad: Prioridad = "media"
    ubicacion: str | None = None


class TicketEstado(BaseModel):
    estado: Estado


class TicketAsignar(BaseModel):
    username_responsable: str


class Comentario(BaseModel):
    texto: str


# ------------------------------------------------------------
# Lógica de usuarios (Challenge 1)
# ------------------------------------------------------------
def registrar_usuario(usuarios: dict, username: str, password: str, rol: str) -> bool:
    if username in usuarios:
        return False
    usuarios[username] = {"password": password, "rol": rol}
    return True


def generar_token(username: str, rol: str) -> str:
    ahora = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub": username,
        "rol": rol,
        "iat": ahora,
        "exp": ahora + datetime.timedelta(minutes=EXPIRACION_MINUTOS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def autenticar_usuario(usuarios: dict, username: str, password: str) -> dict:
    datos = usuarios.get(username)
    if datos is None or datos["password"] != password:
        return {"autenticado": False, "mensaje": "Credenciales inválidas"}
    token = generar_token(username, datos["rol"])
    return {"autenticado": True, "token": token, "rol": datos["rol"]}


def modificar_rol(usuarios: dict, username: str, nuevo_rol: str) -> dict | None:
    if username not in usuarios:
        return None
    usuarios[username]["rol"] = nuevo_rol
    return {"username": username, "rol": nuevo_rol}


def eliminar_usuario(usuarios: dict, username: str) -> bool:
    if username not in usuarios:
        return False
    del usuarios[username]
    return True


# ------------------------------------------------------------
# Seguridad: obtener el usuario a partir del token
# ------------------------------------------------------------
def usuario_actual(
    credenciales: HTTPAuthorizationCredentials = Depends(seguridad),
) -> dict:
    try:
        payload = jwt.decode(credenciales.credentials, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="El token ha expirado")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido")

    username = payload.get("sub")
    datos = usuarios.get(username)
    if datos is None:
        raise HTTPException(status_code=401, detail="El usuario del token ya no existe")
    # El rol se lee del diccionario, así un cambio de rol aplica al instante
    return {"username": username, "rol": datos["rol"]}


def es_staff(usuario: dict) -> bool:
    return usuario["rol"] in ROLES_STAFF


def buscar_ticket(ticket_id: int) -> dict:
    ticket = tickets.get(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail=f"El reporte {ticket_id} no existe")
    return ticket


def ahora_iso() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def nuevo_ticket(autor: str, titulo: str, descripcion: str, categoria: str,
                 tipo: str = "problema", prioridad: str = "media",
                 ubicacion: str | None = None) -> dict:
    global proximo_id
    ticket = {
        "id": proximo_id,
        "titulo": titulo,
        "descripcion": descripcion,
        "categoria": categoria,
        "tipo": tipo,
        "prioridad": prioridad,
        "ubicacion": ubicacion,
        "estado": "abierto",
        "autor": autor,
        "asignado_a": None,
        "apoyos": [],
        "comentarios": [],
        "creado": ahora_iso(),
    }
    tickets[proximo_id] = ticket
    proximo_id += 1
    return ticket


def cargar_ejemplos() -> None:
    t = nuevo_ticket("docente_demo", "El proyector del aula 12 no enciende",
                     "Desde el lunes no prende. Tuve que dar la clase sin diapositivas.",
                     "aulas", "problema", "alta", "Aula 12, 2.º piso")
    t["apoyos"] = ["alumno_demo"]
    t["asignado_a"] = "mantenimiento"
    t["estado"] = "en_progreso"
    t["comentarios"].append({"autor": "mantenimiento", "fecha": ahora_iso(),
                             "texto": "Pedimos la lámpara de repuesto, llega esta semana."})

    t = nuevo_ticket("alumno_demo", "El Wi-Fi se corta en la biblioteca",
                     "Se desconecta cada pocos minutos, sobre todo a la tarde.",
                     "wifi", "problema", "alta", "Biblioteca central")
    t["apoyos"] = ["docente_demo"]

    nuevo_ticket("alumno_demo", "Más enchufes en las mesas de estudio",
                  "Casi no hay enchufes y las notebooks no aguantan toda la tarde.",
                  "biblioteca", "mejora", "media", "Biblioteca, sala de lectura")

    t = nuevo_ticket("docente_demo", "Publicar las fechas de parciales en el campus virtual",
                     "Un calendario único evitaría que se superpongan parciales.",
                     "campus_virtual", "mejora", "baja")
    t["asignado_a"] = "sistemas"
    t["estado"] = "resuelto"


cargar_ejemplos()


# ------------------------------------------------------------
# Front: sirve index.html en http://127.0.0.1:8000/
# ------------------------------------------------------------
@app.get("/", include_in_schema=False)
def inicio():
    return FileResponse(Path(__file__).parent / "index.html")


@app.get("/resumen", tags=["Reportes"])
def resumen():
    """Datos públicos para la pantalla de ingreso: totales y lo más apoyado."""
    lista = list(tickets.values())
    activos = [t for t in lista if t["estado"] != "cerrado"]
    destacados = sorted(activos, key=lambda t: (len(t["apoyos"]), t["id"]), reverse=True)[:3]
    return {
        "total": len(lista),
        "abiertos": sum(t["estado"] == "abierto" for t in lista),
        "en_progreso": sum(t["estado"] == "en_progreso" for t in lista),
        "resueltos": sum(t["estado"] == "resuelto" for t in lista),
        "destacados": [
            {"titulo": t["titulo"], "categoria": t["categoria"],
             "apoyos": len(t["apoyos"]), "estado": t["estado"]}
            for t in destacados
        ],
    }


# ------------------------------------------------------------
# Endpoints de usuarios (consigna del Challenge 2)
# ------------------------------------------------------------
@app.post("/alta_usuario", status_code=status.HTTP_201_CREATED, tags=["Usuarios"])
def alta_usuario(datos: UsuarioAlta):
    if not registrar_usuario(usuarios, datos.username, datos.password, datos.rol):
        raise HTTPException(status_code=400, detail=f"El usuario '{datos.username}' ya existe")
    return {"mensaje": f"Usuario '{datos.username}' registrado correctamente"}


@app.post("/login", tags=["Usuarios"])
def login(datos: UsuarioLogin):
    resultado = autenticar_usuario(usuarios, datos.username, datos.password)
    if not resultado["autenticado"]:
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")
    return {"access_token": resultado["token"], "token_type": "bearer", "rol": resultado["rol"]}


@app.put("/modificar_rol", tags=["Usuarios"])
def endpoint_modificar_rol(datos: UsuarioRol):
    actualizado = modificar_rol(usuarios, datos.username, datos.rol)
    if actualizado is None:
        raise HTTPException(status_code=404, detail=f"El usuario '{datos.username}' no existe")
    return {"mensaje": "Rol actualizado correctamente", "usuario": actualizado}


@app.delete("/eliminar_usuario", tags=["Usuarios"])
def endpoint_eliminar_usuario(datos: UsuarioBaja):
    if not eliminar_usuario(usuarios, datos.username):
        raise HTTPException(status_code=404, detail=f"El usuario '{datos.username}' no existe")
    return {"mensaje": f"Usuario '{datos.username}' eliminado correctamente"}


@app.get("/usuarios_responsables", tags=["Usuarios"])
def listar_responsables(usuario: dict = Depends(usuario_actual)):
    if usuario["rol"] != "admin":
        raise HTTPException(status_code=403, detail="Solo admin puede ver a los responsables")
    return [u for u, d in usuarios.items() if d["rol"] == "responsable"]


# ------------------------------------------------------------
# Endpoints de reportes (requieren token)
# ------------------------------------------------------------
@app.post("/tickets", status_code=status.HTTP_201_CREATED, tags=["Reportes"])
def crear_ticket(datos: TicketAlta, usuario: dict = Depends(usuario_actual)):
    ubicacion = (datos.ubicacion or "").strip() or None
    return nuevo_ticket(usuario["username"], datos.titulo, datos.descripcion,
                        datos.categoria, datos.tipo, datos.prioridad, ubicacion)


@app.get("/tickets", tags=["Reportes"])
def listar_tickets(
    estado: Estado | None = None,
    prioridad: Prioridad | None = None,
    categoria: Categoria | None = None,
    tipo: Tipo | None = None,
    mios: bool = False,
    usuario: dict = Depends(usuario_actual),
):
    resultado = list(tickets.values())
    if mios:
        resultado = [t for t in resultado if t["autor"] == usuario["username"]
                     or t["asignado_a"] == usuario["username"]]
    if estado:
        resultado = [t for t in resultado if t["estado"] == estado]
    if prioridad:
        resultado = [t for t in resultado if t["prioridad"] == prioridad]
    if categoria:
        resultado = [t for t in resultado if t["categoria"] == categoria]
    if tipo:
        resultado = [t for t in resultado if t["tipo"] == tipo]
    # Los más apoyados primero; a igual apoyo, los más nuevos
    return sorted(resultado, key=lambda t: (len(t["apoyos"]), t["id"]), reverse=True)


@app.get("/tickets/{ticket_id}", tags=["Reportes"])
def ver_ticket(ticket_id: int, usuario: dict = Depends(usuario_actual)):
    return buscar_ticket(ticket_id)


@app.post("/tickets/{ticket_id}/apoyo", tags=["Reportes"])
def apoyar_ticket(ticket_id: int, usuario: dict = Depends(usuario_actual)):
    """Suma o quita el apoyo ("a mí también me pasa") del usuario actual."""
    ticket = buscar_ticket(ticket_id)
    if ticket["autor"] == usuario["username"]:
        raise HTTPException(status_code=400, detail="No podés apoyar tu propio reporte")
    if ticket["estado"] == "cerrado":
        raise HTTPException(status_code=400, detail="El reporte está cerrado")
    if usuario["username"] in ticket["apoyos"]:
        ticket["apoyos"].remove(usuario["username"])
    else:
        ticket["apoyos"].append(usuario["username"])
    return ticket


@app.put("/tickets/{ticket_id}/tomar", tags=["Reportes"])
def tomar_ticket(ticket_id: int, usuario: dict = Depends(usuario_actual)):
    if usuario["rol"] != "responsable":
        raise HTTPException(status_code=403, detail="Solo un responsable puede tomar reportes")
    ticket = buscar_ticket(ticket_id)
    if ticket["asignado_a"] is not None:
        raise HTTPException(status_code=400, detail=f"Ya lo atiende '{ticket['asignado_a']}'")
    ticket["asignado_a"] = usuario["username"]
    ticket["estado"] = "en_progreso"
    return ticket


@app.put("/tickets/{ticket_id}/asignar", tags=["Reportes"])
def asignar_ticket(ticket_id: int, datos: TicketAsignar, usuario: dict = Depends(usuario_actual)):
    if usuario["rol"] != "admin":
        raise HTTPException(status_code=403, detail="Solo admin puede asignar reportes")
    ticket = buscar_ticket(ticket_id)
    destino = usuarios.get(datos.username_responsable)
    if destino is None or destino["rol"] != "responsable":
        raise HTTPException(status_code=400, detail="El usuario destino no existe o no es responsable")
    ticket["asignado_a"] = datos.username_responsable
    if ticket["estado"] == "abierto":
        ticket["estado"] = "en_progreso"
    return ticket


@app.put("/tickets/{ticket_id}/estado", tags=["Reportes"])
def cambiar_estado(ticket_id: int, datos: TicketEstado, usuario: dict = Depends(usuario_actual)):
    ticket = buscar_ticket(ticket_id)
    if not es_staff(usuario):
        raise HTTPException(status_code=403, detail="Solo responsables o admin cambian el estado")
    if usuario["rol"] == "responsable" and ticket["asignado_a"] != usuario["username"]:
        raise HTTPException(status_code=403, detail="Solo podés cambiar reportes asignados a vos")
    ticket["estado"] = datos.estado
    return ticket


@app.post("/tickets/{ticket_id}/comentarios", status_code=status.HTTP_201_CREATED, tags=["Reportes"])
def comentar_ticket(ticket_id: int, datos: Comentario, usuario: dict = Depends(usuario_actual)):
    ticket = buscar_ticket(ticket_id)
    if ticket["estado"] == "cerrado":
        raise HTTPException(status_code=400, detail="El reporte está cerrado")
    comentario = {"autor": usuario["username"], "texto": datos.texto, "fecha": ahora_iso()}
    ticket["comentarios"].append(comentario)
    return ticket


@app.delete("/tickets/{ticket_id}", tags=["Reportes"])
def borrar_ticket(ticket_id: int, usuario: dict = Depends(usuario_actual)):
    if usuario["rol"] != "admin":
        raise HTTPException(status_code=403, detail="Solo admin puede borrar reportes")
    buscar_ticket(ticket_id)
    del tickets[ticket_id]
    return {"mensaje": f"Reporte {ticket_id} eliminado correctamente"}
