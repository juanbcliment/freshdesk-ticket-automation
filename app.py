import os
import json
import datetime
import survey_sender
import ticket_assigner
import google_sheets_handler
import fuera_horario 

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE_PATH = os.path.join(SCRIPT_DIR, 'config.json')

def cargar_configuracion_principal(ruta_archivo):
    try:
        with open(ruta_archivo, 'r', encoding='utf-8') as f:
            config = json.load(f)
        return config
    except FileNotFoundError:
        print(f"ERROR CRÍTICO: Archivo de configuración principal '{ruta_archivo}' no encontrado.")
        return None
    except json.JSONDecodeError as e:
        print(f"ERROR CRÍTICO: Error al decodificar '{ruta_archivo}'. Detalles: {e}")
        return None

def cargar_cache_json(ruta_archivo_cache, default_value):
    if not os.path.exists(ruta_archivo_cache):
        print(f"Advertencia: Archivo de caché '{ruta_archivo_cache}' no encontrado. Usando valor por defecto: {default_value}")
        return default_value
    try:
        with open(ruta_archivo_cache, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        print(f"Advertencia: Error al decodificar archivo de caché '{ruta_archivo_cache}'. Usando valor por defecto.")
        return default_value
    except Exception as e:
        print(f"Error inesperado al cargar caché '{ruta_archivo_cache}': {e}. Usando valor por defecto.")
        return default_value


def main():
    print(f"--- Orquestador Principal Iniciado ({datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) ---")
    
    config_principal = cargar_configuracion_principal(CONFIG_FILE_PATH)
    if not config_principal:
        print("Finalizando orquestador debido a error de configuración principal.")
        return

    fd_config = config_principal.get('freshdesk', {})
    gs_config = config_principal.get('google_sheets', {}) 
    archivos_estado_config = config_principal.get('archivos_estado', {})
    params_app_config = config_principal.get('parametros_aplicacion', {}) 

    if not all([fd_config, gs_config, archivos_estado_config]): 
        print("ERROR CRÍTICO: Faltan secciones clave (freshdesk, google_sheets, archivos_estado) en config.json.")
        return
    #pausar el archivo de caché de Google Sheets
    google_sheets_handler.ejecutar_actualizacion_caches(gs_config, archivos_estado_config)

    ruta_mapa_agentes_cache = os.path.join(SCRIPT_DIR, archivos_estado_config.get('mapa_agentes_cache'))
    ruta_agentes_operativos_cache = os.path.join(SCRIPT_DIR, archivos_estado_config.get('agentes_operativos_cache'))
    
    mapa_agentes_cache = cargar_cache_json(ruta_mapa_agentes_cache, default_value={})
    agentes_operativos_cache = cargar_cache_json(ruta_agentes_operativos_cache, default_value=[])

    ruta_config_global_cache = os.path.join(SCRIPT_DIR, archivos_estado_config.get('configuracion_global_cache'))
    configuracion_global_cache = cargar_cache_json(ruta_config_global_cache, default_value={})

    if not configuracion_global_cache:
        print("ERROR CRÍTICO: La configuración global (mensajes, horarios) no pudo ser cargada desde la caché. ")
        return 

    mensaje_apertura_plantilla = configuracion_global_cache.get('MENSAJE_APERTURA', "Plantilla de apertura no encontrada en Sheet.")
    mensaje_cierre_plantilla = configuracion_global_cache.get('MENSAJE_CIERRE_ENCUESTA', "Plantilla de cierre no encontrada en Sheet.")
    mensaje_fuera_horario_plantilla = configuracion_global_cache.get('MENSAJE_FUERA_HORARIO', "Plantilla de fuera de horario no encontrada en Sheet.")
    
    horario_atencion_config = {
        "hora_inicio": configuracion_global_cache.get('HORARIO_ATENCION_INICIO'),
        "hora_fin": configuracion_global_cache.get('HORARIO_ATENCION_FIN'),
        "timezone": configuracion_global_cache.get('TIMEZONE_APP') 
    }
    
    if horario_atencion_config["hora_inicio"] and horario_atencion_config["hora_fin"]:
        # Pre-formatear las horas en el mensaje de fuera de horario si es necesario
        # y si la plantilla las usa. Dejar ticket_id para formato posterior.
        try:
            mensaje_fuera_horario_plantilla = mensaje_fuera_horario_plantilla.format(
                HORARIO_ATENCION_INICIO=horario_atencion_config["hora_inicio"],
                HORARIO_ATENCION_FIN=horario_atencion_config["hora_fin"],
                ticket_id="{ticket_id}" # Mantener este placeholder
            )
        except KeyError as ke:
            print(f"Advertencia: La plantilla MENSAJE_FUERA_HORARIO no usa {{HORARIO_ATENCION_INICIO}} o {{HORARIO_ATENCION_FIN}}. Error: {ke}")
            # La plantilla se usará tal cual si no tiene esos placeholders.
    
    # Ya no se formatea con url_encuesta aquí, se asume que está en la plantilla del Sheet.

    if not mapa_agentes_cache and not agentes_operativos_cache:
        print("Advertencia: Las cachés de agentes están vacías. La asignación de tickets podría no funcionar.")
    elif not agentes_operativos_cache:
         print("Advertencia: La caché de agentes operativos está vacía. La asignación de tickets no funcionará.")
    
    fuera_horario.ejecutar_proceso_fuera_de_horario(
        fd_config,
        mensaje_fuera_horario_plantilla, 
        horario_atencion_config,      
        archivos_estado_config,
        params_app_config, 
        SCRIPT_DIR
    )
    print("\n--------------------------------------------------\n")
    
    if agentes_operativos_cache: 
        ticket_assigner.ejecutar_proceso_asignaciones(
            fd_config,
            mensaje_apertura_plantilla,
            archivos_estado_config,
            SCRIPT_DIR, 
            mapa_agentes_cache,
           agentes_operativos_cache 
        )
    else:
        print("Saltando proceso de asignación de tickets: no hay agentes operativos en caché.")
    
    print("\n--------------------------------------------------\n")
    
    survey_sender.ejecutar_proceso_encuestas(
       fd_config, 
       mensaje_cierre_plantilla,
       archivos_estado_config,
       params_app_config, 
       SCRIPT_DIR, 
       mapa_agentes_cache
    )

    print(f"\n--- Orquestador Principal Finalizado ({datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) ---")

if __name__ == "__main__":
    main()