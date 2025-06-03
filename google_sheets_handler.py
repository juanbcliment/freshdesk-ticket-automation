import os
import json
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta

# --- Constantes (igual que antes para la hoja de agentes) ---
COL_AGENT_ID = 'Agent_ID'
COL_AGENT_NAME = 'Agent_name'
COL_STATUS = 'Status'
COL_DESCANSO_INICIO_HORA = 'Descanso_Inicio_Hora'
COL_SUFFIX_HORARIO1 = '_1'
COL_SUFFIX_HORARIO2 = '_2'
DURACION_DESCANSO_MINUTOS = 60 
FORMATO_HORA = "%H:%M"
DIAS_SEMANA_COLUMNAS = {
    0: 'Lunes', 1: 'Martes', 2: 'Miercoles', 3: 'Jueves',
    4: 'Viernes', 5: 'Sabado', 6: 'Domingo'
}
ESTADO_SHEET_ACTIVO = 'activo'

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def _parse_horario_string(horario_str):
    if not horario_str or str(horario_str).strip().lower() == 'off':
        return None, None
    for sep in [' a ', '-']: 
        if sep in str(horario_str):
            parts = str(horario_str).split(sep)
            if len(parts) == 2:
                try:
                    return parts[0].strip(), parts[1].strip()
                except ValueError:
                    return None, None
    return None, None

def _is_currently_on_shift(start_time_str, end_time_str, ahora_dt):
    if not start_time_str or not end_time_str:
        return False
    try:
        now_t = ahora_dt.time()
        start_t = datetime.strptime(start_time_str, FORMATO_HORA).time()
        end_t = datetime.strptime(end_time_str, FORMATO_HORA).time()
        
        if start_t <= end_t: 
            return start_t <= now_t < end_t
        else: 
            return now_t >= start_t or now_t < end_t
    except Exception as e:
        print(f"Error parseando turno individual '{start_time_str}-{end_time_str}': {e}")
        return False

def _is_on_active_break(descanso_inicio_hora_str, ahora_dt, duracion_descanso_min=DURACION_DESCANSO_MINUTOS):
    if not descanso_inicio_hora_str or str(descanso_inicio_hora_str).strip() == "":
        return False
    try:
        descanso_inicio_t = datetime.strptime(str(descanso_inicio_hora_str).strip(), FORMATO_HORA).time()
        
        # Crear un datetime naive para la hora de inicio del descanso en la fecha de ahora_dt
        naive_descanso_inicio_dt = datetime.combine(ahora_dt.date(), descanso_inicio_t)

        # Hacer que el datetime del descanso sea aware, usando la misma timezone que ahora_dt
        if ahora_dt.tzinfo is not None and ahora_dt.tzinfo.utcoffset(ahora_dt) is not None:
            # Si ahora_dt es timezone-aware (gracias a pytz)
            # Usamos el tzinfo de ahora_dt para localizar el datetime naive del descanso.
            # Esto es crucial si pytz.timezone.localize() fue usado para crear ahora_dt.
            # Si ahora_dt.tzinfo es un objeto timezone de pytz, tiene el método localize.
            if hasattr(ahora_dt.tzinfo, 'localize'):
                descanso_inicio_dt_actual = ahora_dt.tzinfo.localize(naive_descanso_inicio_dt)
            else:
                # Para timezones estándar (como las de datetime.timezone), se usa replace
                # pero esto puede ser problemático con DST. La mejor práctica es
                # asegurar que ahora_dt venga de pytz si se usa pytz.
                # Por simplicidad, si no es localizable (no es un tz de pytz), 
                # lo creamos con replace. Esto es menos robusto para DST.
                descanso_inicio_dt_actual = naive_descanso_inicio_dt.replace(tzinfo=ahora_dt.tzinfo)

        else:
            # Si ahora_dt es naive, descanso_inicio_dt_actual también será naive
            descanso_inicio_dt_actual = naive_descanso_inicio_dt
        
        descanso_fin_dt_actual = descanso_inicio_dt_actual + timedelta(minutes=duracion_descanso_min)

        # Ahora ambas (ahora_dt y descanso_xxx_dt_actual) deberían ser aware (o ambas naive)
        # y la comparación debería funcionar.
        if descanso_fin_dt_actual.date() == descanso_inicio_dt_actual.date():
            return descanso_inicio_dt_actual <= ahora_dt < descanso_fin_dt_actual
        else: 
            return ahora_dt >= descanso_inicio_dt_actual or ahora_dt < descanso_fin_dt_actual
            
    except ValueError: 
        print(f"Advertencia: Formato incorrecto para Descanso_Inicio_Hora: '{descanso_inicio_hora_str}'. No se considera en descanso.")
        return False
    except Exception as e:
        print(f"Error parseando descanso activo con inicio '{descanso_inicio_hora_str}': {e}")
        return False


