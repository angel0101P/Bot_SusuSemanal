import os
import threading
from flask import Flask  # ← AGREGAR ESTE IMPORT
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters, CallbackQueryHandler
import psycopg
from datetime import datetime, timedelta
import json
import telegram
from dotenv import load_dotenv

app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot is running", 200

# Configuración
# Cargar variables de entorno
load_dotenv()

# Configuración desde variables de entorno
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')
ADMIN_ID = int(os.getenv('ADMIN_ID', '5908252094'))

# Conexión a la base de datos - CAMBIO PARA PSYCOPG3
def get_db_connection():
    return psycopg.connect(DATABASE_URL)

def reparar_tablas():
    """Reparar tablas existentes agregando columnas faltantes"""
    print("🔧 Verificando y reparando columnas faltantes...")
    
    # Verificar y agregar columna 'descripcion'
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT descripcion FROM productos LIMIT 1")
        conn.close()
        print("✅ Columna 'descripcion' existe")
    except Exception:
        print("⚠️ Agregando columna 'descripcion'...")
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("ALTER TABLE productos ADD COLUMN descripcion TEXT")
            conn.commit()
            conn.close()
            print("✅ Columna 'descripcion' agregada")
        except Exception as e:
            print(f"❌ Error al agregar 'descripcion': {e}")
    
    # Verificar y agregar columna 'categoria'
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT categoria FROM productos LIMIT 1")
        conn.close()
        print("✅ Columna 'categoria' existe")
    except Exception:
        print("⚠️ Agregando columna 'categoria'...")
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("ALTER TABLE productos ADD COLUMN categoria VARCHAR(100)")
            conn.commit()
            conn.close()
            print("✅ Columna 'categoria' agregada")
        except Exception as e:
            print(f"❌ Error al agregar 'categoria': {e}")
    
    # Verificar y agregar columna 'contador_activo'
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT contador_activo FROM config_pagos LIMIT 1")
        conn.close()
        print("✅ Columna 'contador_activo' existe")
    except Exception:
        print("⚠️ Agregando columna 'contador_activo'...")
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("ALTER TABLE config_pagos ADD COLUMN contador_activo BOOLEAN DEFAULT TRUE")
            conn.commit()
            conn.close()
            print("✅ Columna 'contador_activo' agregada")
        except Exception as e:
            print(f"❌ Error al agregar 'contador_activo': {e}")
    
    # Verificar y agregar columna 'contador_pausado' en planes_pago
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT contador_pausado FROM planes_pago LIMIT 1")
        conn.close()
        print("✅ Columna 'contador_pausado' existe")
    except Exception:
        print("⚠️ Agregando columna 'contador_pausado'...")
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("ALTER TABLE planes_pago ADD COLUMN contador_pausado BOOLEAN DEFAULT FALSE")
            conn.commit()
            conn.close()
            print("✅ Columna 'contador_pausado' agregada")
        except Exception as e:
            print(f"❌ Error al agregar 'contador_pausado': {e}")
    
    # ✅ NUEVA: Verificar y agregar columna 'fecha_ultimo_pago' en planes_pago
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT fecha_ultimo_pago FROM planes_pago LIMIT 1")
        conn.close()
        print("✅ Columna 'fecha_ultimo_pago' existe")
    except Exception:
        print("⚠️ Agregando columna 'fecha_ultimo_pago'...")
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("ALTER TABLE planes_pago ADD COLUMN fecha_ultimo_pago TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
            conn.commit()
            conn.close()
            print("✅ Columna 'fecha_ultimo_pago' agregada")
        except Exception as e:
            print(f"❌ Error al agregar 'fecha_ultimo_pago': {e}")
    
    print("🎉 Verificación de columnas completada")

def init_db():
    """Inicializar base de datos con todas las columnas necesarias"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Tabla de usuarios
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS usuarios (
                id SERIAL PRIMARY KEY,
                user_id BIGINT UNIQUE,
                user_name VARCHAR(255),
                first_name VARCHAR(255),
                last_name VARCHAR(255),
                phone VARCHAR(50),
                fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                estado VARCHAR(50) DEFAULT 'activo'
            )
        ''')
        
        # Tabla de pagos
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pagos (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                user_name VARCHAR(255),
                referencia VARCHAR(100),
                file_id VARCHAR(255),
                monto DECIMAL(10,2),
                estado VARCHAR(50) DEFAULT 'pendiente',
                fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabla de productos
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS productos (
                id SERIAL PRIMARY KEY,
                nombre VARCHAR(255),
                descripcion TEXT,
                precio DECIMAL(10,2),
                categoria VARCHAR(100),
                estado VARCHAR(50) DEFAULT 'activo',
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabla de configuración
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS config_pagos (
                id SERIAL PRIMARY KEY,
                semanas INT DEFAULT 10,
                contador_activo BOOLEAN DEFAULT TRUE,
                fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabla de planes de pago activos
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS planes_pago (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                productos_json JSONB,
                total DECIMAL(10,2),
                semanas INT,
                pago_semanal DECIMAL(10,2),
                semanas_completadas INT DEFAULT 0,
                estado VARCHAR(50) DEFAULT 'activo',
                contador_pausado BOOLEAN DEFAULT FALSE,
                fecha_inicio TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                fecha_ultimo_pago TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 🆕 TABLA DE PUNTOS DE USUARIOS
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS usuarios_puntos (
                id SERIAL PRIMARY KEY,
                user_id BIGINT UNIQUE,
                puntos_totales INT DEFAULT 0,
                puntos_disponibles INT DEFAULT 0,
                fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 🆕 TABLA DE REFERIDOS
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS referidos (
                id SERIAL PRIMARY KEY,
                user_id_referidor BIGINT,
                user_id_referido BIGINT,
                nombre_referido VARCHAR(255),
                telefono_referido VARCHAR(50),
                estado VARCHAR(50) DEFAULT 'pendiente',
                puntos_otorgados BOOLEAN DEFAULT FALSE,
                fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 🆕 TABLA DE HISTORIAL DE PUNTOS
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS puntos_historial (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                tipo VARCHAR(50),
                puntos INT,
                descripcion TEXT,
                fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Insertar configuración por defecto
        cursor.execute('''
            INSERT INTO config_pagos (semanas, contador_activo) 
            SELECT 10, TRUE 
            WHERE NOT EXISTS (SELECT 1 FROM config_pagos)
        ''')
        
        conn.commit()
        conn.close()
        
        # ✅ LLAMAR A LA REPARACIÓN DESPUÉS DE CREAR TABLAS
        reparar_tablas()
        
        print("✅ Base de datos inicializada correctamente")
        
    except Exception as e:
        print(f"❌ Error al inicializar BD: {e}")
        reparar_tablas()

def verificar_base_datos():
    """Verificar base de datos"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as total FROM pagos")
        resultado_pagos = cursor.fetchone()
        cursor.execute("SELECT COUNT(*) as total FROM usuarios")
        resultado_usuarios = cursor.fetchone()
        cursor.execute("SELECT COUNT(*) as total FROM productos")
        resultado_productos = cursor.fetchone()
        cursor.execute("SELECT COUNT(*) as total FROM planes_pago WHERE estado = 'activo'")
        resultado_planes = cursor.fetchone()
        cursor.execute("SELECT semanas, contador_activo FROM config_pagos LIMIT 1")
        config = cursor.fetchone()
        
        # 🆕 Verificar sistema de puntos
        cursor.execute("SELECT COUNT(*) as total FROM usuarios_puntos")
        resultado_puntos = cursor.fetchone()
        cursor.execute("SELECT COUNT(*) as total FROM referidos")
        resultado_referidos = cursor.fetchone()
        
        conn.close()
        
        semanas_config = config[0] if config else 10
        contador_activo = config[1] if config else True
        print(f"📊 TOTAL en BD - Pagos: {resultado_pagos[0]}, Usuarios: {resultado_usuarios[0]}, Productos: {resultado_productos[0]}, Planes: {resultado_planes[0]}, Puntos: {resultado_puntos[0]}, Referidos: {resultado_referidos[0]}, Semanas: {semanas_config}, Contador: {'ACTIVO' if contador_activo else 'PAUSADO'}")
        return resultado_pagos[0], resultado_usuarios[0], resultado_productos[0], resultado_planes[0], semanas_config
    except Exception as e:
        print(f"❌ Error al verificar BD: {e}")
        return 0, 0, 0, 0, 10

# =============================================
# 🆕 SISTEMA DE PUNTOS Y REFERIDOS
# =============================================

async def agregar_puntos(user_id: int, puntos: int, tipo: str, descripcion: str):
    """Agrega puntos a un usuario y registra en el historial"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Verificar si el usuario existe en la tabla de puntos
        cursor.execute("SELECT puntos_disponibles FROM usuarios_puntos WHERE user_id = %s", (user_id,))
        usuario_puntos = cursor.fetchone()
        
        if usuario_puntos:
            # Actualizar puntos existentes
            nuevos_puntos = usuario_puntos[0] + puntos
            cursor.execute("""
                UPDATE usuarios_puntos 
                SET puntos_totales = puntos_totales + %s, 
                    puntos_disponibles = %s,
                    fecha_actualizacion = CURRENT_TIMESTAMP
                WHERE user_id = %s
            """, (puntos, nuevos_puntos, user_id))
        else:
            # Crear nuevo registro de puntos
            cursor.execute("""
                INSERT INTO usuarios_puntos (user_id, puntos_totales, puntos_disponibles)
                VALUES (%s, %s, %s)
            """, (user_id, puntos, puntos))
        
        # Registrar en historial
        cursor.execute("""
            INSERT INTO puntos_historial (user_id, tipo, puntos, descripcion)
            VALUES (%s, %s, %s, %s)
        """, (user_id, tipo, puntos, descripcion))
        
        conn.commit()
        conn.close()
        
        print(f"✅ {puntos} puntos agregados a usuario {user_id} - {descripcion}")
        return True
        
    except Exception as e:
        print(f"❌ Error al agregar puntos: {e}")
        return False

async def verificar_beneficios_puntos(user_id: int):
    """Verifica si el usuario alcanzó algún beneficio por puntos"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT puntos_disponibles FROM usuarios_puntos WHERE user_id = %s", (user_id,))
        resultado = cursor.fetchone()
        conn.close()
        
        if not resultado:
            return
        
        puntos_actuales = resultado[0]
        
        # Verificar beneficios
        if puntos_actuales >= 100:
            await notificar_beneficio(user_id, 100, "🎉 ¡FELICIDADES! Has ganado 1 SEMANA GRATIS en el gym 🏋️‍♂️")
        
        if puntos_actuales >= 200:
            await notificar_beneficio(user_id, 200, "🎉 ¡INCREÍBLE! Has ganado 15% DE DESCUENTO en todo 🛍️")
            
    except Exception as e:
        print(f"❌ Error al verificar beneficios: {e}")

async def notificar_beneficio(user_id: int, puntos_requeridos: int, mensaje: str):
    """Notifica un beneficio al usuario"""
    try:
        # Aquí deberías enviar un mensaje al usuario
        # Por ahora solo imprimimos el log
        print(f"🎁 Usuario {user_id} alcanzó {puntos_requeridos} puntos - {mensaje}")
        
        # En un futuro, podrías enviar un mensaje al usuario:
        # await context.bot.send_message(chat_id=user_id, text=mensaje)
        
    except Exception as e:
        print(f"❌ Error al notificar beneficio: {e}")