def _get_current_datetime_with_timezone(timezone_str=None):
    try:
        import pytz # Asegurarse que pytz se importa aquí
        if timezone_str:
            try:
                tz = pytz.timezone(timezone_str)
                return datetime.now(tz) # Esto devuelve un datetime aware
            except pytz.UnknownTimeZoneError:
                print(f"Advertencia: Timezone '{timezone_str}' desconocido. Usando hora local del servidor (naive).")
                return datetime.now() # Fallback a naive datetime
        else:
            return datetime.now() # Hora local del servidor (naive)
    except ImportError:
        if timezone_str:
            print("Advertencia: Módulo 'pytz' no instalado. Timezone no se aplicará. Usando hora local del servidor (naive).")
        return datetime.now() # Fallback a naive datetime


def _cargar_configuracion_global_desde_sheet(client, planilla_nombre, hoja_config_nombre):
    config_global = {}
    try:
        hoja_config = client.open(planilla_nombre).worksheet(hoja_config_nombre)
        registros_config = hoja_config.get_all_records() 

        for fila in registros_config:
            clave = fila.get('ClaveConfig')
            valor1 = fila.get('ValorConfig1')
            if clave and valor1 is not None: 
                 config_global[clave.strip()] = str(valor1).strip()

        requeridos = ['HORARIO_ATENCION_INICIO', 'HORARIO_ATENCION_FIN', 
                      'MENSAJE_APERTURA', 'MENSAJE_CIERRE_ENCUESTA', 'MENSAJE_FUERA_HORARIO']
        for req_clave in requeridos:
            if req_clave not in config_global:
                print(f"Advertencia: Clave requerida '{req_clave}' no encontrada en la hoja '{hoja_config_nombre}'.")
        
        print(f"Configuración global cargada desde '{hoja_config_nombre}': {len(config_global)} elementos.")
        return config_global

    except gspread.exceptions.WorksheetNotFound:
        print(f"ERROR: Hoja de configuración global '{hoja_config_nombre}' no encontrada en la planilla '{planilla_nombre}'.")
    except Exception as e:
        print(f"ERROR cargando configuración global desde Google Sheets: {e}")
    return config_global