async def referidos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra el panel de referidos del usuario"""
    user_id = update.effective_user.id
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Obtener información del usuario
    cursor.execute("SELECT first_name, user_name FROM usuarios WHERE user_id = %s", (user_id,))
    usuario = cursor.fetchone()
    
    if not usuario:
        await update.message.reply_text("❌ Debes registrarte con /start primero")
        conn.close()
        return
    
    first_name, user_name = usuario
    
    # Obtener referidos del usuario
    cursor.execute("""
        SELECT r.nombre_referido, r.telefono_referido, r.estado, r.fecha_registro
        FROM referidos r
        WHERE r.user_id_referidor = %s
        ORDER BY r.fecha_registro DESC
    """, (user_id,))
    referidos_lista = cursor.fetchall()
    
    # Obtener puntos del usuario
    cursor.execute("SELECT puntos_disponibles FROM usuarios_puntos WHERE user_id = %s", (user_id,))
    puntos_result = cursor.fetchone()
    puntos_actuales = puntos_result[0] if puntos_result else 0
    
    conn.close()
    
    # Crear código de referido único
    codigo_referido = f"REF{user_id}"
    
    mensaje = f"👥 **TU PANEL DE REFERIDOS**\n\n"
    mensaje += f"👤 **Referidor:** {first_name}\n"
    mensaje += f"🆔 **Tu código:** `{codigo_referido}`\n"
    mensaje += f"⭐ **Tus puntos:** {puntos_actuales}\n\n"
    
    mensaje += "📋 **Cómo referir amigos:**\n"
    mensaje += "1. Comparte tu código con amigos\n"
    mensaje += "2. Ellos deben usar /start con tu código\n"
    mensaje += "3. El admin verificará el referido\n"
    mensaje += "4. ¡Ganas 7 puntos por cada referido!\n\n"
    
    if referidos_lista:
        mensaje += "📊 **TUS REFERIDOS:**\n"
        for nombre, telefono, estado, fecha in referidos_lista:
            icono = "✅" if estado == "aprobado" else "⏳" if estado == "pendiente" else "❌"
            mensaje += f"{icono} **{nombre}** - {telefono}\n"
            mensaje += f"   📅 {fecha.strftime('%d/%m/%Y')} - {estado}\n"
    else:
        mensaje += "📭 **Aún no tienes referidos**\n"
    
    mensaje += f"\n💎 **Beneficios por puntos:**\n"
    mensaje += f"• 100 puntos → 1 semana gratis en gym\n"
    mensaje += f"• 200 puntos → 15% descuento en todo\n"
    
    keyboard = [
        [InlineKeyboardButton("📤 Compartir código", callback_data="compartir_codigo")],
        [InlineKeyboardButton("⭐ Mis puntos", callback_data="ver_mis_puntos")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(mensaje, reply_markup=reply_markup)

async def mispuntos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra los puntos y historial del usuario"""
    user_id = update.effective_user.id
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Obtener puntos del usuario
    cursor.execute("SELECT puntos_totales, puntos_disponibles FROM usuarios_puntos WHERE user_id = %s", (user_id,))
    puntos_result = cursor.fetchone()
    
    if not puntos_result:
        await update.message.reply_text(
            "⭐ **TU SISTEMA DE PUNTOS**\n\n"
            "Aún no tienes puntos acumulados.\n\n"
            "💡 **Cómo ganar puntos:**\n"
            "• 2 puntos por pago puntual\n"
            "• 5 puntos por pago adelantado\n"
            "• 7 puntos por referido verificado\n\n"
            "👥 **Para referir amigos usa:** /referidos"
        )
        conn.close()
        return
    
    puntos_totales, puntos_disponibles = puntos_result
    
    # Obtener historial reciente
    cursor.execute("""
        SELECT tipo, puntos, descripcion, fecha 
        FROM puntos_historial 
        WHERE user_id = %s 
        ORDER BY fecha DESC 
        LIMIT 10
    """, (user_id,))
    historial = cursor.fetchall()
    
    conn.close()
    
    mensaje = f"⭐ **TU SISTEMA DE PUNTOS**\n\n"
    mensaje += f"🏆 **Puntos totales:** {puntos_totales}\n"
    mensaje += f"💎 **Puntos disponibles:** {puntos_disponibles}\n\n"
    
    # Mostrar progreso hacia beneficios
    mensaje += "🎯 **TUS BENEFICIOS:**\n"
    if puntos_disponibles >= 200:
        mensaje += "✅ **200 puntos** - 15% descuento en todo 🛍️\n"
        mensaje += "✅ **100 puntos** - 1 semana gratis en gym 🏋️‍♂️\n"
    elif puntos_disponibles >= 100:
        mensaje += "✅ **100 puntos** - 1 semana gratis en gym 🏋️‍♂️\n"
        mensaje += f"⏳ **200 puntos** - 15% descuento ({puntos_disponibles}/200)\n"
    else:
        mensaje += f"⏳ **100 puntos** - 1 semana gratis ({puntos_disponibles}/100)\n"
        mensaje += f"⏳ **200 puntos** - 15% descuento ({puntos_disponibles}/200)\n"
    
    mensaje += f"\n📊 **HISTORIAL RECIENTE:**\n"
    
    if historial:
        for tipo, puntos, descripcion, fecha in historial:
            icono = "➕" if puntos > 0 else "➖"
            mensaje += f"{icono} **{puntos} pts** - {descripcion}\n"
            mensaje += f"   📅 {fecha.strftime('%d/%m/%Y %H:%M')}\n"
    else:
        mensaje += "📭 No hay historial de puntos\n"
    
    mensaje += f"\n💡 **Siguiente beneficio:** "
    if puntos_disponibles < 100:
        mensaje += f"{100 - puntos_disponibles} pts para 1 semana gratis"
    elif puntos_disponibles < 200:
        mensaje += f"{200 - puntos_disponibles} pts para 15% descuento"
    else:
        mensaje += "¡Tienes todos los beneficios!"
    
    keyboard = [
        [InlineKeyboardButton("👥 Referir amigos", callback_data="ir_a_referidos")],
        [InlineKeyboardButton("🔄 Actualizar", callback_data="actualizar_puntos")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(mensaje, reply_markup=reply_markup)

async def ranking_puntos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra el ranking de puntos (solo admin)"""
    if update.effective_user.id != 5908252094:
        await update.message.reply_text("❌ No tienes permisos de administrador")
        return
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Obtener ranking de puntos
    cursor.execute("""
        SELECT up.user_id, u.first_name, u.last_name, up.puntos_totales, up.puntos_disponibles
        FROM usuarios_puntos up
        LEFT JOIN usuarios u ON up.user_id = u.user_id
        ORDER BY up.puntos_disponibles DESC
        LIMIT 20
    """)
    ranking = cursor.fetchall()
    
    # Obtener estadísticas generales
    cursor.execute("SELECT COUNT(*) FROM usuarios_puntos")
    total_usuarios_puntos = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(puntos_disponibles) FROM usuarios_puntos")
    total_puntos = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(*) FROM referidos WHERE estado = 'aprobado'")
    referidos_aprobados = cursor.fetchone()[0]
    
    conn.close()
    
    mensaje = "🏆 **RANKING DE PUNTOS - ADMIN**\n\n"
    
    if ranking:
        posicion = 1
        for user_id, first_name, last_name, puntos_totales, puntos_disponibles in ranking:
            nombre_completo = f"{first_name or ''} {last_name or ''}".strip() or f"Usuario {user_id}"
            medalla = "🥇" if posicion == 1 else "🥈" if posicion == 2 else "🥉" if posicion == 3 else f"{posicion}."
            
            mensaje += f"{medalla} **{nombre_completo}**\n"
            mensaje += f"   🆔 ID: {user_id}\n"
            mensaje += f"   ⭐ Puntos: {puntos_disponibles} (Total: {puntos_totales})\n"
            mensaje += f"   ✏️ /asignar_{user_id}\n"
            mensaje += "━━━━━━━━━━━━━━━━━━━━\n\n"
            posicion += 1
    else:
        mensaje += "📭 No hay usuarios con puntos aún\n\n"
    
    mensaje += f"📊 **ESTADÍSTICAS GENERALES:**\n"
    mensaje += f"• 👥 Usuarios con puntos: {total_usuarios_puntos}\n"
    mensaje += f"• ⭐ Total puntos en sistema: {total_puntos}\n"
    mensaje += f"• 👥 Referidos aprobados: {referidos_aprobados}\n"
    mensaje += f"• 💰 Valor estimado: ${total_puntos * 0.1:.2f}\n\n"
    
    mensaje += "🛠️ **Acciones:**\n"
    mensaje += "/verreferidos - Ver todos los referidos pendientes\n"
    mensaje += "/verpuntosusuario_ID - Ver puntos de usuario específico"
    
    await update.message.reply_text(mensaje)

async def ver_referidos_pendientes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra todos los referidos pendientes de verificación (solo admin)"""
    if update.effective_user.id != 5908252094:
        await update.message.reply_text("❌ No tienes permisos de administrador")
        return
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT r.id, r.user_id_referidor, u1.first_name as nombre_referidor, 
               r.user_id_referido, u2.first_name as nombre_referido,
               r.nombre_referido, r.telefono_referido, r.fecha_registro
        FROM referidos r
        LEFT JOIN usuarios u1 ON r.user_id_referidor = u1.user_id
        LEFT JOIN usuarios u2 ON r.user_id_referido = u2.user_id
        WHERE r.estado = 'pendiente'
        ORDER BY r.fecha_registro DESC
    """)
    referidos_pendientes = cursor.fetchall()
    
    conn.close()
    
    if not referidos_pendientes:
        await update.message.reply_text("✅ No hay referidos pendientes de verificación")
        return
    
    mensaje = "📋 **REFERIDOS PENDIENTES - ADMIN**\n\n"
    
    for ref_id, user_id_ref, nombre_ref, user_id_referido, nombre_referido, nombre_ref_manual, telefono, fecha in referidos_pendientes:
        nombre_referidor = nombre_ref or f"Usuario {user_id_ref}"
        nombre_referido_final = nombre_referido or nombre_ref_manual or "No registrado"
        
        mensaje += f"🆔 **ID Referido:** {ref_id}\n"
        mensaje += f"👤 **Referidor:** {nombre_referidor} (ID: {user_id_ref})\n"
        mensaje += f"👥 **Referido:** {nombre_referido_final}\n"
        mensaje += f"📱 **Teléfono:** {telefono or 'No proporcionado'}\n"
        mensaje += f"📅 **Fecha:** {fecha.strftime('%d/%m/%Y %H:%M')}\n"
        
        if user_id_referido:
            mensaje += f"✅ **Usuario registrado en sistema**\n"
        else:
            mensaje += f"⚠️ **Usuario NO registrado en sistema**\n"
        
        mensaje += f"✅ /verificarreferido_{ref_id} | ❌ /rechazarreferido_{ref_id}\n"
        mensaje += "━━━━━━━━━━━━━━━━━━━━\n\n"
    
    await update.message.reply_text(mensaje)

async def verificar_referido(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Verifica un referido pendiente (solo admin)"""
    if update.effective_user.id != 5908252094:
        await update.message.reply_text("❌ No tienes permisos de administrador")
        return

    command_text = update.message.text
    try:
        referido_id = command_text.split('_')[1]
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Obtener información del referido
        cursor.execute("""
            SELECT user_id_referidor, user_id_referido, nombre_referido
            FROM referidos 
            WHERE id = %s AND estado = 'pendiente'
        """, (referido_id,))
        referido = cursor.fetchone()
        
        if not referido:
            await update.message.reply_text("❌ Referido no encontrado o ya verificado")
            conn.close()
            return
        
        user_id_referidor, user_id_referido, nombre_referido = referido
        
        # Actualizar estado del referido
        cursor.execute("UPDATE referidos SET estado = 'aprobado' WHERE id = %s", (referido_id,))
        
        # Otorgar puntos al referidor
        puntos_otorgados = 7
        descripcion = f"Referido aprobado: {nombre_referido}"
        
        # Usar la función agregar_puntos
        success = await agregar_puntos(user_id_referidor, puntos_otorgados, "referido", descripcion)
        
        if success:
            # Marcar como puntos otorgados
            cursor.execute("UPDATE referidos SET puntos_otorgados = TRUE WHERE id = %s", (referido_id,))
        
        conn.commit()
        conn.close()
        
        # Notificar al referidor
        try:
            await context.bot.send_message(
                chat_id=user_id_referidor,
                text=f"🎉 **¡REFERIDO APROBADO!**\n\n"
                     f"Tu referido **{nombre_referido}** ha sido aprobado.\n\n"
                     f"⭐ **+7 puntos** han sido agregados a tu cuenta.\n"
                     f"🏆 **Total de puntos:** (Ver en /mispuntos)\n\n"
                     f"¡Sigue invitando amigos para ganar más puntos!"
            )
        except Exception as e:
            print(f"❌ No se pudo notificar al referidor: {e}")
        
        await update.message.reply_text(
            f"✅ **Referido aprobado exitosamente**\n\n"
            f"👤 **Referidor:** {user_id_referidor}\n"
            f"👥 **Referido:** {nombre_referido}\n"
            f"⭐ **Puntos otorgados:** 7\n\n"
            f"El referidor ha sido notificado."
        )
        
    except Exception as e:
        print(f"❌ Error al verificar referido: {e}")
        await update.message.reply_text("❌ Error al verificar el referido")

async def rechazar_referido(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Rechaza un referido pendiente (solo admin)"""
    if update.effective_user.id != 5908252094:
        await update.message.reply_text("❌ No tienes permisos de administrador")
        return

    command_text = update.message.text
    try:
        referido_id = command_text.split('_')[1]
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Obtener información del referido
        cursor.execute("""
            SELECT user_id_referidor, nombre_referido
            FROM referidos 
            WHERE id = %s AND estado = 'pendiente'
        """, (referido_id,))
        referido = cursor.fetchone()
        
        if not referido:
            await update.message.reply_text("❌ Referido no encontrado o ya procesado")
            conn.close()
            return
        
        user_id_referidor, nombre_referido = referido
        
        # Actualizar estado del referido a rechazado
        cursor.execute("UPDATE referidos SET estado = 'rechazado' WHERE id = %s", (referido_id,))
        conn.commit()
        conn.close()
        
        # Notificar al referidor
        try:
            await context.bot.send_message(
                chat_id=user_id_referidor,
                text=f"❌ **REFERIDO RECHAZADO**\n\n"
                     f"Tu referido **{nombre_referido}** ha sido rechazado.\n\n"
                     f"💡 **Posibles razones:**\n"
                     f"• El usuario no se registró correctamente\n"
                     f"• Información incompleta o incorrecta\n"
                     f"• Ya estaba registrado en el sistema\n\n"
                     f"Puedes intentar con otro referido usando /referidos"
            )
        except Exception as e:
            print(f"❌ No se pudo notificar al referidor: {e}")
        
        await update.message.reply_text(
            f"✅ **Referido rechazado**\n\n"
            f"👤 **Referidor:** {user_id_referidor}\n"
            f"👥 **Referido:** {nombre_referido}\n\n"
            f"El referidor ha sido notificado."
        )
        
    except Exception as e:
        print(f"❌ Error al rechazar referido: {e}")
        await update.message.reply_text("❌ Error al rechazar el referido")
        
        
        
        # =============================================
# 🆕 FUNCIÓN PARA VACIAR RANKING DE PUNTOS
# =============================================

async def vaciar_ranking_puntos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Vacía/limpia todo el sistema de puntos (solo admin)"""
    if update.effective_user.id != 5908252094:
        await update.message.reply_text("❌ No tienes permisos de administrador")
        return

    # Crear teclado de confirmación
    keyboard = [
        [InlineKeyboardButton("✅ SÍ, VACIAR TODO", callback_data="vaciar_puntos_si")],
        [InlineKeyboardButton("❌ CANCELAR", callback_data="vaciar_puntos_no")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Obtener estadísticas actuales
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM usuarios_puntos")
    total_usuarios = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(puntos_totales) FROM usuarios_puntos")
    total_puntos = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(*) FROM puntos_historial")
    total_historial = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM referidos")
    total_referidos = cursor.fetchone()[0]
    
    conn.close()
    
    mensaje = (
        "🗑️ **VACIAR SISTEMA DE PUNTOS - CONFIRMACIÓN**\n\n"
        "⚠️ **ESTA ACCIÓN ELIMINARÁ:**\n"
        f"• 👥 {total_usuarios} usuarios de la tabla de puntos\n"
        f"• ⭐ {total_puntos} puntos totales en el sistema\n"
        f"• 📊 {total_historial} registros del historial de puntos\n"
        f"• 👥 {total_referidos} registros de referidos\n\n"
        "❌ **ESTA ACCIÓN NO SE PUEDE DESHACER**\n\n"
        "¿Estás completamente seguro de vaciar todo el sistema de puntos?"
    )
    
    await update.message.reply_text(mensaje, reply_markup=reply_markup)

async def ver_puntos_usuario(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ver puntos de un usuario específico (solo admin)"""
    if update.effective_user.id != 5908252094:
        await update.message.reply_text("❌ No tienes permisos de administrador")
        return

    command_text = update.message.text
    try:
        user_id = command_text.split('_')[1]
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Obtener información del usuario
        cursor.execute("SELECT first_name, last_name FROM usuarios WHERE user_id = %s", (user_id,))
        usuario = cursor.fetchone()
        
        if not usuario:
            await update.message.reply_text("❌ Usuario no encontrado")
            conn.close()
            return
        
        first_name, last_name = usuario
        nombre_completo = f"{first_name or ''} {last_name or ''}".strip()
        
        # Obtener puntos del usuario
        cursor.execute("""
            SELECT puntos_totales, puntos_disponibles, fecha_actualizacion
            FROM usuarios_puntos 
            WHERE user_id = %s
        """, (user_id,))
        puntos = cursor.fetchone()
        
        # Obtener historial de puntos
        cursor.execute("""
            SELECT tipo, puntos, descripcion, fecha
            FROM puntos_historial
            WHERE user_id = %s
            ORDER BY fecha DESC
            LIMIT 10
        """, (user_id,))
        historial = cursor.fetchall()
        
        # Obtener referidos del usuario
        cursor.execute("""
            SELECT COUNT(*) FROM referidos 
            WHERE user_id_referidor = %s AND estado = 'aprobado'
        """, (user_id,))
        referidos_aprobados = cursor.fetchone()[0]
        
        conn.close()
        
        mensaje = f"⭐ **PUNTOS DE USUARIO - ADMIN**\n\n"
        mensaje += f"👤 **Usuario:** {nombre_completo}\n"
        mensaje += f"🆔 **ID:** {user_id}\n\n"
        
        if puntos:
            puntos_totales, puntos_disponibles, fecha_actualizacion = puntos
            mensaje += f"🏆 **Puntos totales:** {puntos_totales}\n"
            mensaje += f"💎 **Puntos disponibles:** {puntos_disponibles}\n"
            mensaje += f"📅 **Última actualización:** {fecha_actualizacion.strftime('%d/%m/%Y %H:%M')}\n"
            mensaje += f"👥 **Referidos aprobados:** {referidos_aprobados}\n\n"
        else:
            mensaje += "📭 **El usuario no tiene puntos aún**\n\n"
        
        if historial:
            mensaje += "📊 **HISTORIAL RECIENTE:**\n"
            for tipo, puntos_mov, descripcion, fecha in historial:
                icono = "➕" if puntos_mov > 0 else "➖"
                mensaje += f"{icono} **{puntos_mov} pts** - {descripcion}\n"
                mensaje += f"   📅 {fecha.strftime('%d/%m/%Y %H:%M')}\n"
        else:
            mensaje += "📭 **No hay historial de puntos**\n"
        
        await update.message.reply_text(mensaje)
        
    except Exception as e:
        print(f"❌ Error al ver puntos de usuario: {e}")
        await update.message.reply_text("❌ Error al obtener información del usuario")

# =============================================
# 🆕 SISTEMA DE INCREMENTO DE SEMANAS
# =============================================

async def incrementar_semanas_automatico(context: ContextTypes.DEFAULT_TYPE):
    """Incrementa semanas automáticamente respetando la configuración del admin"""
    print(f"🔄 [{datetime.now().strftime('%Y-%m-%d %H:%M')}] Verificando incremento automático...")
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 1. Verificar configuración global
        cursor.execute("SELECT semanas, contador_activo FROM config_pagos LIMIT 1")
        config = cursor.fetchone()
        
        if not config:
            print("❌ No se encontró configuración")
            conn.close()
            return
            
        semanas_config, contador_activo = config
        
        if not contador_activo:
            print("⏸️ Contador global PAUSADO por admin - No se incrementan semanas")
            conn.close()
            return
        
        # 2. Incrementar planes activos no pausados individualmente
        cursor.execute("""
            UPDATE planes_pago 
            SET semanas_completadas = semanas_completadas + 1,
                fecha_ultimo_pago = CURRENT_TIMESTAMP
            WHERE estado = 'activo' 
            AND contador_pausado = FALSE
            AND semanas_completadas < semanas
        """)
        planes_afectados = cursor.rowcount
        
        # 3. Verificar planes completados
        cursor.execute("""
            SELECT user_id, semanas_completadas, semanas 
            FROM planes_pago 
            WHERE estado = 'activo' 
            AND semanas_completadas >= semanas
            AND contador_pausado = FALSE
        """)
        planes_completados = cursor.fetchall()
        
        conn.commit()
        conn.close()
        
        # 4. Logs y notificaciones
        if planes_afectados > 0:
            print(f"✅ {planes_afectados} planes incrementados +1 semana (Config: {semanas_config} semanas)")
            
            # Notificar usuarios
            for user_id, semanas_comp, semanas_tot in planes_completados:
                try:
                    if semanas_comp == semanas_tot:
                        # Plan completado
                        await context.bot.send_message(
                            chat_id=user_id,
                            text="🎉 **¡FELICITACIONES!**\n\n"
                                 "✅ **HAS COMPLETADO TU PLAN DE PAGO**\n\n"
                                 f"Has terminado las {semanas_tot} semanas de tu plan.\n\n"
                                 "📞 Contacta al administrador para finalizar el proceso."
                        )
                    else:
                        # Semana normal
                        await context.bot.send_message(
                            chat_id=user_id,
                            text="📅 **AVANCE AUTOMÁTICO**\n\n"
                                 f"✅ Tu plan ha avanzado a la semana {semanas_comp}/{semanas_tot}\n\n"
                                 "💳 Recuerda realizar tu pago semanal.\n"
                                 "📋 Ver progreso: /misplanes"
                        )
                except Exception as e:
                    print(f"❌ No se pudo notificar a usuario {user_id}: {e}")
        else:
            print("📭 No hay planes para incrementar esta semana")
            
    except Exception as e:
        print(f"❌ Error en incremento automático: {e}")

async def incrementar_semana_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Incrementa una semana manualmente respetando la configuración"""
    if update.effective_user.id != 5908252094:
        await update.message.reply_text("❌ No tienes permisos de administrador")
        return

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Verificar configuración
        cursor.execute("SELECT semanas, contador_activo FROM config_pagos LIMIT 1")
        config = cursor.fetchone()
        
        if not config:
            await update.message.reply_text("❌ Error: No se encontró configuración")
            conn.close()
            return
            
        semanas_config, contador_activo = config
        
        if not contador_activo:
            keyboard = [
                [InlineKeyboardButton("✅ REANUDAR CONTADOR", callback_data="reanudar_y_incrementar")],
                [InlineKeyboardButton("❌ SOLO INCREMENTAR", callback_data="incrementar_force")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "⚠️ **CONTADOR PAUSADO**\n\n"
                "El contador global está pausado. ¿Qué deseas hacer?\n\n"
                "✅ **Reanudar contador**: Activa el contador e incrementa\n"
                "❌ **Solo incrementar**: Incrementa sin reanudar el contador automático",
                reply_markup=reply_markup
            )
            conn.close()
            return
        
        # Incrementar semanas
        cursor.execute("""
            UPDATE planes_pago 
            SET semanas_completadas = semanas_completadas + 1,
                fecha_ultimo_pago = CURRENT_TIMESTAMP
            WHERE estado = 'activo' 
            AND contador_pausado = FALSE
            AND semanas_completadas < semanas
        """)
        planes_afectados = cursor.rowcount
        
        # Obtener estadísticas
        cursor.execute("SELECT COUNT(*) FROM planes_pago WHERE estado = 'activo'")
        total_planes = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM planes_pago WHERE contador_pausado = TRUE AND estado = 'activo'")
        planes_pausados = cursor.fetchone()[0]
        
        conn.commit()
        conn.close()
        
        await update.message.reply_text(
            f"✅ **Semana incrementada manualmente**\n\n"
            f"📊 **Estadísticas:**\n"
            f"• 📈 Planes afectados: {planes_afectados}\n"
            f"• 📋 Total planes activos: {total_planes}\n"
            f"• ⏸️ Planes pausados: {planes_pausados}\n"
            f"• 🔢 Semanas configuradas: {semanas_config}\n\n"
            f"Los usuarios han sido notificados automáticamente."
        )
        
        # Notificar usuarios
        if planes_afectados > 0:
            await notificar_usuarios_incremento(context, "manual")
                    
    except Exception as e:
        print(f"❌ Error en incremento manual: {e}")
        await update.message.reply_text("❌ Error al incrementar semanas")

async def forzar_incremento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fuerza el incremento de semana ignorando el estado de pausa"""
    if update.effective_user.id != 5908252094:
        await update.message.reply_text("❌ No tienes permisos de administrador")
        return

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT semanas FROM config_pagos LIMIT 1")
        config = cursor.fetchone()
        semanas_config = config[0] if config else 10
        
        # Incrementar IGNORANDO el estado de pausa
        cursor.execute("""
            UPDATE planes_pago 
            SET semanas_completadas = semanas_completadas + 1,
                fecha_ultimo_pago = CURRENT_TIMESTAMP
            WHERE estado = 'activo' 
            AND semanas_completadas < semanas
        """)
        planes_afectados = cursor.rowcount
        
        conn.commit()
        conn.close()
        
        await update.message.reply_text(
            f"🚀 **INCREMENTO FORZADO**\n\n"
            f"✅ {planes_afectados} planes incrementados +1 semana\n"
            f"🔢 Configuración: {semanas_config} semanas\n"
            f"⚠️ Se ignoró el estado de pausa del contador"
        )
        
        # Notificar usuarios
        await notificar_usuarios_incremento(context, "forzado")
                    
    except Exception as e:
        print(f"❌ Error en incremento forzado: {e}")
        await update.message.reply_text("❌ Error al forzar incremento")

async def notificar_usuarios_incremento(context: ContextTypes.DEFAULT_TYPE, tipo: str):
    """Notifica a los usuarios sobre el incremento de semanas"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT user_id, semanas_completadas, semanas 
            FROM planes_pago 
            WHERE estado = 'activo' 
            AND contador_pausado = FALSE
        """)
        planes = cursor.fetchall()
        
        for user_id, semanas_comp, semanas_tot in planes:
            try:
                if semanas_comp >= semanas_tot:
                    # Plan completado
                    await context.bot.send_message(
                        chat_id=user_id,
                        text="🎉 **¡PLAN COMPLETADO!**\n\n"
                             f"✅ Has terminado las {semanas_tot} semanas.\n\n"
                             "📞 Contacta al administrador."
                    )
                else:
                    # Avance normal
                    mensaje = "📅 **AVANCE DE SEMANA**\n\n" if tipo == "manual" else "📅 **AVANCE AUTOMÁTICO**\n\n"
                    mensaje += f"✅ Tu plan ha avanzado a la semana {semanas_comp}/{semanas_tot}\n\n"
                    mensaje += "💳 Recuerda realizar tu pago semanal.\n"
                    mensaje += "📋 Ver progreso: /misplanes"
                    
                    await context.bot.send_message(chat_id=user_id, text=mensaje)
            except Exception as e:
                print(f"❌ No se pudo notificar a usuario {user_id}: {e}")
        
        conn.close()
    except Exception as e:
        print(f"❌ Error en notificación: {e}")
# =============================================
# 🆕 MODIFICACIONES A FUNCIONES EXISTENTES
# =============================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando start para registro de usuarios - ACTUALIZADO CON SISTEMA DE REFERIDOS"""
    user_id = update.effective_user.id
    user_name = update.effective_user.username
    first_name = update.effective_user.first_name
    last_name = update.effective_user.last_name
    
    # Verificar si hay código de referido en el mensaje
    args = context.args
    codigo_referido = args[0] if args else None
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Verificar si el usuario ya existe
    cursor.execute("SELECT * FROM usuarios WHERE user_id = %s", (user_id,))
    usuario_existente = cursor.fetchone()
    
    if usuario_existente:
        conn.close()
        await update.message.reply_text(
            f"👋 ¡Hola de nuevo {first_name}!\n\n"
            f"Ya estás registrado en el sistema.\n\n"
            f"🛍️ Ver catálogo: /catalogo\n"
            f"📋 Mi plan: /misplanes\n"
            f"👤 Mi perfil: /miperfil\n"
            f"⭐ Mis puntos: /mispuntos\n"
            f"👥 Referidos: /referidos\n"
            f"💳 Registrar pago: /pagarealizado"
        )
    else:
        # Proceso de registro nuevo
        context.user_data['registrando_usuario'] = True
        context.user_data['datos_usuario'] = {
            'user_id': user_id,
            'user_name': user_name,
            'first_name': first_name,
            'last_name': last_name,
            'codigo_referido': codigo_referido  # 🆕 Guardar código de referido
        }
        conn.close()
        
        keyboard = [
            [InlineKeyboardButton("📱 Compartir teléfono", callback_data="compartir_telefono")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        mensaje_bienvenida = f"👋 ¡Hola {first_name}!\n\nTe damos la bienvenida al sistema de planes de pago semanal."
        
        # 🆕 Informar sobre código de referido si existe
        if codigo_referido:
            mensaje_bienvenida += f"\n\n🔗 Código de referido detectado: {codigo_referido}"
            # Intentar obtener información del referidor
            try:
                if codigo_referido.startswith('REF'):
                    referidor_id = int(codigo_referido[3:])
                    conn_temp = get_db_connection()
                    cursor_temp = conn_temp.cursor()
                    cursor_temp.execute("SELECT first_name FROM usuarios WHERE user_id = %s", (referidor_id,))
                    referidor = cursor_temp.fetchone()
                    conn_temp.close()
                    
                    if referidor:
                        mensaje_bienvenida += f"\nTe está refiriendo: {referidor[0]}"
            except:
                pass
        
        mensaje_bienvenida += "\n\nPara completar tu registro, necesitamos tu número de teléfono:"
        
        await update.message.reply_text(mensaje_bienvenida, reply_markup=reply_markup)

async def handle_phone_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja el registro del teléfono del usuario - ACTUALIZADO CON SISTEMA DE REFERIDOS"""
    if not context.user_data.get('registrando_usuario'):
        return
    
    # Si el usuario presionó el botón de compartir teléfono
    if update.message.contact:
        phone = update.message.contact.phone_number
    else:
        # Si el usuario escribió el teléfono manualmente
        phone = update.message.text.strip()
    
    datos_usuario = context.user_data['datos_usuario']
    codigo_referido = datos_usuario.get('codigo_referido')
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Registrar usuario
        cursor.execute(
            "INSERT INTO usuarios (user_id, user_name, first_name, last_name, phone) VALUES (%s, %s, %s, %s, %s)",
            (datos_usuario['user_id'], datos_usuario['user_name'], datos_usuario['first_name'], 
             datos_usuario['last_name'], phone)
        )
        
        # 🆕 Procesar referido si existe código
        if codigo_referido and codigo_referido.startswith('REF'):
            try:
                referidor_id = int(codigo_referido[3:])
                
                # Verificar que el referidor existe
                cursor.execute("SELECT first_name FROM usuarios WHERE user_id = %s", (referidor_id,))
                referidor = cursor.fetchone()
                
                if referidor:
                    # Registrar referido
                    cursor.execute("""
                        INSERT INTO referidos (user_id_referidor, user_id_referido, nombre_referido, telefono_referido)
                        VALUES (%s, %s, %s, %s)
                    """, (referidor_id, datos_usuario['user_id'], datos_usuario['first_name'], phone))
                    
                    print(f"✅ Referido registrado: {referidor_id} -> {datos_usuario['user_id']}")
            except Exception as e:
                print(f"❌ Error al procesar referido: {e}")
        
        conn.commit()
        conn.close()
        
        context.user_data['registrando_usuario'] = False
        context.user_data['datos_usuario'] = None
        
        mensaje_exito = (
            f"✅ **¡Registro completado!** 🎉\n\n"
            f"👤 **Usuario:** {datos_usuario['first_name']} {datos_usuario['last_name'] or ''}\n"
            f"📱 **Teléfono:** {phone}\n"
        )
        
        # 🆕 Informar sobre referido
        if codigo_referido:
            mensaje_exito += f"🔗 **Código referido:** {codigo_referido}\n"
            mensaje_exito += "📋 Tu referido será verificado por el administrador.\n"
        
        mensaje_exito += (
            f"\n🛍️ **Comienza a explorar:**\n"
            f"/catalogo - Ver productos disponibles\n"
            f"/misplanes - Tu plan asignado\n"
            f"/miperfil - Tu información\n"
            f"/mispuntos - Tu sistema de puntos\n"
            f"/referidos - Invitar amigos\n\n"
            f"¡Gracias por registrarte! 🎊"
        )
        
        await update.message.reply_text(mensaje_exito)
        
    except Exception as e:
        print(f"❌ Error en registro: {e}")
        await update.message.reply_text("❌ Error en el registro. Intenta nuevamente.")

async def miperfil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra el perfil del usuario - ACTUALIZADO CON PUNTOS"""
    user_id = update.effective_user.id
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT first_name, last_name, user_name, phone, fecha_registro FROM usuarios WHERE user_id = %s", (user_id,))
    usuario = cursor.fetchone()
    
    if not usuario:
        await update.message.reply_text("❌ Debes registrarte con /start primero")
        conn.close()
        return
    
    first_name, last_name, user_name, phone, fecha_registro = usuario
    
    # Contar planes activos
    cursor.execute("SELECT COUNT(*) FROM planes_pago WHERE user_id = %s AND estado = 'activo'", (user_id,))
    planes_activos = cursor.fetchone()[0]
    
    # Contar pagos realizados
    cursor.execute("SELECT COUNT(*) FROM pagos WHERE user_id = %s", (user_id,))
    total_pagos = cursor.fetchone()[0]
    
    # 🆕 Obtener puntos
    cursor.execute("SELECT puntos_disponibles FROM usuarios_puntos WHERE user_id = %s", (user_id,))
    puntos_result = cursor.fetchone()
    puntos_actuales = puntos_result[0] if puntos_result else 0
    
    # 🆕 Contar referidos aprobados
    cursor.execute("SELECT COUNT(*) FROM referidos WHERE user_id_referidor = %s AND estado = 'aprobado'", (user_id,))
    referidos_aprobados = cursor.fetchone()[0]
    
    conn.close()
    
    mensaje = (
        f"👤 **TU PERFIL**\n\n"
        f"🆔 **ID:** {user_id}\n"
        f"👨‍💼 **Nombre:** {first_name} {last_name or ''}\n"
        f"📱 **Teléfono:** {phone or 'No registrado'}\n"
        f"📅 **Fecha registro:** {fecha_registro.strftime('%d/%m/%Y')}\n\n"
        f"📊 **Estadísticas:**\n"
        f"• 📋 Planes activos: {planes_activos}\n"
        f"• 💳 Pagos realizados: {total_pagos}\n"
        f"• ⭐ Puntos acumulados: {puntos_actuales}\n"
        f"• 👥 Referidos aprobados: {referidos_aprobados}\n\n"
        f"🛍️ **Acciones:**\n"
        f"/catalogo - Ver productos\n"
        f"/misplanes - Mi plan\n"
        f"/mispuntos - Mis puntos\n"
        f"/referidos - Invitar amigos\n"
        f"/pagarealizado - Registrar pago"
    )
    
    await update.message.reply_text(mensaje)

async def confirmar_pago(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirma un pago pendiente (admin) - ACTUALIZADO CON SISTEMA DE PUNTOS"""
    if update.effective_user.id != 5908252094:
        await update.message.reply_text("❌ No tienes permisos de administrador")
        return

    command_text = update.message.text
    try:
        pago_id = command_text.split('_')[1]
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Obtener información del pago
        cursor.execute("SELECT user_id, monto, fecha FROM pagos WHERE id = %s", (pago_id,))
        pago_info = cursor.fetchone()
        
        if not pago_info:
            await update.message.reply_text("❌ Pago no encontrado")
            conn.close()
            return
        
        user_id, monto, fecha_pago = pago_info
        
        # Actualizar estado del pago
        cursor.execute("UPDATE pagos SET estado = 'aprobado' WHERE id = %s", (pago_id,))
        
        # 🆕 CALCULAR PUNTOS POR PAGO
        puntos_otorgados = 0
        descripcion_puntos = ""
        
        # Verificar si es pago adelantado (más de 7 días antes del incremento automático)
        fecha_actual = datetime.now()
        dias_restantes = (fecha_actual - fecha_pago).days
        
        if dias_restantes >= 7:
            puntos_otorgados = 5
            descripcion_puntos = f"Pago adelantado - ${monto:.2f}"
        else:
            puntos_otorgados = 2
            descripcion_puntos = f"Pago puntual - ${monto:.2f}"
        
        # Otorgar puntos
        if puntos_otorgados > 0:
            success = await agregar_puntos(user_id, puntos_otorgados, "pago", descripcion_puntos)
            if success:
                print(f"✅ {puntos_otorgados} puntos otorgados a usuario {user_id} por pago {pago_id}")
        
        conn.commit()
        conn.close()
        
        # Notificar al usuario
        try:
            mensaje_usuario = (
                f"✅ **¡Tu pago ha sido aprobado!**\n\n"
                f"💰 **Monto:** ${monto:.2f}\n"
                f"📅 **Fecha pago:** {fecha_pago.strftime('%d/%m/%Y')}\n"
            )
            
            if puntos_otorgados > 0:
                mensaje_usuario += f"⭐ **+{puntos_otorgados} puntos** agregados a tu cuenta\n\n"
            
            mensaje_usuario += (
                f"Puedes ver el estado actualizado con /mistatus\n"
                f"Ver tus puntos con /mispuntos"
            )
            
            await context.bot.send_message(chat_id=user_id, text=mensaje_usuario)
            
            # 🆕 Verificar si alcanzó algún beneficio
            await verificar_beneficios_puntos(user_id)
            
        except Exception as e:
            print(f"❌ No se pudo notificar al usuario: {e}")
        
        mensaje_admin = f"✅ Pago aprobado y usuario notificado"
        if puntos_otorgados > 0:
            mensaje_admin += f" (+{puntos_otorgados} puntos otorgados)"
        
        await update.message.reply_text(mensaje_admin)
        
    except Exception as e:
        print(f"❌ Error en confirmar_pago: {e}")
        await update.message.reply_text("❌ Error al confirmar el pago")

# =============================================
# 🆕 MANEJO DE BOTONES PARA SISTEMA DE PUNTOS
# =============================================

async def button_handler_puntos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja los botones del sistema de puntos"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    print(f"🟡 BOTÓN PUNTOS: {data}")
    
    if data == "compartir_codigo":
        # Crear código de referido
        codigo_referido = f"REF{user_id}"
        
        mensaje_compartir = (
            f"📤 **COMPARTIR CÓDIGO DE REFERIDO**\n\n"
            f"¡Invita a tus amigos y gana puntos!\n\n"
            f"🔗 **Tu código:** `{codigo_referido}`\n\n"
            f"📋 **Cómo funciona:**\n"
            f"1. Comparte este código con amigos\n"
            f"2. Ellos deben usar /start {codigo_referido}\n"
            f"3. El admin verificará el registro\n"
            f"4. ¡Ganas 7 puntos por cada amigo!\n\n"
            f"💬 **Mensaje para compartir:**\n"
            f"¡Únete al sistema de planes de pago! Usa mi código {codigo_referido} al registrarte con /start y ambos ganamos beneficios."
        )
        
        await query.edit_message_text(mensaje_compartir)
        
    elif data == "ver_mis_puntos":
        await mispuntos(update, context)
        
    elif data == "ir_a_referidos":
        await referidos(update, context)
        
    elif data == "actualizar_puntos":
        await mispuntos(update, context)

# =============================================
# 🆕 SISTEMA DE ASIGNACIÓN ADMINISTRATIVA
# =============================================

async def asignar_productos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Asignar productos a usuario (solo admin)"""
    if update.effective_user.id != 5908252094:
        await update.message.reply_text("❌ No tienes permisos de administrador")
        return

    command_text = update.message.text
    try:
        user_id = command_text.split('_')[1]
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Obtener información del usuario
        cursor.execute("SELECT first_name, last_name FROM usuarios WHERE user_id = %s", (user_id,))
        usuario = cursor.fetchone()
        
        if not usuario:
            await update.message.reply_text("❌ Usuario no encontrado")
            conn.close()
            return
            
        first_name, last_name = usuario
        nombre_completo = f"{first_name or ''} {last_name or ''}".strip()
        
        # Obtener productos activos
        cursor.execute("SELECT id, nombre, precio, descripcion FROM productos WHERE estado = 'activo' ORDER BY nombre")
        productos = cursor.fetchall()
        
        # Obtener plan actual del usuario (si existe)
        cursor.execute("SELECT productos_json FROM planes_pago WHERE user_id = %s AND estado = 'activo'", (user_id,))
        plan_actual = cursor.fetchone()
        
        productos_actuales = {}
        if plan_actual and plan_actual[0]:
            productos_actuales = plan_actual[0] if isinstance(plan_actual[0], dict) else json.loads(plan_actual[0])
        
        # Obtener configuración de semanas ANTES de cerrar la conexión
        cursor.execute("SELECT semanas FROM config_pagos LIMIT 1")
        config = cursor.fetchone()
        semanas = config[0] if config else 10
        
        conn.close()  # ✅ Cerrar conexión aquí, después de obtener TODOS los datos
        
        if not productos:
            await update.message.reply_text("❌ No hay productos disponibles en el catálogo")
            return
        
        # Crear interfaz de asignación
        mensaje = f"🛍️ **ASIGNAR PRODUCTOS A USUARIO**\n\n"
        mensaje += f"👤 **Usuario:** {nombre_completo}\n"
        mensaje += f"🆔 **ID:** {user_id}\n\n"
        mensaje += "📦 **PRODUCTOS DISPONIBLES:**\n\n"
        
        keyboard = []
        
        for producto_id, nombre, precio, descripcion in productos:
            cantidad_actual = productos_actuales.get(str(producto_id), 0)
            mensaje += f"📦 **{nombre}** - ${precio:.2f}\n"
            mensaje += f"   📝 {descripcion or 'Sin descripción'}\n"
            mensaje += f"   🔢 Cantidad actual: {cantidad_actual}\n"
            
            # Botones para ajustar cantidad
            row = [
                InlineKeyboardButton(f"➖ {nombre[:15]}...", callback_data=f"asignar_menos_{user_id}_{producto_id}"),
                InlineKeyboardButton(f"➕ {nombre[:15]}...", callback_data=f"asignar_mas_{user_id}_{producto_id}")
            ]
            keyboard.append(row)
        
        # Botones de control
        keyboard.append([InlineKeyboardButton("✅ CONFIRMAR ASIGNACIÓN", callback_data=f"asignar_confirmar_{user_id}")])
        keyboard.append([InlineKeyboardButton("🔄 REINICIAR", callback_data=f"asignar_reiniciar_{user_id}")])
        keyboard.append([InlineKeyboardButton("❌ CANCELAR", callback_data=f"asignar_cancelar")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Calcular resumen actual
        total_actual = 0
        for producto_id, cantidad in productos_actuales.items():
            for prod_id, nombre, precio, desc in productos:
                if str(prod_id) == producto_id:
                    total_actual += precio * cantidad
                    break
        
        pago_semanal_actual = total_actual / semanas if semanas > 0 else 0
        
        mensaje += f"\n📊 **RESUMEN ACTUAL:**\n"
        mensaje += f"💰 **Total:** ${total_actual:.2f}\n"
        mensaje += f"📅 **Pago semanal:** ${pago_semanal_actual:.2f}\n"
        mensaje += f"🔢 **Semanas:** {semanas}\n"
        
        await update.message.reply_text(mensaje, reply_markup=reply_markup)
        
    except Exception as e:
        print(f"❌ Error en asignar_productos: {e}")
        await update.message.reply_text("❌ Error al procesar la asignación")

async def ver_asignaciones(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ver todas las asignaciones activas (solo admin)"""
    if update.effective_user.id != 5908252094:
        await update.message.reply_text("❌ No tienes permisos de administrador")
        return
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Obtener todas las asignaciones activas
    cursor.execute("""
        SELECT p.user_id, u.first_name, u.last_name, p.productos_json, p.total, p.pago_semanal, p.semanas_completadas, p.semanas
        FROM planes_pago p
        LEFT JOIN usuarios u ON p.user_id = u.user_id
        WHERE p.estado = 'activo'
        ORDER BY u.first_name
    """)
    asignaciones = cursor.fetchall()
    
    # Obtener configuración
    cursor.execute("SELECT semanas FROM config_pagos LIMIT 1")
    config = cursor.fetchone()
    semanas_config = config[0] if config else 10
    
    conn.close()
    
    if not asignaciones:
        await update.message.reply_text("📭 No hay asignaciones activas en el sistema")
        return
    
    # Calcular totales generales
    total_general = 0
    pago_semanal_total = 0
    
    mensaje = "📊 **ASIGNACIONES ACTIVAS - ADMIN**\n\n"
    
    for user_id, first_name, last_name, productos_json, total, pago_semanal, semanas_comp, semanas in asignaciones:
        nombre_completo = f"{first_name or ''} {last_name or ''}".strip()
        
        total_general += total
        pago_semanal_total += pago_semanal
        
        mensaje += f"👤 **{nombre_completo}** (ID: {user_id})\n"
        
        # Mostrar productos asignados
        if productos_json:
            productos = productos_json if isinstance(productos_json, dict) else json.loads(productos_json)
            for producto_id, cantidad in productos.items():
                # Obtener nombre del producto
                conn_temp = get_db_connection()
                cursor_temp = conn_temp.cursor()
                cursor_temp.execute("SELECT nombre, precio FROM productos WHERE id = %s", (int(producto_id),))
                producto_info = cursor_temp.fetchone()
                conn_temp.close()
                
                if producto_info:
                    nombre_producto, precio_producto = producto_info
                    mensaje += f"   🛍️ {nombre_producto} x{cantidad} - ${precio_producto * cantidad:.2f}\n"
        
        mensaje += f"   💰 **Total:** ${total:.2f}\n"
        mensaje += f"   💳 **Pago semanal:** ${pago_semanal:.2f}\n"
        mensaje += f"   📅 **Progreso:** {semanas_comp}/{semanas} semanas\n"
        mensaje += f"   ✏️ /asignar_{user_id}\n"
        mensaje += "━━━━━━━━━━━━━━━━━━━━\n\n"
    
    # Estadísticas generales
    total_usuarios = len(asignaciones)
    promedio_usuario = total_general / total_usuarios if total_usuarios > 0 else 0
    
    mensaje += f"📈 **ESTADÍSTICAS GENERALES:**\n"
    mensaje += f"👥 **Usuarios activos:** {total_usuarios}\n"
    mensaje += f"💰 **Total general:** ${total_general:.2f}\n"
    mensaje += f"💳 **Pago semanal total:** ${pago_semanal_total:.2f}\n"
    mensaje += f"📊 **Promedio por usuario:** ${promedio_usuario:.2f}\n"
    mensaje += f"🔢 **Semanas configuradas:** {semanas_config}"
    
    await update.message.reply_text(mensaje)

async def mis_planes_mejorado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ver planes de pago activos del usuario (VERSIÓN MEJORADA)"""
    user_id = update.effective_user.id
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, productos_json, total, semanas, pago_semanal, semanas_completadas, fecha_inicio, contador_pausado
        FROM planes_pago 
        WHERE user_id = %s AND estado = 'activo'
        ORDER BY fecha_inicio DESC
    """, (user_id,))
    planes = cursor.fetchall()
    
    if not planes:
        await update.message.reply_text(
            "📋 **TU PLAN DE PAGO**\n\n"
            "No tienes un plan de pago asignado.\n\n"
            "📞 Contacta al administrador para que te asigne productos."
        )
        conn.close()
        return
    
    # Obtener configuración
    cursor.execute("SELECT semanas FROM config_pagos LIMIT 1")
    config = cursor.fetchone()
    semanas_config = config[0] if config else 10
    
    plan_id, productos_json, total, semanas, pago_semanal, semanas_comp, fecha_inicio, contador_pausado = planes[0]
    
    # Convertir productos_json si es necesario
    if isinstance(productos_json, str):
        productos_json = json.loads(productos_json)
    
    # Construir mensaje detallado
    mensaje = "📋 **TU PLAN DE PAGO** (Asignado por administración)\n\n"
    mensaje += "🛍️ **PRODUCTOS ASIGNADOS:**\n"
    
    total_calculado = 0
    if productos_json:
        for producto_id, cantidad in productos_json.items():
            cursor.execute("SELECT nombre, precio FROM productos WHERE id = %s", (int(producto_id),))
            producto_info = cursor.fetchone()
            if producto_info:
                nombre, precio = producto_info
                subtotal = precio * cantidad
                total_calculado += subtotal
                mensaje += f"• {nombre} x{cantidad} - ${subtotal:.2f}\n"
    
    conn.close()
    
    estado_contador = "⏸️ PAUSADO" if contador_pausado else "🟢 ACTIVO"
    
    mensaje += f"\n💰 **TOTAL:** ${total_calculado:.2f}\n"
    mensaje += f"📅 **SEMANAS:** {semanas_comp}/{semanas_config}\n"
    mensaje += f"💳 **PAGO SEMANAL:** ${pago_semanal:.2f}\n"
    mensaje += f"📊 **PROGRESO:** {semanas_comp}/{semanas_config} semanas\n"
    mensaje += f"⏰ **CONTADOR:** {estado_contador}\n\n"
    mensaje += "💳 **Registrar pago:** /pagarealizado\n"
    mensaje += "📞 **Contactar admin:** @tu_admin"
    
    await update.message.reply_text(mensaje)

# =============================================
# 🛍️ SISTEMA DE CATÁLOGO (SOLO LECTURA)
# =============================================

async def catalogo_solo_lectura(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Catálogo completo para usuarios (SOLO LECTURA, sin comprar)"""
    user_id = update.effective_user.id
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Verificar si el usuario existe
    cursor.execute("SELECT * FROM usuarios WHERE user_id = %s", (user_id,))
    usuario = cursor.fetchone()
    
    if not usuario:
        await update.message.reply_text("❌ Debes registrarte con /start primero")
        conn.close()
        return
        
    # Obtener productos activos
    cursor.execute("""
        SELECT id, nombre, precio, descripcion, categoria 
        FROM productos 
        WHERE estado = 'activo' 
        ORDER BY categoria, id
    """)
    productos = cursor.fetchall()
    
    # Obtener configuración de semanas
    cursor.execute("SELECT semanas FROM config_pagos LIMIT 1")
    config = cursor.fetchone()
    conn.close()
    
    semanas = config[0] if config else 10
    
    if not productos:
        await update.message.reply_text("📭 El catálogo está vacío por ahora")
        return
        
    # Organizar por categorías
    categorias = {}
    for id_prod, nombre, precio, descripcion, categoria in productos:
        cat = categoria or "General"
        if cat not in categorias:
            categorias[cat] = []
        categorias[cat].append((id_prod, nombre, precio, descripcion))
    
    mensaje = f"🛍️ **CATÁLOGO DE PRODUCTOS**\n**Plan de pago: {semanas} SEMANAS**\n\n"
    mensaje += "📞 **Contacta al administrador para asignarte productos**\n\n"
    
    for categoria, productos_cat in categorias.items():
        mensaje += f"📂 **{categoria.upper()}**\n"
        for id_prod, nombre, precio, descripcion in productos_cat:
            pago_semanal = precio / semanas
            mensaje += f"  {id_prod}. **{nombre}** - ${precio:.2f}\n"
            mensaje += f"     📝 {descripcion or 'Sin descripción'}\n"
            mensaje += f"     💰 **Pago semanal:** ${pago_semanal:.2f}\n\n"

    mensaje += "📋 **Tu plan actual:** /misplanes\n"
    mensaje += "⭐ **Tus puntos:** /mispuntos\n"
    mensaje += "📞 **Contactar admin:** @tu_admin"
    
    await update.message.reply_text(mensaje)

# =============================================
# 🔄 MANEJO DE BOTONES PARA ASIGNACIÓN
# =============================================

async def button_handler_asignacion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja los botones del sistema de asignación"""
    query = update.callback_query
    await query.answer()
    
    print(f"🟡 BOTÓN ASIGNACIÓN: {query.data}")
    
    if query.data.startswith("asignar_mas_") or query.data.startswith("asignar_menos_"):
        await manejar_cambio_cantidad(query, context)
    elif query.data.startswith("asignar_confirmar_"):
        await confirmar_asignacion(query, context)
    elif query.data.startswith("asignar_reiniciar_"):
        await reiniciar_asignacion(query, context)
    elif query.data == "asignar_cancelar":
        await query.edit_message_text("❌ **Asignación cancelada**")

async def manejar_cambio_cantidad(query, context):
    """Maneja aumento/disminución de cantidades"""
    partes = query.data.split('_')
    accion = partes[1]  # 'mas' o 'menos'
    user_id = partes[2]
    producto_id = partes[3]
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Obtener productos disponibles
    cursor.execute("SELECT id, nombre, precio, descripcion FROM productos WHERE estado = 'activo' ORDER BY nombre")
    productos = cursor.fetchall()
    
    # Obtener estado actual desde la base de datos o temporal
    productos_actuales = context.user_data.get(f'asignacion_temp_{user_id}', {})
    if not productos_actuales:
        cursor.execute("SELECT productos_json FROM planes_pago WHERE user_id = %s AND estado = 'activo'", (user_id,))
        plan_actual = cursor.fetchone()
        if plan_actual and plan_actual[0]:
            productos_actuales = plan_actual[0] if isinstance(plan_actual[0], dict) else json.loads(plan_actual[0])
    
    # Actualizar cantidad
    producto_key = str(producto_id)
    cantidad_actual = productos_actuales.get(producto_key, 0)
    
    if accion == 'mas':
        productos_actuales[producto_key] = cantidad_actual + 1
    elif accion == 'menos' and cantidad_actual > 0:
        productos_actuales[producto_key] = cantidad_actual - 1
        if productos_actuales[producto_key] == 0:
            del productos_actuales[producto_key]
    
    # Guardar estado temporal en context
    context.user_data[f'asignacion_temp_{user_id}'] = productos_actuales
    
    conn.close()
    
    # Recrear el mensaje con los nuevos valores
    await recrear_mensaje_asignacion(query, context, user_id, productos, productos_actuales)

async def recrear_mensaje_asignacion(query, context, user_id, productos, productos_actuales):
    """Recrea el mensaje de asignación con los valores actualizados"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Obtener información del usuario
    cursor.execute("SELECT first_name, last_name FROM usuarios WHERE user_id = %s", (user_id,))
    usuario = cursor.fetchone()
    first_name, last_name = usuario
    nombre_completo = f"{first_name or ''} {last_name or ''}".strip()
    
    # Obtener configuración de semanas
    cursor.execute("SELECT semanas FROM config_pagos LIMIT 1")
    config = cursor.fetchone()
    semanas = config[0] if config else 10
    
    conn.close()  # ✅ Cerrar conexión aquí
    
    # Crear mensaje
    mensaje = f"🛍️ **ASIGNAR PRODUCTOS A USUARIO**\n\n"
    mensaje += f"👤 **Usuario:** {nombre_completo}\n"
    mensaje += f"🆔 **ID:** {user_id}\n\n"
    mensaje += "📦 **PRODUCTOS DISPONIBLES:**\n\n"
    
    keyboard = []
    
    for producto_id, nombre, precio, descripcion in productos:
        cantidad_actual = productos_actuales.get(str(producto_id), 0)
        mensaje += f"📦 **{nombre}** - ${precio:.2f}\n"
        mensaje += f"   📝 {descripcion or 'Sin descripción'}\n"
        mensaje += f"   🔢 Cantidad actual: {cantidad_actual}\n"
        
        # Botones para ajustar cantidad
        row = [
            InlineKeyboardButton(f"➖ {nombre[:15]}...", callback_data=f"asignar_menos_{user_id}_{producto_id}"),
            InlineKeyboardButton(f"➕ {nombre[:15]}...", callback_data=f"asignar_mas_{user_id}_{producto_id}")
        ]
        keyboard.append(row)
    
    # Botones de control
    keyboard.append([InlineKeyboardButton("✅ CONFIRMAR ASIGNACIÓN", callback_data=f"asignar_confirmar_{user_id}")])
    keyboard.append([InlineKeyboardButton("🔄 REINICIAR", callback_data=f"asignar_reiniciar_{user_id}")])
    keyboard.append([InlineKeyboardButton("❌ CANCELAR", callback_data=f"asignar_cancelar")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Calcular resumen actual
    total_actual = 0
    for producto_id, cantidad in productos_actuales.items():
        for prod_id, nombre, precio, desc in productos:
            if str(prod_id) == producto_id:
                total_actual += precio * cantidad
                break
    
    pago_semanal_actual = total_actual / semanas if semanas > 0 else 0
    
    mensaje += f"\n📊 **RESUMEN ACTUAL:**\n"
    mensaje += f"💰 **Total:** ${total_actual:.2f}\n"
    mensaje += f"📅 **Pago semanal:** ${pago_semanal_actual:.2f}\n"
    mensaje += f"🔢 **Semanas:** {semanas}\n"
    
    await query.edit_message_text(mensaje, reply_markup=reply_markup)

async def confirmar_asignacion(query, context):
    """Confirma la asignación de productos"""
    partes = query.data.split('_')
    user_id = partes[2]
    
    # Obtener productos temporales
    productos_actuales = context.user_data.get(f'asignacion_temp_{user_id}', {})
    
    # Limpiar productos con cantidad 0
    productos_finales = {k: v for k, v in productos_actuales.items() if v > 0}
    
    if not productos_finales:
        await query.edit_message_text("❌ **No se pueden asignar 0 productos**\n\nLa asignación debe incluir al menos un producto.")
        return
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Calcular total
        total = 0
        for producto_id, cantidad in productos_finales.items():
            cursor.execute("SELECT precio FROM productos WHERE id = %s", (int(producto_id),))
            producto = cursor.fetchone()
            if producto:
                total += producto[0] * cantidad
        
        # Obtener configuración
        cursor.execute("SELECT semanas FROM config_pagos LIMIT 1")
        config = cursor.fetchone()
        semanas = config[0] if config else 10
        pago_semanal = total / semanas if semanas > 0 else 0
        
        # Verificar si ya existe un plan activo
        cursor.execute("SELECT id FROM planes_pago WHERE user_id = %s AND estado = 'activo'", (user_id,))
        plan_existente = cursor.fetchone()
        
        if plan_existente:
            # Actualizar plan existente (REINICIAR progreso)
            cursor.execute("""
                UPDATE planes_pago 
                SET productos_json = %s, total = %s, semanas = %s, pago_semanal = %s, 
                    semanas_completadas = 0, fecha_actualizacion = CURRENT_TIMESTAMP
                WHERE user_id = %s AND estado = 'activo'
            """, (json.dumps(productos_finales), total, semanas, pago_semanal, user_id))
        else:
            # Crear nuevo plan
            cursor.execute("""
                INSERT INTO planes_pago (user_id, productos_json, total, semanas, pago_semanal)
                VALUES (%s, %s, %s, %s, %s)
            """, (user_id, json.dumps(productos_finales), total, semanas, pago_semanal))
        
        conn.commit()
        
        # Obtener información del usuario para el mensaje
        cursor.execute("SELECT first_name, last_name FROM usuarios WHERE user_id = %s", (user_id,))
        usuario = cursor.fetchone()
        first_name, last_name = usuario
        nombre_completo = f"{first_name or ''} {last_name or ''}".strip()
        
        # Construir mensaje de confirmación
        mensaje = f"✅ **ASIGNACIÓN CONFIRMADA**\n\n"
        mensaje += f"👤 **Usuario:** {nombre_completo}\n"
        mensaje += f"🆔 **ID:** {user_id}\n\n"
        mensaje += "🛍️ **PRODUCTOS ASIGNADOS:**\n"
        
        for producto_id, cantidad in productos_finales.items():
            cursor.execute("SELECT nombre, precio FROM productos WHERE id = %s", (int(producto_id),))
            producto = cursor.fetchone()
            if producto:
                nombre, precio = producto
                mensaje += f"• {nombre} x{cantidad} - ${precio * cantidad:.2f}\n"
        
        mensaje += f"\n💰 **TOTAL:** ${total:.2f}\n"
        mensaje += f"📅 **SEMANAS:** {semanas}\n"
        mensaje += f"💳 **PAGO SEMANAL:** ${pago_semanal:.2f}\n"
        
        if plan_existente:
            mensaje += f"\n⚠️ **El progreso anterior se reinició a 0 semanas**"
        
        await query.edit_message_text(mensaje)
        
        # Limpiar datos temporales
        if f'asignacion_temp_{user_id}' in context.user_data:
            del context.user_data[f'asignacion_temp_{user_id}']
            
    except Exception as e:
        print(f"❌ Error al confirmar asignación: {e}")
        await query.edit_message_text("❌ Error al confirmar la asignación")
    finally:
        conn.close()

async def reiniciar_asignacion(query, context):
    """Reinicia la asignación actual"""
    partes = query.data.split('_')
    user_id = partes[2]
    
    # Limpiar datos temporales
    if f'asignacion_temp_{user_id}' in context.user_data:
        del context.user_data[f'asignacion_temp_{user_id}']
    
    # Volver a cargar la asignación
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Obtener información del usuario
    cursor.execute("SELECT first_name, last_name FROM usuarios WHERE user_id = %s", (user_id,))
    usuario = cursor.fetchone()
    
    if not usuario:
        await query.edit_message_text("❌ Usuario no encontrado")
        conn.close()
        return
        
    first_name, last_name = usuario
    nombre_completo = f"{first_name or ''} {last_name or ''}".strip()
    
    # Obtener productos activos
    cursor.execute("SELECT id, nombre, precio, descripcion FROM productos WHERE estado = 'activo' ORDER BY nombre")
    productos = cursor.fetchall()
    
    # Iniciar con productos vacíos
    productos_actuales = {}
    
    conn.close()
    
    # Recrear mensaje
    await recrear_mensaje_asignacion(query, context, user_id, productos, productos_actuales)

# =============================================
# 🎯 FUNCIONES BÁSICAS DEL BOT (MODIFICADAS)
# =============================================

async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancela cualquier operación en curso"""
    context.user_data.clear()
    
    await update.message.reply_text(
        "🔄 **Operación cancelada**\n\n"
        "Todas las acciones en curso han sido canceladas.\n\n"
        "Puedes comenzar de nuevo."
    )

async def pagarealizado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia el proceso de registro de pago"""
    user_id = update.effective_user.id
    
    # Verificar si el usuario está registrado
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE user_id = %s", (user_id,))
    usuario = cursor.fetchone()
    conn.close()
    
    if not usuario:
        await update.message.reply_text("❌ Debes registrarte con /start primero")
        return
    
    context.user_data['esperando_datos_pago'] = True
    context.user_data['esperando_imagen'] = False
    
    await update.message.reply_text(
        "💳 **REGISTRAR PAGO**\n\n"
        "Por favor envía los datos de tu pago en el siguiente formato:\n\n"
        "**Nombre: Tu nombre completo**\n"
        "**Referencia: Número de referencia o transacción**\n"
        "**Monto: Cantidad pagada**\n\n"
        "Ejemplo:\n"
        "Nombre: Juan Pérez\n"
        "Referencia: 123456\n"
        "Monto: 150.00"
    )

async def verpagos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra los pagos pendientes (solo admin)"""
    if update.effective_user.id != 5908252094:
        await update.message.reply_text("❌ No tienes permisos de administrador")
        return
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.id, p.user_id, u.first_name, u.last_name, p.referencia, p.monto, p.fecha, p.estado 
        FROM pagos p 
        LEFT JOIN usuarios u ON p.user_id = u.user_id 
        WHERE p.estado = 'pendiente'
        ORDER BY p.fecha DESC
    """)
    pagos = cursor.fetchall()
    conn.close()
    
    if not pagos:
        await update.message.reply_text("✅ No hay pagos pendientes por revisar")
        return
    
    mensaje = "📋 **PAGOS PENDIENTES**\n\n"
    
    for pago_id, user_id, first_name, last_name, referencia, monto, fecha, estado in pagos:
        nombre_completo = f"{first_name or ''} {last_name or ''}".strip()
        mensaje += f"🆔 **ID Pago:** {pago_id}\n"
        mensaje += f"👤 **Usuario:** {nombre_completo or 'N/A'} (ID: {user_id})\n"
        mensaje += f"💰 **Monto:** ${monto:.2f}\n"
        mensaje += f"🔢 **Referencia:** {referencia}\n"
        mensaje += f"📅 **Fecha:** {fecha.strftime('%d/%m/%Y %H:%M')}\n"
        mensaje += f"👁️ /verimagen_{pago_id} | ✅ /confirmar_{pago_id} | ❌ /rechazar_{pago_id} | 🗑️ /borrar_{pago_id}\n"
        mensaje += "━━━━━━━━━━━━━━━━━━━━\n\n"
    
    await update.message.reply_text(mensaje)

async def verusuarios(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra todos los usuarios (solo admin)"""
    if update.effective_user.id != 5908252094:
        await update.message.reply_text("❌ No tienes permisos de administrador")
        return
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT user_id, first_name, last_name, user_name, phone, fecha_registro, estado 
        FROM usuarios 
        ORDER BY fecha_registro DESC
    """)
    usuarios = cursor.fetchall()
    conn.close()
    
    if not usuarios:
        await update.message.reply_text("📭 No hay usuarios registrados")
        return
    
    mensaje = "👥 **USUARIOS REGISTRADOS**\n\n"
    
    for user_id, first_name, last_name, user_name, phone, fecha_registro, estado in usuarios:
        nombre_completo = f"{first_name or ''} {last_name or ''}".strip()
        mensaje += f"🆔 **ID:** {user_id}\n"
        mensaje += f"👤 **Nombre:** {nombre_completo or 'N/A'}\n"
        mensaje += f"📱 **Teléfono:** {phone or 'No registrado'}\n"
        mensaje += f"📅 **Registro:** {fecha_registro.strftime('%d/%m/%Y')}\n"
        mensaje += f"📊 **Estado:** {estado}\n"
        mensaje += f"🗑️ /borrarusuario_{user_id}\n"
        mensaje += "━━━━━━━━━━━━━━━━━━━━\n\n"
    
    await update.message.reply_text(mensaje)

async def mistatus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra el estado de los pagos del usuario"""
    user_id = update.effective_user.id
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT referencia, monto, estado, fecha 
        FROM pagos 
        WHERE user_id = %s 
        ORDER BY fecha DESC
    """, (user_id,))
    pagos = cursor.fetchall()
    conn.close()
    
    if not pagos:
        await update.message.reply_text(
            "📊 **MIS PAGOS**\n\n"
            "No has realizado ningún pago todavía.\n\n"
            "💳 Para registrar un pago usa:\n"
            "/pagarealizado"
        )
        return
    
    mensaje = "📊 **HISTORIAL DE MIS PAGOS**\n\n"
    
    for referencia, monto, estado, fecha in pagos:
        icono = "✅" if estado == "aprobado" else "⏳" if estado == "pendiente" else "❌"
        mensaje += f"{icono} **Referencia:** {referencia}\n"
        mensaje += f"💰 **Monto:** ${monto:.2f}\n"
        mensaje += f"📊 **Estado:** {estado}\n"
        mensaje += f"📅 **Fecha:** {fecha.strftime('%d/%m/%Y %H:%M')}\n"
        mensaje += "━━━━━━━━━━━━━━━━━━━━\n\n"
    
    await update.message.reply_text(mensaje)

# =============================================
# FUNCIONES DE MANEJO DE ARCHIVOS
# =============================================

async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja la recepción de imágenes/comprobantes"""
    print(f"🟡 IMAGEN RECIBIDA - User data: {context.user_data}")
    
    if context.user_data.get('esperando_imagen'):
        user_id = update.effective_user.id
        
        # Obtener la imagen
        if update.message.photo:
            file_id = update.message.photo[-1].file_id
        elif update.message.document:
            file_id = update.message.document.file_id
        else:
            await update.message.reply_text("❌ No se pudo obtener la imagen")
            return
        
        # Obtener datos del pago
        datos_pago = context.user_data.get('datos_pago', {})
        nombre = datos_pago.get('nombre', '')
        referencia = datos_pago.get('referencia', '')
        monto = datos_pago.get('monto', '0')
        
        try:
            monto_float = float(monto)
        except ValueError:
            monto_float = 0
        
        # Guardar en base de datos
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO pagos (user_id, user_name, referencia, file_id, monto) VALUES (%s, %s, %s, %s, %s)",
            (user_id, nombre, referencia, file_id, monto_float)
        )
        conn.commit()
        conn.close()
        
        # Limpiar estados
        context.user_data['esperando_imagen'] = False
        context.user_data['datos_pago'] = None
        
        await update.message.reply_text(
            "✅ **¡Pago registrado exitosamente!**\n\n"
            "📋 **Resumen:**\n"
            f"👤 **Nombre:** {nombre}\n"
            f"🔢 **Referencia:** {referencia}\n"
            f"💰 **Monto:** ${monto_float:.2f}\n\n"
            "⏳ **Estado:** Pendiente de revisión\n\n"
            "El administrador revisará tu comprobante y actualizará el estado.\n"
            "Puedes ver el estado con /mistatus"
        )
        print(f"✅ Pago registrado para usuario {user_id}")
    else:
        await update.message.reply_text(
            "ℹ️ Para registrar un pago, usa el comando /pagarealizado primero"
        )

async def handle_all_documents(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja documentos que no son imágenes"""
    await update.message.reply_text(
        "📄 **Formato no compatible**\n\n"
        "Solo se aceptan imágenes como comprobantes de pago.\n\n"
        "Por favor envía una foto o captura de pantalla de tu comprobante."
    )

async def handle_rechazo_motivo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja el motivo de rechazo de un pago"""
    if not context.user_data.get('rechazando_pago'):
        return
    
    motivo = update.message.text
    pago_id = context.user_data['rechazando_pago']
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE pagos SET estado = 'rechazado' WHERE id = %s", (pago_id,))
    conn.commit()
    
    # Obtener user_id del pago rechazado
    cursor.execute("SELECT user_id FROM pagos WHERE id = %s", (pago_id,))
    resultado = cursor.fetchone()
    conn.close()
    
    context.user_data['rechazando_pago'] = None
    
    if resultado:
        user_id = resultado[0]
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"❌ **Tu pago ha sido rechazado**\n\n"
                     f"**Motivo:** {motivo}\n\n"
                     f"Por favor contacta al administrador para más información."
            )
        except Exception as e:
            print(f"❌ No se pudo notificar al usuario: {e}")
    
    await update.message.reply_text("✅ Pago rechazado y usuario notificado")

# =============================================
# FUNCIONES ADMIN PARA PAGOS
# =============================================

async def verimagen_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra la imagen del comprobante de pago (admin)"""
    if update.effective_user.id != 5908252094:
        await update.message.reply_text("❌ No tienes permisos de administrador")
        return

    command_text = update.message.text
    try:
        pago_id = command_text.split('_')[1]
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT file_id, user_id, referencia, monto FROM pagos WHERE id = %s", (pago_id,))
        pago = cursor.fetchone()
        conn.close()
        
        if pago:
            file_id, user_id, referencia, monto = pago
            await update.message.reply_photo(
                photo=file_id,
                caption=f"📸 **Comprobante de pago**\n\n"
                       f"🆔 **ID Pago:** {pago_id}\n"
                       f"👤 **User ID:** {user_id}\n"
                       f"🔢 **Referencia:** {referencia}\n"
                       f"💰 **Monto:** ${monto:.2f}"
            )
        else:
            await update.message.reply_text("❌ Pago no encontrado")
            
    except Exception as e:
        print(f"❌ Error en verimagen_admin: {e}")
        await update.message.reply_text("❌ Error al mostrar la imagen")

async def rechazar_pago(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Rechaza un pago pendiente (admin)"""
    if update.effective_user.id != 5908252094:
        await update.message.reply_text("❌ No tienes permisos de administrador")
        return

    command_text = update.message.text
    try:
        pago_id = command_text.split('_')[1]
        
        context.user_data['rechazando_pago'] = pago_id
        await update.message.reply_text(
            "❌ **RECHAZAR PAGO**\n\n"
            "Por favor envía el motivo del rechazo:\n"
            "(Ejemplo: 'Comprobante ilegible', 'Monto incorrecto', etc.)"
        )
        
    except Exception as e:
        print(f"❌ Error en rechazar_pago: {e}")
        await update.message.reply_text("❌ Error al procesar el rechazo")

async def borrar_pago(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Elimina un pago (admin)"""
    if update.effective_user.id != 5908252094:
        await update.message.reply_text("❌ No tienes permisos de administrador")
        return

    command_text = update.message.text
    try:
        pago_id = command_text.split('_')[1]
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM pagos WHERE id = %s", (pago_id,))
        conn.commit()
        conn.close()
        
        await update.message.reply_text("✅ Pago eliminado correctamente")
        
    except Exception as e:
        print(f"❌ Error en borrar_pago: {e}")
        await update.message.reply_text("❌ Error al eliminar el pago")

async def borrarusuario(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Elimina un usuario y TODOS sus datos relacionados (admin)"""
    if update.effective_user.id != 5908252094:
        await update.message.reply_text("❌ No tienes permisos de administrador")
        return

    command_text = update.message.text
    try:
        user_id = command_text.split('_')[1]
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 1. Primero obtener información del usuario para confirmar
        cursor.execute("SELECT first_name, last_name FROM usuarios WHERE user_id = %s", (user_id,))
        usuario = cursor.fetchone()
        
        if not usuario:
            await update.message.reply_text("❌ Usuario no encontrado")
            conn.close()
            return
        
        first_name, last_name = usuario
        nombre_completo = f"{first_name or ''} {last_name or ''}".strip()
        
        # 2. Contar datos relacionados para mostrar en confirmación
        cursor.execute("SELECT COUNT(*) FROM planes_pago WHERE user_id = %s", (user_id,))
        planes_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM pagos WHERE user_id = %s", (user_id,))
        pagos_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM usuarios_puntos WHERE user_id = %s", (user_id,))
        puntos_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM referidos WHERE user_id_referidor = %s OR user_id_referido = %s", (user_id, user_id))
        referidos_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM puntos_historial WHERE user_id = %s", (user_id,))
        historial_count = cursor.fetchone()[0]
        
        # 3. Mostrar confirmación con advertencia
        mensaje = (
            f"🗑️ **ELIMINAR USUARIO - CONFIRMACIÓN**\n\n"
            f"👤 **Usuario:** {nombre_completo}\n"
            f"🆔 **ID:** {user_id}\n\n"
            f"📊 **Datos a eliminar:**\n"
            f"• 📋 Planes activos: {planes_count}\n"
            f"• 💳 Pagos registrados: {pagos_count}\n"
            f"• ⭐ Datos de puntos: {puntos_count}\n"
            f"• 👥 Referidos: {referidos_count}\n"
            f"• 📈 Historial puntos: {historial_count}\n\n"
            f"⚠️ **Esta acción NO es reversible**\n\n"
            f"¿Estás seguro de eliminar este usuario y TODOS sus datos?"
        )
        
        keyboard = [
            [InlineKeyboardButton("✅ SÍ, ELIMINAR TODO", callback_data=f"eliminar_usuario_si_{user_id}")],
            [InlineKeyboardButton("❌ CANCELAR", callback_data=f"eliminar_usuario_no_{user_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(mensaje, reply_markup=reply_markup)
        conn.close()
        
    except Exception as e:
        print(f"❌ Error en borrarusuario: {e}")
        await update.message.reply_text("❌ Error al procesar la eliminación")

# =============================================
# FUNCIONES DE PRODUCTOS
# =============================================

async def admin_ver_productos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ver catálogo completo para admin"""
    if update.effective_user.id != 5908252094:
        await update.message.reply_text("❌ No tienes permisos de administrador")
        return
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Obtener productos activos
    cursor.execute("""
        SELECT id, nombre, precio, descripcion, categoria 
        FROM productos 
        WHERE estado = 'activo' 
        ORDER BY id
    """)
    productos = cursor.fetchall()
    
    # Obtener configuración
    cursor.execute("SELECT semanas, contador_activo FROM config_pagos LIMIT 1")
    config = cursor.fetchone()
    conn.close()
    
    semanas = config[0] if config else 10
    contador_activo = config[1] if config else True
    
    if not productos:
        await update.message.reply_text("📭 No hay productos en el catálogo")
        return
        
    mensaje = f"🛍️ **CATÁLOGO COMPLETO - ADMIN**\n"
    mensaje += f"**Plan de pago:** {semanas} SEMANAS\n"
    mensaje += f"**Contador:** {'🟢 ACTIVO' if contador_activo else '🔴 PAUSADO'}\n\n"
    
    for id_prod, nombre, precio, descripcion, categoria in productos:
        pago_semanal = precio / semanas
        mensaje += f"🆔 **ID:** {id_prod}\n"
        mensaje += f"📦 **Producto:** {nombre}\n"
        mensaje += f"💰 **Precio:** ${precio:.2f}\n"
        mensaje += f"📝 **Descripción:** {descripcion or 'Sin descripción'}\n"
        mensaje += f"📂 **Categoría:** {categoria or 'General'}\n"
        mensaje += f"💳 **Pago semanal:** ${pago_semanal:.2f}\n"
        mensaje += f"✏️ /editarproducto_{id_prod} | 🗑️ /eliminarproducto_{id_prod}\n"
        mensaje += "━━━━━━━━━━━━━━━━━━━━\n\n"

    await update.message.reply_text(mensaje)

async def admin_agregar_producto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Agregar producto completo con descripción y categoría"""
    if update.effective_user.id != 5908252094:
        await update.message.reply_text("❌ No tienes permisos de administrador")
        return
        
    context.user_data['agregando_producto'] = True
    await update.message.reply_text(
        "🛍️ **AGREGAR PRODUCTO COMPLETO**\n\n"
        "Envía los datos en este formato:\n\n"
        "**Nombre: iPhone 15**\n"
        "**Precio: 1000**\n"
        "**Descripción: Último modelo iPhone**\n"
        "**Categoría: Tecnología**\n\n"
        "Ejemplo completo:\n"
        "Nombre: iPhone 15\n"
        "Precio: 1000\n"
        "Descripción: Último modelo iPhone 2023\n"
        "Categoría: Tecnología"
    )

async def editar_producto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Editar producto existente"""
    if update.effective_user.id != 5908252094:
        await update.message.reply_text("❌ No tienes permisos de administrador")
        return

    command_text = update.message.text
    if not command_text.startswith('/editarproducto_'):
        await update.message.reply_text("❌ Uso: /editarproducto_1")
        return
    
    try:
        producto_id = command_text.split('_')[1]
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT nombre, precio FROM productos WHERE id = %s", (producto_id,))
        producto = cursor.fetchone()
        conn.close()
        
        if producto:
            nombre, precio = producto
            context.user_data['editando_producto'] = producto_id
            
            keyboard = [
                [InlineKeyboardButton("📝 Nombre", callback_data=f"editar_nombre_{producto_id}")],
                [InlineKeyboardButton("💰 Precio", callback_data=f"editar_precio_{producto_id}")],
                [InlineKeyboardButton("📄 Descripción", callback_data=f"editar_descripcion_{producto_id}")],
                [InlineKeyboardButton("📂 Categoría", callback_data=f"editar_categoria_{producto_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"✏️ **EDITANDO PRODUCTO**\n\n"
                f"📦 **Producto:** {nombre}\n"
                f"💰 **Precio:** ${precio}\n\n"
                f"¿Qué deseas editar?",
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text("❌ Producto no encontrado")
            
    except Exception as e:
        print(f"❌ Error en editar_producto: {e}")
        await update.message.reply_text("❌ Error al procesar edición")

async def eliminar_producto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Eliminar producto con confirmación"""
    if update.effective_user.id != 5908252094:
        await update.message.reply_text("❌ No tienes permisos de administrador")
        return

    command_text = update.message.text
    if not command_text.startswith('/eliminarproducto_'):
        await update.message.reply_text("❌ Uso: /eliminarproducto_1")
        return
    
    try:
        producto_id = command_text.split('_')[1]
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT nombre, precio FROM productos WHERE id = %s", (producto_id,))
        producto = cursor.fetchone()
        conn.close()
        
        if producto:
            nombre, precio = producto
            
            keyboard = [
                [InlineKeyboardButton("✅ Sí, eliminar", callback_data=f"eliminar_si_{producto_id}")],
                [InlineKeyboardButton("❌ Cancelar", callback_data=f"eliminar_no_{producto_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"🗑️ **ELIMINAR PRODUCTO**\n\n"
                f"📦 **Producto:** {nombre}\n"
                f"💰 **Precio:** ${precio}\n\n"
                f"¿Estás seguro de eliminar este producto?",
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text("❌ Producto no encontrado")
            
    except Exception as e:
        print(f"❌ Error en eliminar_producto: {e}")
        await update.message.reply_text("❌ Error al procesar eliminación")

# =============================================
# SISTEMA DE CONTROL DE CONTADOR (SOLO ADMIN)
# =============================================

async def estado_contador(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ver estado del contador con información completa"""
    if update.effective_user.id != 5908252094:
        await update.message.reply_text("❌ No tienes permisos de administrador")
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Configuración global
    cursor.execute("SELECT semanas, contador_activo FROM config_pagos LIMIT 1")
    config = cursor.fetchone()
    semanas = config[0] if config else 10
    contador_activo = config[1] if config else True
    
    # Estadísticas
    cursor.execute("SELECT COUNT(*) FROM planes_pago WHERE estado = 'activo'")
    total_planes = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM planes_pago WHERE contador_pausado = TRUE AND estado = 'activo'")
    planes_pausados = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM planes_pago WHERE semanas_completadas >= semanas AND estado = 'activo'")
    planes_completados = cursor.fetchone()[0]
    
    conn.close()
    
    # Calcular próximo incremento automático
    ahora = datetime.now()
    proximo_incremento = ahora + timedelta(days=7)
    
    await update.message.reply_text(
        f"⚙️ **ESTADO DEL SISTEMA - DETALLADO**\n\n"
        f"🔢 **Semanas configuradas:** {semanas}\n"
        f"📊 **Estado contador:** {'🟢 ACTIVO' if contador_activo else '🔴 PAUSADO'}\n\n"
        f"📈 **ESTADÍSTICAS:**\n"
        f"• 📋 Planes activos: {total_planes}\n"
        f"• ⏸️ Planes pausados: {planes_pausados}\n"
        f"• ✅ Planes completados: {planes_completados}\n\n"
        f"🔄 **INCREMENTO AUTOMÁTICO:**\n"
        f"• ⏰ Próximo: {proximo_incremento.strftime('%d/%m/%Y %H:%M')}\n"
        f"• 📅 Frecuencia: 7 días\n\n"
        f"**Controles:**\n"
        f"⏸️ /pausarcontador - Pausar contador\n"
        f"▶️ /reanudarcontador - Reanudar contador\n"
        f"🔢 /configurarsemanas - Cambiar semanas\n"
        f"📈 /incrementarsemana - Incremento manual\n"
        f"🔄 /forzarincremento - Forzar incremento (ignora pausa)"
    )

async def pausar_contador(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pausar contador de semanas"""
    if update.effective_user.id != 5908252094:
        await update.message.reply_text("❌ No tienes permisos de administrador")
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE config_pagos SET contador_activo = FALSE")
    cursor.execute("UPDATE planes_pago SET contador_pausado = TRUE WHERE estado = 'activo'")
    conn.commit()
    conn.close()
    
    await update.message.reply_text(
        "🔴 **CONTADOR PAUSADO**\n\n"
        "El contador de semanas ha sido pausado para TODOS los planes activos.\n\n"
        "Para reanudar usa: /reanudarcontador"
    )

async def reanudar_contador(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reanudar contador de semanas"""
    if update.effective_user.id != 5908252094:
        await update.message.reply_text("❌ No tienes permisos de administrador")
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE config_pagos SET contador_activo = TRUE")
    cursor.execute("UPDATE planes_pago SET contador_pausado = FALSE WHERE estado = 'activo'")
    conn.commit()
    conn.close()
    
    await update.message.reply_text(
        "🟢 **CONTADOR REANUDADO**\n\n"
        "El contador de semanas ha sido activado para TODOS los planes activos.\n\n"
        "Para pausar usa: /pausarcontador"
    )

async def configurar_semanas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Configurar semanas con opciones predefinidas y reinicio automático"""
    if update.effective_user.id != 5908252094:
        await update.message.reply_text("❌ No tienes permisos de administrador")
        return

    if context.args:
        try:
            semanas = int(context.args[0])
            if semanas < 1:
                await update.message.reply_text("❌ El número de semanas debe ser mayor a 0")
                return

            conn = get_db_connection()
            cursor = conn.cursor()
            
            # 1. Actualizar configuración de semanas
            cursor.execute("UPDATE config_pagos SET semanas = %s", (semanas,))
            
            # 2. ✅ REINICIAR AUTOMÁTICAMENTE TODOS LOS CONTADORES
            cursor.execute("""
                UPDATE planes_pago 
                SET semanas_completadas = 0, 
                    fecha_ultimo_pago = CURRENT_TIMESTAMP
                WHERE estado = 'activo'
            """)
            planes_afectados = cursor.rowcount
            
            conn.commit()
            conn.close()

            await update.message.reply_text(
                f"✅ **Configuración actualizada y contadores reiniciados**\n\n"
                f"🔢 **Nuevas semanas de pago:** {semanas}\n"
                f"🔄 **Planes reiniciados:** {planes_afectados}\n\n"
                f"Todos los planes activos han sido reiniciados a semana 0.\n"
                f"El sistema comenzará desde el inicio con {semanas} semanas."
            )
            return
            
        except ValueError:
            await update.message.reply_text("❌ El número de semanas debe ser un número válido")
            return

    # Mostrar opciones de semanas (código existente se mantiene igual)
    keyboard = [
        [InlineKeyboardButton("🔄 4 Semanas", callback_data="semanas_4")],
        [InlineKeyboardButton("🔄 8 Semanas", callback_data="semanas_8")],
        [InlineKeyboardButton("🔄 12 Semanas", callback_data="semanas_12")],
        [InlineKeyboardButton("🔄 16 Semanas", callback_data="semanas_16")],
        [InlineKeyboardButton("🔄 20 Semanas", callback_data="semanas_20")],
        [InlineKeyboardButton("✏️ Personalizado", callback_data="semanas_personalizado")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT semanas, contador_activo FROM config_pagos LIMIT 1")
    config = cursor.fetchone()
    conn.close()
    
    semanas_actuales = config[0] if config else 10
    contador_activo = config[1] if config else True
    
    await update.message.reply_text(
        f"⚙️ **CONFIGURAR SEMANAS DE PAGO**\n\n"
        f"🔢 **Actual:** {semanas_actuales} semanas\n"
        f"📊 **Contador:** {'🟢 ACTIVO' if contador_activo else '🔴 PAUSADO'}\n\n"
        f"⚠️ **IMPORTANTE:** Al cambiar las semanas, todos los contadores se reiniciarán a 0.\n\n"
        f"Selecciona el número de semanas para los planes de pago:",
        reply_markup=reply_markup
    )

    # Mostrar opciones de semanas
    keyboard = [
        [InlineKeyboardButton("🔄 4 Semanas", callback_data="semanas_4")],
        [InlineKeyboardButton("🔄 8 Semanas", callback_data="semanas_8")],
        [InlineKeyboardButton("🔄 12 Semanas", callback_data="semanas_12")],
        [InlineKeyboardButton("🔄 16 Semanas", callback_data="semanas_16")],
        [InlineKeyboardButton("🔄 20 Semanas", callback_data="semanas_20")],
        [InlineKeyboardButton("✏️ Personalizado", callback_data="semanas_personalizado")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT semanas, contador_activo FROM config_pagos LIMIT 1")
    config = cursor.fetchone()
    conn.close()
    
    semanas_actuales = config[0] if config else 10
    contador_activo = config[1] if config else True
    
    await update.message.reply_text(
        f"⚙️ **CONFIGURAR SEMANAS DE PAGO**\n\n"
        f"🔢 **Actual:** {semanas_actuales} semanas\n"
        f"📊 **Contador:** {'🟢 ACTIVO' if contador_activo else '🔴 PAUSADO'}\n\n"
        f"Selecciona el número de semanas para los planes de pago:",
        reply_markup=reply_markup
    )

# =============================================
# FUNCIONES ADICIONALES PARA PAGOS
# =============================================

async def verpagostodos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra TODOS los pagos con opciones simplificadas (solo admin)"""
    if update.effective_user.id != 5908252094:
        await update.message.reply_text("❌ No tienes permisos de administrador")
        return
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.id, p.user_id, u.first_name, u.last_name, p.referencia, p.monto, p.fecha, p.estado 
        FROM pagos p 
        LEFT JOIN usuarios u ON p.user_id = u.user_id 
        ORDER BY p.fecha DESC
        LIMIT 50
    """)
    pagos = cursor.fetchall()
    conn.close()
    
    if not pagos:
        await update.message.reply_text("📭 No hay pagos registrados en el sistema")
        return
    
    mensaje = "📋 **TODOS LOS PAGOS - LISTA COMPLETA**\n\n"
    
    for pago_id, user_id, first_name, last_name, referencia, monto, fecha, estado in pagos:
        nombre_completo = f"{first_name or ''} {last_name or ''}".strip()
        
        # Iconos según estado
        icono = "✅" if estado == "aprobado" else "⏳" if estado == "pendiente" else "❌"
        
        mensaje += f"{icono} **ID Pago:** {pago_id}\n"
        mensaje += f"👤 **Usuario:** {nombre_completo or 'N/A'} (ID: {user_id})\n"
        mensaje += f"💰 **Monto:** ${monto:.2f}\n"
        mensaje += f"🔢 **Referencia:** {referencia}\n"
        mensaje += f"📅 **Fecha:** {fecha.strftime('%d/%m/%Y %H:%M')}\n"
        mensaje += f"📊 **Estado:** {estado}\n"
        mensaje += f"👁️ /verpago_{pago_id} | 🗑️ /borrarpago_{pago_id}\n"
        mensaje += "━━━━━━━━━━━━━━━━━━━━\n\n"
    
    mensaje += "💡 **Leyenda:** ✅ Aprobado | ⏳ Pendiente | ❌ Rechazado"
    
    await update.message.reply_text(mensaje)

async def verpago_detalle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ver detalles de un pago específico (admin)"""
    if update.effective_user.id != 5908252094:
        await update.message.reply_text("❌ No tienes permisos de administrador")
        return

    command_text = update.message.text
    try:
        pago_id = command_text.split('_')[1]
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.id, p.user_id, u.first_name, u.last_name, p.referencia, p.monto, p.fecha, p.estado, p.user_name, p.file_id
            FROM pagos p 
            LEFT JOIN usuarios u ON p.user_id = u.user_id 
            WHERE p.id = %s
        """, (pago_id,))
        pago = cursor.fetchone()
        conn.close()
        
        if pago:
            pago_id, user_id, first_name, last_name, referencia, monto, fecha, estado, user_name, file_id = pago
            nombre_completo = f"{first_name or ''} {last_name or ''}".strip()
            
            # PRIMERO enviar la imagen si existe
            if file_id:
                try:
                    await update.message.reply_photo(
                        photo=file_id,
                        caption=f"📸 **Comprobante de pago**\n🆔 ID Pago: {pago_id}"
                    )
                except Exception as e:
                    print(f"❌ Error al enviar imagen: {e}")
                    await update.message.reply_text("❌ No se pudo cargar la imagen del comprobante")
            
            # LUEGO enviar los detalles en texto
            mensaje = (
                f"📄 **DETALLES DEL PAGO**\n\n"
                f"🆔 **ID Pago:** {pago_id}\n"
                f"👤 **Usuario:** {nombre_completo or 'N/A'}\n"
                f"📱 **Username:** @{user_name or 'No tiene'}\n"
                f"🆔 **User ID:** {user_id}\n"
                f"💰 **Monto:** ${monto:.2f}\n"
                f"🔢 **Referencia:** {referencia}\n"
                f"📅 **Fecha:** {fecha.strftime('%d/%m/%Y %H:%M')}\n"
                f"📊 **Estado:** {estado}\n"
                f"📸 **Comprobante:** {'✅' if file_id else '❌ No disponible'}\n\n"
                f"🛠️ **Acciones:**\n"
                f"🗑️ /borrarpago_{pago_id} - Eliminar este pago\n"
                f"📋 /verpagostodos - Volver a la lista"
            )
            
            await update.message.reply_text(mensaje)
        else:
            await update.message.reply_text("❌ Pago no encontrado")
            
    except Exception as e:
        print(f"❌ Error en verpago_detalle: {e}")
        await update.message.reply_text("❌ Error al mostrar el pago")

async def borrarpago_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Eliminar pago con confirmación (admin)"""
    if update.effective_user.id != 5908252094:
        await update.message.reply_text("❌ No tienes permisos de administrador")
        return

    command_text = update.message.text
    try:
        pago_id = command_text.split('_')[1]
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.id, p.user_id, u.first_name, u.last_name, p.referencia, p.monto, p.estado
            FROM pagos p 
            LEFT JOIN usuarios u ON p.user_id = u.user_id 
            WHERE p.id = %s
        """, (pago_id,))
        pago = cursor.fetchone()
        conn.close()
        
        if pago:
            pago_id, user_id, first_name, last_name, referencia, monto, estado = pago
            nombre_completo = f"{first_name or ''} {last_name or ''}".strip()
            
            mensaje = (
                f"🗑️ **ELIMINAR PAGO - CONFIRMACIÓN**\n\n"
                f"🆔 **ID Pago:** {pago_id}\n"
                f"👤 **Usuario:** {nombre_completo or 'N/A'}\n"
                f"💰 **Monto:** ${monto:.2f}\n"
                f"🔢 **Referencia:** {referencia}\n"
                f"📊 **Estado:** {estado}\n\n"
                f"⚠️ **¿Estás seguro de eliminar este pago?**\n"
                f"Esta acción no se puede deshacer."
            )
            
            keyboard = [
                [InlineKeyboardButton("✅ SÍ, ELIMINAR", callback_data=f"borrarpago_si_{pago_id}")],
                [InlineKeyboardButton("❌ CANCELAR", callback_data=f"borrarpago_no_{pago_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(mensaje, reply_markup=reply_markup)
        else:
            await update.message.reply_text("❌ Pago no encontrado")
            
    except Exception as e:
        print(f"❌ Error en borrarpago_admin: {e}")
        await update.message.reply_text("❌ Error al procesar la eliminación")

# =============================================
# MANEJO DE BOTONES GENERALES
# =============================================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja los botones de confirmación"""
    query = update.callback_query
    await query.answer()
    
    print(f"🟡 BOTÓN PRESIONADO: {query.data}")
    user_id = query.from_user.id

    # CONFIGURAR SEMANAS (SOLO ADMIN)
    if query.data.startswith("semanas_"):
        if user_id != 5908252094:
            await query.answer("❌ No tienes permisos", show_alert=True)
            return
            
        if query.data == "semanas_personalizado":
            context.user_data['configurando_semanas'] = True
            await query.edit_message_text(
                "🔢 **CONFIGURAR SEMANAS PERSONALIZADAS**\n\n"
                "Envía el número de semanas deseado (ejemplo: 15):\n\n"
                "⚠️ **Nota:** Todos los contadores se reiniciarán a 0 y se recalcularán los pagos."
            )
            return
            
        try:
            semanas = int(query.data.split('_')[1])
            
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # 1. Actualizar configuración
            cursor.execute("UPDATE config_pagos SET semanas = %s", (semanas,))
            
            # 2. ✅ RECALCULAR TODOS LOS PLANES CON LAS NUEVAS SEMANAS
            cursor.execute("SELECT id, productos_json FROM planes_pago WHERE estado = 'activo'")
            planes = cursor.fetchall()
            
            planes_actualizados = 0
            for plan_id, productos_json in planes:
                if productos_json:
                    # Convertir JSON si es necesario
                    if isinstance(productos_json, str):
                        productos_dict = json.loads(productos_json)
                    else:
                        productos_dict = productos_json
                    
                    # Calcular nuevo total
                    total_nuevo = 0
                    for producto_id, cantidad in productos_dict.items():
                        cursor.execute("SELECT precio FROM productos WHERE id = %s", (int(producto_id),))
                        producto = cursor.fetchone()
                        if producto:
                            total_nuevo += producto[0] * cantidad
                    
                    # Calcular nuevo pago semanal
                    pago_semanal_nuevo = total_nuevo / semanas if semanas > 0 else 0
                    
                    # Actualizar el plan
                    cursor.execute("""
                        UPDATE planes_pago 
                        SET semanas_completadas = 0,
                            fecha_ultimo_pago = CURRENT_TIMESTAMP,
                            total = %s,
                            semanas = %s,
                            pago_semanal = %s
                        WHERE id = %s
                    """, (total_nuevo, semanas, pago_semanal_nuevo, plan_id))
                    
                    planes_actualizados += 1
            
            conn.commit()
            conn.close()

            await query.edit_message_text(
                f"✅ **Configuración actualizada y planes recalculados**\n\n"
                f"🔢 **Nuevas semanas de pago:** {semanas}\n"
                f"🔄 **Planes actualizados:** {planes_actualizados}\n\n"
                f"Todos los planes activos han sido:\n"
                f"• 🔄 Reiniciados a semana 0\n"
                f"• 💰 Recalculados con {semanas} semanas\n"
                f"• 📊 Actualizados los pagos semanales\n\n"
                f"El sistema comenzará desde el inicio con {semanas} semanas."
            )
            
        except Exception as e:
            print(f"❌ Error al configurar semanas: {e}")
            await query.edit_message_text("❌ Error al configurar las semanas")

    # EDITAR PRODUCTO (ADMIN)
    elif query.data.startswith("editar_"):
        if user_id != 5908252094:
            await query.answer("❌ No tienes permisos", show_alert=True)
            return
            
        partes = query.data.split('_')
        tipo = partes[1]
        producto_id = partes[2]
        
        context.user_data['editando_campo'] = {
            'tipo': tipo,
            'producto_id': producto_id
        }
        
        mensajes = {
            'nombre': "Envía el nuevo nombre del producto:",
            'precio': "Envía el nuevo precio del producto:",
            'descripcion': "Envía la nueva descripción del producto:",
            'categoria': "Envía la nueva categoría del producto:"
        }
        
        await query.edit_message_text(f"✏️ **EDITAR {tipo.upper()}**\n\n{mensajes.get(tipo, 'Envía el nuevo valor:')}")

    # ELIMINAR PRODUCTO (ADMIN)
    elif query.data.startswith("eliminar_si_"):
        if user_id != 5908252094:
            await query.answer("❌ No tienes permisos", show_alert=True)
            return
            
        producto_id = query.data.split('_')[2]
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE productos SET estado = 'inactivo' WHERE id = %s", (producto_id,))
        conn.commit()
        conn.close()
        
        await query.edit_message_text("✅ **Producto eliminado**\n\nEl producto ha sido marcado como inactivo.")
        
    elif query.data.startswith("eliminar_no_"):
        await query.edit_message_text("❌ **Eliminación cancelada**\n\nEl producto se mantiene activo.")

    # COMPARTIR TELÉFONO
    elif query.data == "compartir_telefono":
        await query.edit_message_text(
            "📱 **Compartir teléfono**\n\n"
            "Por favor comparte tu número de teléfono usando el botón de contacto "
            "o escribe tu número manualmente:"
        )
        
    # ELIMINAR USUARIO CONFIRMADO
    elif query.data.startswith("eliminar_usuario_si_"):
        if user_id != 5908252094:
            await query.answer("❌ No tienes permisos", show_alert=True)
            return
            
        user_id_eliminar = query.data.split('_')[3]
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # 1. Marcar planes como eliminados
            cursor.execute("UPDATE planes_pago SET estado = 'eliminado' WHERE user_id = %s", (user_id_eliminar,))
            
            # 2. ELIMINAR DATOS DE PUNTOS (NUEVO)
            cursor.execute("DELETE FROM usuarios_puntos WHERE user_id = %s", (user_id_eliminar,))
            cursor.execute("DELETE FROM puntos_historial WHERE user_id = %s", (user_id_eliminar,))
            
            # 3. Actualizar referidos (marcar como eliminados o mantener según prefieras)
            cursor.execute("UPDATE referidos SET estado = 'eliminado' WHERE user_id_referidor = %s OR user_id_referido = %s", 
                        (user_id_eliminar, user_id_eliminar))
            
            # 4. Eliminar usuario
            cursor.execute("DELETE FROM usuarios WHERE user_id = %s", (user_id_eliminar,))
            
            conn.commit()
            conn.close()
            
            await query.edit_message_text(
                f"✅ **Usuario eliminado completamente**\n\n"
                f"🆔 **ID Usuario:** {user_id_eliminar}\n\n"
                f"Se han eliminado TODOS los datos relacionados:\n"
                f"• 👤 Datos de usuario\n"
                f"• 📋 Planes de pago\n"
                f"• ⭐ Sistema de puntos\n"
                f"• 📈 Historial de puntos\n"
                f"• 👥 Referidos asociados"
            )
            
        except Exception as e:
            print(f"❌ Error al eliminar usuario: {e}")
            await query.edit_message_text("❌ Error al eliminar el usuario")

    
    elif query.data.startswith("eliminar_usuario_no_"):
        await query.edit_message_text("❌ **Eliminación cancelada**\n\nEl usuario se mantiene activo.")
        
    # BORRAR PAGO CONFIRMADO
    elif query.data.startswith("borrarpago_si_"):
        if user_id != 5908252094:
            await query.answer("❌ No tienes permisos", show_alert=True)
            return
            
        pago_id = query.data.split('_')[2]
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM pagos WHERE id = %s", (pago_id,))
            conn.commit()
            conn.close()
            
            await query.edit_message_text(
                f"✅ **Pago eliminado correctamente**\n\n"
                f"🆔 **ID Pago:** {pago_id}\n\n"
                f"El pago ha sido eliminado permanentemente de la base de datos."
            )
            
        except Exception as e:
            print(f"❌ Error al eliminar pago: {e}")
            await query.edit_message_text("❌ Error al eliminar el pago")
    
    elif query.data.startswith("borrarpago_no_"):
        await query.edit_message_text("❌ **Eliminación cancelada**\n\nEl pago se mantiene en el sistema.")
        
        # VACIAR PUNTOS CONFIRMADO
    elif query.data == "vaciar_puntos_si":
        if user_id != 5908252094:
            await query.answer("❌ No tienes permisos", show_alert=True)
            return
            
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # 1. Vaciar tabla de usuarios_puntos
            cursor.execute("DELETE FROM usuarios_puntos")
            usuarios_eliminados = cursor.rowcount
            
            # 2. Vaciar historial de puntos
            cursor.execute("DELETE FROM puntos_historial")
            historial_eliminado = cursor.rowcount
            
            # 3. Vaciar tabla de referidos
            cursor.execute("DELETE FROM referidos")
            referidos_eliminados = cursor.rowcount
            
            conn.commit()
            conn.close()
            
            await query.edit_message_text(
                f"✅ **Sistema de puntos vaciado completamente**\n\n"
                f"🗑️ **Datos eliminados:**\n"
                f"• 👥 {usuarios_eliminados} usuarios de puntos\n"
                f"• 📊 {historial_eliminado} registros de historial\n"
                f"• 👥 {referidos_eliminados} referidos\n\n"
                f"El sistema de puntos ha sido reiniciado a cero."
            )
            
        except Exception as e:
            print(f"❌ Error al vaciar puntos: {e}")
            await query.edit_message_text("❌ Error al vaciar el sistema de puntos")

    # CANCELAR VACIADO DE PUNTOS
    elif query.data == "vaciar_puntos_no":
        await query.edit_message_text("❌ **Operación cancelada**\n\nEl sistema de puntos se mantiene intacto.")
        
        
        # BOTONES PARA INCREMENTO MANUAL
    elif query.data == "reanudar_y_incrementar":
        if user_id != 5908252094:
            await query.answer("❌ No tienes permisos", show_alert=True)
            return
            
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Reanudar contador
            cursor.execute("UPDATE config_pagos SET contador_activo = TRUE")
            
            # Incrementar semanas
            cursor.execute("""
                UPDATE planes_pago 
                SET semanas_completadas = semanas_completadas + 1,
                    fecha_ultimo_pago = CURRENT_TIMESTAMP
                WHERE estado = 'activo' 
                AND contador_pausado = FALSE
                AND semanas_completadas < semanas
            """)
            planes_afectados = cursor.rowcount
            
            conn.commit()
            conn.close()
            
            await query.edit_message_text(
                f"✅ **Contador reanudado e incremento realizado**\n\n"
                f"📈 {planes_afectados} planes incrementados +1 semana\n"
                f"🟢 Contador global REANUDADO"
            )
            
        except Exception as e:
            print(f"❌ Error: {e}")
            await query.edit_message_text("❌ Error al procesar")
            
    elif query.data == "incrementar_force":
        if user_id != 5908252094:
            await query.answer("❌ No tienes permisos", show_alert=True)
            return
            
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Solo incrementar sin reanudar contador
            cursor.execute("""
                UPDATE planes_pago 
                SET semanas_completadas = semanas_completadas + 1,
                    fecha_ultimo_pago = CURRENT_TIMESTAMP
                WHERE estado = 'activo' 
                AND semanas_completadas < semanas
            """)
            planes_afectados = cursor.rowcount
            
            conn.commit()
            conn.close()
            
            await query.edit_message_text(
                f"🚀 **INCREMENTO FORZADO**\n\n"
                f"✅ {planes_afectados} planes incrementados +1 semana\n"
                f"⏸️ Contador global sigue PAUSADO"
            )
            
        except Exception as e:
            print(f"❌ Error: {e}")
            await query.edit_message_text("❌ Error al forzar incremento")
        
# =============================================
# FUNCIONES DE MANEJO DE MENSAJES
# =============================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"🔵 MENSAJE RECIBIDO: {update.message.text}")
    print(f"🔵 USER DATA: {context.user_data}")
    
    user_id = update.effective_user.id
    
    # 1. Verificar si está registrando usuario
    if context.user_data.get('registrando_usuario'):
        await handle_phone_registration(update, context)
        return
    
    # 2. Verificar si está agregando producto (admin)
    if context.user_data.get('agregando_producto'):
        await handle_agregar_producto(update, context)
        return
    
    # 3. Verificar si está editando producto (admin)
    if context.user_data.get('editando_campo'):
        await handle_editar_producto(update, context)
        return
    
    # 4. Verificar si está configurando semanas (admin)
    if context.user_data.get('configurando_semanas'):
        await handle_configurar_semanas(update, context)
        return
    
    # 5. Verificar si es motivo de rechazo
    if context.user_data.get('rechazando_pago'):
        await handle_rechazo_motivo(update, context)
        return
    
    # 6. Verificar si estamos esperando datos de pago
    if context.user_data.get('esperando_datos_pago'):
        print("✅ SÍ estaba esperando datos de pago")
        
        # Procesar datos del pago
        texto = update.message.text
        lineas = texto.split('\n')
        datos = {}
        
        print(f"📝 Líneas detectadas: {lineas}")
        
        for linea in lineas:
            linea = linea.strip()
            if ':' in linea:
                partes = linea.split(':', 1)
                clave = partes[0].strip().lower()
                valor = partes[1].strip()
                datos[clave] = valor
                print(f"📋 Dato extraído: '{clave}' = '{valor}'")

        # Verificar datos
        if 'nombre' in datos and 'referencia' in datos and 'monto' in datos:
            context.user_data['datos_pago'] = datos
            await update.message.reply_text(
                "✅ Datos recibidos. Ahora por favor envía la imagen del comprobante."
            )
            print("🎉 TODOS los datos completos - listo para imagen")
            print(f"🎉 Datos guardados: {datos}")
        else:
            print(f"❌ Datos incompletos. Tenemos: {list(datos.keys())}")
            await update.message.reply_text(
                "❌ Formato incorrecto. Usa:\n\n"
                "Nombre: Tu nombre completo\n"
                "Referencia: Número de referencia\n"
                "Monto: Cantidad pagada"
            )
        
        context.user_data['esperando_datos_pago'] = False
        context.user_data['esperando_imagen'] = True
        print(f"🟡 USER DATA después de procesar texto: {context.user_data}")
        
    else:
        print("❌ NO estaba esperando datos de pago - mensaje normal")
        await update.message.reply_text(
            "Usa /pagarealizado para registrar un pago o /catalogo para ver productos"
        )

# =============================================
# FUNCIONES DE MANEJO DE PRODUCTOS
# =============================================

async def handle_agregar_producto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja el proceso de agregar producto completo"""
    if not context.user_data.get('agregando_producto'):
        return
    
    texto = update.message.text
    lineas = texto.split('\n')
    datos = {}
    
    for linea in lineas:
        linea = linea.strip()
        if ':' in linea:
            partes = linea.split(':', 1)
            clave = partes[0].strip().lower()
            valor = partes[1].strip()
            datos[clave] = valor

    # Verificar datos mínimos
    if 'nombre' in datos and 'precio' in datos:
        try:
            nombre = datos['nombre']
            precio = float(datos['precio'])
            descripcion = datos.get('descripción', datos.get('descripcion', ''))
            categoria = datos.get('categoría', datos.get('categoria', 'General'))
            
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO productos (nombre, precio, descripcion, categoria) VALUES (%s, %s, %s, %s)",
                (nombre, precio, descripcion, categoria)
            )
            conn.commit()
            conn.close()
            
            context.user_data['agregando_producto'] = False
            
            await update.message.reply_text(
                f"✅ **Producto agregado exitosamente**\n\n"
                f"📦 **Nombre:** {nombre}\n"
                f"💰 **Precio:** ${precio:.2f}\n"
                f"📝 **Descripción:** {descripcion or 'Sin descripción'}\n"
                f"📂 **Categoría:** {categoria}\n\n"
                f"Los usuarios ya pueden verlo en el catálogo con /catalogo"
            )
            print(f"✅ Producto agregado: {nombre} - ${precio}")
            
        except ValueError:
            await update.message.reply_text("❌ El precio debe ser un número válido")
        except Exception as e:
            print(f"❌ Error al agregar producto: {e}")
            await update.message.reply_text("❌ Error al agregar el producto")
    else:
        await update.message.reply_text(
            "❌ Formato incorrecto. Usa:\n\n"
            "Nombre: Nombre del producto\n"
            "Precio: 100\n"
            "Descripción: Descripción opcional\n"
            "Categoría: Categoría opcional"
        )

async def handle_editar_producto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja la edición de productos"""
    if not context.user_data.get('editando_campo'):
        return
    
    campo = context.user_data['editando_campo']
    nuevo_valor = update.message.text.strip()
    producto_id = campo['producto_id']
    tipo = campo['tipo']
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if tipo == 'precio':
            nuevo_valor = float(nuevo_valor)
            cursor.execute("UPDATE productos SET precio = %s WHERE id = %s", (nuevo_valor, producto_id))
        elif tipo == 'nombre':
            cursor.execute("UPDATE productos SET nombre = %s WHERE id = %s", (nuevo_valor, producto_id))
        elif tipo == 'descripcion':
            cursor.execute("UPDATE productos SET descripcion = %s WHERE id = %s", (nuevo_valor, producto_id))
        elif tipo == 'categoria':
            cursor.execute("UPDATE productos SET categoria = %s WHERE id = %s", (nuevo_valor, producto_id))
        
        conn.commit()
        conn.close()
        
        context.user_data['editando_campo'] = None
        
        await update.message.reply_text(f"✅ **{tipo.capitalize()} actualizado correctamente**")
        
    except ValueError:
        await update.message.reply_text("❌ El precio debe ser un número válido")
    except Exception as e:
        print(f"❌ Error al editar producto: {e}")
        await update.message.reply_text("❌ Error al actualizar el producto")

async def handle_configurar_semanas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja la configuración personalizada de semanas con reinicio y recálculo automático"""
    if not context.user_data.get('configurando_semanas'):
        return
    
    if update.effective_user.id != 5908252094:
        await update.message.reply_text("❌ No tienes permisos de administrador")
        context.user_data['configurando_semanas'] = None
        return
    
    try:
        semanas = int(update.message.text.strip())
        
        if semanas < 1:
            await update.message.reply_text("❌ El número de semanas debe ser mayor a 0")
            return
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 1. Actualizar configuración
        cursor.execute("UPDATE config_pagos SET semanas = %s", (semanas,))
        
        # 2. ✅ RECALCULAR TODOS LOS PLANES CON LAS NUEVAS SEMANAS
        cursor.execute("SELECT id, productos_json FROM planes_pago WHERE estado = 'activo'")
        planes = cursor.fetchall()
        
        planes_actualizados = 0
        for plan_id, productos_json in planes:
            if productos_json:
                # Convertir JSON si es necesario
                if isinstance(productos_json, str):
                    productos_dict = json.loads(productos_json)
                else:
                    productos_dict = productos_json
                
                # Calcular nuevo total
                total_nuevo = 0
                for producto_id, cantidad in productos_dict.items():
                    cursor.execute("SELECT precio FROM productos WHERE id = %s", (int(producto_id),))
                    producto = cursor.fetchone()
                    if producto:
                        total_nuevo += producto[0] * cantidad
                
                # Calcular nuevo pago semanal
                pago_semanal_nuevo = total_nuevo / semanas if semanas > 0 else 0
                
                # Actualizar el plan
                cursor.execute("""
                    UPDATE planes_pago 
                    SET semanas_completadas = 0,
                        fecha_ultimo_pago = CURRENT_TIMESTAMP,
                        total = %s,
                        semanas = %s,
                        pago_semanal = %s
                    WHERE id = %s
                """, (total_nuevo, semanas, pago_semanal_nuevo, plan_id))
                
                planes_actualizados += 1
        
        conn.commit()
        conn.close()
        
        context.user_data['configurando_semanas'] = None
        
        await update.message.reply_text(
            f"✅ **Configuración actualizada y planes recalculados**\n\n"
            f"🔢 **Nuevas semanas de pago:** {semanas}\n"
            f"🔄 **Planes actualizados:** {planes_actualizados}\n\n"
            f"Todos los planes activos han sido:\n"
            f"• 🔄 Reiniciados a semana 0\n"
            f"• 💰 Recalculados con {semanas} semanas\n"
            f"• 📊 Actualizados los pagos semanales\n\n"
            f"El sistema comenzará desde el inicio con {semanas} semanas."
        )
        
    except ValueError:
        await update.message.reply_text("❌ El número de semanas debe ser un número válido")
    except Exception as e:
        print(f"❌ Error al configurar semanas: {e}")
        await update.message.reply_text("❌ Error al configurar las semanas")

# =============================================
# MANEJO DE COMANDOS DINÁMICOS
# =============================================

async def handle_dynamic_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja comandos dinámicos"""
    command_text = update.message.text
    print(f"🟡 COMANDO DINÁMICO DETECTADO: {command_text}")
    
    if command_text.startswith('/verimagen_'):
        await verimagen_admin(update, context)
    elif command_text.startswith('/confirmar_'):
        await confirmar_pago(update, context)
    elif command_text.startswith('/rechazar_'):
        await rechazar_pago(update, context)
    elif command_text.startswith('/borrar_'):
        await borrar_pago(update, context)
    elif command_text.startswith('/borrarusuario_'):
        await borrarusuario(update, context)
    # 🆕 NUEVOS COMANDOS DE ASIGNACIÓN
    elif command_text.startswith('/asignar_'):
        await asignar_productos(update, context)
    elif command_text.startswith('/editarproducto_'):
        await editar_producto(update, context)
    elif command_text.startswith('/eliminarproducto_'):
        await eliminar_producto(update, context)
    elif command_text.startswith('/verpago_'):
        await verpago_detalle(update, context)
    elif command_text.startswith('/borrarpago_'):
        await borrarpago_admin(update, context)
    # 🆕 NUEVOS COMANDOS DE SISTEMA DE PUNTOS
    elif command_text.startswith('/verificarreferido_'):
        await verificar_referido(update, context)
    elif command_text.startswith('/rechazarreferido_'):
        await rechazar_referido(update, context)
    elif command_text.startswith('/verpuntosusuario_'):
        await ver_puntos_usuario(update, context)
    else:
        await update.message.reply_text("❌ Comando no reconocido")

# =============================================
# 🎯 FUNCIÓN MAIN ACTUALIZADA
# =============================================

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja errores globales del bot"""
    error = context.error
    
    if isinstance(error, telegram.error.TimedOut):
        print("⏰ Timeout en conexión con Telegram - Reintentando...")
        # No hacer nada, el bot reintentará automáticamente
    elif isinstance(error, telegram.error.NetworkError):
        print("🌐 Error de red - Reintentando...")
    else:
        print(f'❌ Error no manejado: {error}')


def main():
    """Función principal - BOT EN HILO PRINCIPAL"""
    print("🎯 INICIANDO BOT DE TELEGRAM EN RENDER...")
    
    # 1. Inicializar base de datos
    print("🗄️ Inicializando base de datos...")
    init_db()
    verificar_base_datos()
    
    # 2. Configurar el bot de Telegram
    print("🤖 Configurando bot de Telegram...")
    
    application = (
        Application.builder()
        .token(TOKEN)
        .read_timeout(30)
        .write_timeout(30) 
        .connect_timeout(30)
        .pool_timeout(30)
        .build()
    )
    
    # =============================================
    # 🎯 TODOS LOS HANDLERS COMPLETOS
    # =============================================
    
    # 1. Handlers de comandos básicos para usuarios
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("cancelar", cancelar))
    application.add_handler(CommandHandler("miperfil", miperfil))
    application.add_handler(CommandHandler("pagarealizado", pagarealizado))
    application.add_handler(CommandHandler("mistatus", mistatus))
    
    # 🆕 2. Handlers para sistema de puntos y referidos
    application.add_handler(CommandHandler("mispuntos", mispuntos))
    application.add_handler(CommandHandler("referidos", referidos))
    
    # 3. Handlers para sistema de asignación administrativa
    application.add_handler(CommandHandler("verasignaciones", ver_asignaciones))
    
    # 4. Handlers modificados para productos (sin carrito)
    application.add_handler(CommandHandler("catalogo", catalogo_solo_lectura))
    application.add_handler(CommandHandler("misplanes", mis_planes_mejorado))
    
    # 5. Handlers de administrador
    application.add_handler(CommandHandler("adminverproductos", admin_ver_productos))
    application.add_handler(CommandHandler("adminagregarproducto", admin_agregar_producto))
    application.add_handler(CommandHandler("verpagos", verpagos))
    application.add_handler(CommandHandler("verpagostodos", verpagostodos))
    application.add_handler(CommandHandler("verusuarios", verusuarios))
    application.add_handler(CommandHandler("estadocontador", estado_contador))
    application.add_handler(CommandHandler("pausarcontador", pausar_contador))
    application.add_handler(CommandHandler("reanudarcontador", reanudar_contador))
    application.add_handler(CommandHandler("configurarsemanas", configurar_semanas))
    
    # 🆕 6. Handlers para sistema de puntos (admin)
    application.add_handler(CommandHandler("rankingpuntos", ranking_puntos))
    application.add_handler(CommandHandler("verreferidos", ver_referidos_pendientes))
    application.add_handler(CommandHandler("vaciarranking", vaciar_ranking_puntos))
    
    # 7. NUEVOS HANDLERS PARA INCREMENTO DE SEMANAS
    application.add_handler(CommandHandler("incrementarsemana", incrementar_semana_manual))
    application.add_handler(CommandHandler("forzarincremento", forzar_incremento))
    
    # 8. Handler para comandos dinámicos de asignación
    application.add_handler(MessageHandler(
        filters.Regex(r'^\/(verimagen|confirmar|rechazar|borrar|borrarusuario|asignar|editarproducto|eliminarproducto|verpago|borrarpago|verificarreferido|rechazarreferido|verpuntosusuario)_\d+'),
        handle_dynamic_commands
    ))
    
    # 9. Handler para mensajes normales
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_message
    ))
    
    # 10. Handlers de archivos
    application.add_handler(MessageHandler(filters.PHOTO, handle_image))
    application.add_handler(MessageHandler(filters.Document.IMAGE, handle_image))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_all_documents))
    
    # 11. Handler de botones de asignación
    application.add_handler(CallbackQueryHandler(button_handler_asignacion, pattern=r'^asignar_.*'))
    
    # 🆕 12. Handler de botones para sistema de puntos
    application.add_handler(CallbackQueryHandler(button_handler_puntos, pattern=r'^(compartir_codigo|ver_mis_puntos|ir_a_referidos|actualizar_puntos)$'))
    
    # 13. Handler de botones generales (para otros botones)
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # ✅ AGREGAR JOB PARA INCREMENTO AUTOMÁTICO
    try:
        if hasattr(application, 'job_queue') and application.job_queue is not None:
            application.job_queue.run_repeating(
                incrementar_semanas_automatico, 
                interval=604800,  # 7 días en segundos
                first=10  # Empezar después de 10 segundos
            )
            print("✅ JobQueue configurado correctamente para incremento automático")
            job_queue_status = "ACTIVADO (cada 7 días)"
        else:
            print("⚠️ JobQueue no disponible. El incremento automático no funcionará.")
            job_queue_status = "NO DISPONIBLE"
    except Exception as e:
        print(f"❌ Error al configurar JobQueue: {e}")
        job_queue_status = "ERROR EN CONFIGURACIÓN"
    
    # ✅ Manejo de errores
    application.add_error_handler(error_handler)
    
    print("✅ BOT CONFIGURADO CORRECTAMENTE")
    print(f"🔄 INCREMENTO AUTOMÁTICO: {job_queue_status}")
    
    # 3. Iniciar Flask en un hilo separado (para Render)
    print("🌐 Iniciando servidor web Flask en segundo plano...")
    
    def run_flask():
        port = int(os.environ.get('PORT', 10000))
        print(f"🌐 Flask ejecutándose en puerto {port}")
        app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
    
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # 4. Iniciar el bot en el HILO PRINCIPAL
    print("\n" + "="*60)
    print("🤖 BOT DE PLANES DE PAGO - SISTEMA COMPLETO CON PUNTOS")
    print("="*60)
    print("📍 COMANDOS PARA USUARIOS:")
    print("   /start - Registrarse en el sistema")
    print("   /catalogo - Ver productos (solo lectura)")
    print("   /misplanes - Ver plan asignado")
    print("   /miperfil - Información personal")
    print("   /mispuntos - Sistema de puntos")
    print("   /referidos - Invitar amigos")
    print("   /pagarealizado - Registrar pago")
    print("   /mistatus - Estado de mis pagos")
    print("\n📍 COMANDOS PARA ADMIN (5908252094):")
    print("   /verasignaciones - Ver todas las asignaciones")
    print("   /asignar_X - Asignar productos a usuario")
    print("   /adminverproductos - Ver catálogo completo")
    print("   /adminagregarproducto - Agregar producto")
    print("   /verpagos - Ver pagos pendientes")
    print("   /verpagostodos - Ver TODOS los pagos")
    print("   /verusuarios - Ver todos los usuarios")
    print("   /estadocontador - Estado del sistema")
    print("   /pausarcontador - Pausar contador global")
    print("   /reanudarcontador - Reanudar contador global")
    print("   /configurarsemanas - Configurar semanas")
    print("   /incrementarsemana - Incremento manual")
    print("   /forzarincremento - Forzar incremento")
    print("   /rankingpuntos - Ranking de puntos")
    print("   /verreferidos - Referidos pendientes")
    print("   /verpuntosusuario_ID - Puntos de usuario")
    print("   /vaciarranking - Vaciar sistema de puntos")
    print("="*60 + "\n")
    
    print("🟢 BOT INICIADO - Escuchando mensajes...")
    print("📍 Los usuarios pueden escribir /start al bot")
    print("📍 Servicio web activo en: https://bot-sususemanal.onrender.com")
    
    try:
        application.run_polling()
    except KeyboardInterrupt:
        print("⏹️ Bot detenido por el usuario")
    except Exception as e:
        print(f"❌ Error en el bot: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("🚀 INICIANDO SISTEMA COMPLETO...")
    
    # SOLUCIÓN: Invertir los hilos - Flask principal, bot en segundo plano
    import asyncio
    
    def run_bot():
        """Ejecutar el bot en su propio event loop"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            main()  # Tu función main original
        except Exception as e:
            print(f"❌ Error en bot: {e}")
    
    # Iniciar bot en segundo plano
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Iniciar Flask en el hilo principal (para Render)
    port = int(os.environ.get('PORT', 10000))
    print(f"🌐 Servidor web principal en puerto {port}")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)