def ejecutar_actualizacion_caches(gs_config, archivos_estado_config):
    print("--- Iniciando Actualización de Caches desde Google Sheets ---")
    
    ruta_credenciales_gs = os.path.join(SCRIPT_DIR, gs_config['credentials_file'])
    planilla_nombre_gs = gs_config['planilla_nombre']
    hoja_agentes_nombre_gs = gs_config['hoja_horarios_agentes'] 
    hoja_config_global_nombre_gs = gs_config['hoja_configuracion_global']

    ruta_mapa_agentes_cache = os.path.join(SCRIPT_DIR, archivos_estado_config['mapa_agentes_cache'])
    ruta_agentes_operativos_cache = os.path.join(SCRIPT_DIR, archivos_estado_config['agentes_operativos_cache'])
    ruta_config_global_cache = os.path.join(SCRIPT_DIR, archivos_estado_config['configuracion_global_cache']) 

    agentes_operativos_ids = []
    todos_los_agentes_map = {}
    configuracion_global_sheet = {}

    try:
        scopes = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_file(ruta_credenciales_gs, scopes=scopes)
        client = gspread.authorize(creds)

        configuracion_global_sheet = _cargar_configuracion_global_desde_sheet(
            client, planilla_nombre_gs, hoja_config_global_nombre_gs
        )
        if configuracion_global_sheet:
            with open(ruta_config_global_cache, 'w', encoding='utf-8') as f:
                json.dump(configuracion_global_sheet, f, ensure_ascii=False, indent=2)
            print(f"Caché de configuración global guardada en: {ruta_config_global_cache}")
        else:
            print("No se pudo cargar la configuración global desde Sheets. No se actualizó la caché.")

        hoja_agentes = client.open(planilla_nombre_gs).worksheet(hoja_agentes_nombre_gs)
        registros_agentes = hoja_agentes.get_all_records()

        timezone_aplicacion = configuracion_global_sheet.get('TIMEZONE_APP')
        ahora_con_timezone = _get_current_datetime_with_timezone(timezone_aplicacion) # Esta función ahora puede devolver naive si pytz falla o no hay timezone_str
        
        # Imprimir si ahora_con_timezone es aware o naive para depuración
        if ahora_con_timezone.tzinfo is not None and ahora_con_timezone.tzinfo.utcoffset(ahora_con_timezone) is not None:
            print(f"Fecha y hora actual (Aware - {ahora_con_timezone.tzinfo}): {ahora_con_timezone.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        else:
            print(f"Fecha y hora actual (Naive - Local del Servidor): {ahora_con_timezone.strftime('%Y-%m-%d %H:%M:%S')}")


        dia_actual_num = ahora_con_timezone.weekday()
        prefijo_dia_col = DIAS_SEMANA_COLUMNAS.get(dia_actual_num)

        if not prefijo_dia_col:
            print(f"Error: No se pudo determinar el prefijo de columna para el día {dia_actual_num}.")
            return 

        col_h1_hoy = f"{prefijo_dia_col}{COL_SUFFIX_HORARIO1}" 
        col_h2_hoy = f"{prefijo_dia_col}{COL_SUFFIX_HORARIO2}" 

        for i, fila_agente in enumerate(registros_agentes):
            try:
                agent_id_str = str(fila_agente.get(COL_AGENT_ID, '')).strip()
                agent_name = str(fila_agente.get(COL_AGENT_NAME, '')).strip()
                if not agent_id_str or not agent_name:
                    continue

                agent_id = int(agent_id_str) 
                todos_los_agentes_map[str(agent_id)] = agent_name

                status_general = str(fila_agente.get(COL_STATUS, '')).strip().lower()
                
                h1_str_hoy = str(fila_agente.get(col_h1_hoy, '')).strip()
                h2_str_hoy = str(fila_agente.get(col_h2_hoy, '')).strip()
                
                desc_inicio_h_str = str(fila_agente.get(COL_DESCANSO_INICIO_HORA, '')).strip()

                h1_ini, h1_fin = _parse_horario_string(h1_str_hoy)
                h2_ini, h2_fin = _parse_horario_string(h2_str_hoy)
                
                en_turno_h1 = _is_currently_on_shift(h1_ini, h1_fin, ahora_con_timezone)
                en_turno_h2 = _is_currently_on_shift(h2_ini, h2_fin, ahora_con_timezone)
                en_turno_agente = en_turno_h1 or en_turno_h2
                
                en_descanso_agente = _is_on_active_break(desc_inicio_h_str, ahora_con_timezone)

                if status_general == ESTADO_SHEET_ACTIVO and en_turno_agente and not en_descanso_agente:
                    agentes_operativos_ids.append(str(agent_id)) 
            except ValueError:
                 print(f"Error procesando fila de agente {i+2}: Agent_ID '{agent_id_str}' no es un número válido. Omitiendo agente.")
            except Exception as e_agente:
                print(f"Error procesando fila de agente {i+2} (ID: {agent_id_str if 'agent_id_str' in locals() else 'desconocido'}): {e_agente}")

        with open(ruta_mapa_agentes_cache, 'w', encoding='utf-8') as f:
            json.dump(todos_los_agentes_map, f, ensure_ascii=False, indent=2)
        print(f"Caché de mapa de agentes guardada: {len(todos_los_agentes_map)} agentes.")

        with open(ruta_agentes_operativos_cache, 'w', encoding='utf-8') as f:
            json.dump(agentes_operativos_ids, f, indent=2) 
        print(f"Caché de IDs de agentes operativos guardada: {len(agentes_operativos_ids)} agentes.")

    except gspread.exceptions.SpreadsheetNotFound:
        print(f"ERROR: Planilla '{planilla_nombre_gs}' no encontrada.")
    except gspread.exceptions.WorksheetNotFound as e:
        print(f"ERROR: Hoja no encontrada en la planilla '{planilla_nombre_gs}'. Detalle: {e}")
    except FileNotFoundError:
        print(f"ERROR: Archivo de credenciales '{ruta_credenciales_gs}' no encontrado.")
    except Exception as e:
        print(f"ERROR CRÍTICO ejecutando actualización de cachés: {e}")
    
    print("--- Actualización de Caches desde Google Sheets Finalizada ---")


if __name__ == "__main__":
    print("Ejecutando prueba local de google_sheets_handler.py...")
    
    mock_gs_config = {
        "credentials_file": "credentials.json", 
        "planilla_nombre": "Horarios_automatizacion_fresh", 
        "hoja_horarios_agentes": "HorariosAgentes", 
        "hoja_configuracion_global": "ConfiguracionGlobal" 
    }
    mock_archivos_estado_config = {
        "mapa_agentes_cache": "cache_mapa_agentes_TEST.json",
        "agentes_operativos_cache": "cache_agentes_operativos_TEST.json",
        "configuracion_global_cache": "cache_configuracion_global_TEST.json"
    }

    if not os.path.exists(os.path.join(SCRIPT_DIR, mock_gs_config['credentials_file'])):
        print(f"\nADVERTENCIA: El archivo de credenciales '{mock_gs_config['credentials_file']}' no se encontró.")
        print("La prueba de google_sheets_handler.py probablemente fallará.")
        print(f"Asegúrate de que '{mock_gs_config['credentials_file']}' esté en el directorio: {SCRIPT_DIR}\n")
    
    for cache_file_key in mock_archivos_estado_config:
        test_cache_path = os.path.join(SCRIPT_DIR, mock_archivos_estado_config[cache_file_key])
        if os.path.exists(test_cache_path):
            try:
                os.remove(test_cache_path)
                print(f"Archivo de caché de prueba eliminado: {test_cache_path}")
            except OSError as e:
                print(f"Error eliminando caché de prueba {test_cache_path}: {e}")


    ejecutar_actualizacion_caches(mock_gs_config, mock_archivos_estado_config)

    print("\nPrueba finalizada. Verifica los archivos .json de TEST generados.")
    print("Si ves errores de 'WorksheetNotFound' o 'SpreadsheetNotFound', asegúrate que los nombres en 'mock_gs_config' coincidan con tu Google Sheet.")
    print("También verifica que el archivo de credenciales es correcto y tiene permisos.")