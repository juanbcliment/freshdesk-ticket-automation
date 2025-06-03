import requests
import datetime
import os

ESTADO_CERRADO_FRESHDESK = 5 

def _cargar_ids_procesados_fuera_horario(ruta_completa_archivo):
    if not os.path.exists(ruta_completa_archivo): return set()
    try:
        with open(ruta_completa_archivo, "r", encoding='utf-8') as f:
            return set(line.strip() for line in f if line.strip())
    except Exception as e:
        print(f"Error cargando IDs procesados (fuera horario) de '{ruta_completa_archivo}': {e}")
        return set()

def _guardar_id_procesado_fuera_horario(ticket_id, ruta_completa_archivo):
    try:
        with open(ruta_completa_archivo, "a", encoding='utf-8') as f:
            f.write(f"{str(ticket_id)}\n")
    except Exception as e:
        print(f"Error guardando ID (fuera horario) {ticket_id} en '{ruta_completa_archivo}': {e}")

def _obtener_tickets_recientes_sin_respuesta_agente(fd_domain, fd_api_key, minutos_antiguedad_max):
    url = f"https://{fd_domain}.freshdesk.com/api/v2/search/tickets"
    ahora_utc = datetime.datetime.now(datetime.timezone.utc)
    hace_x_minutos_utc = ahora_utc - datetime.timedelta(minutes=minutos_antiguedad_max)
    timestamp_limite = hace_x_minutos_utc.strftime("'%Y-%m-%dT%H:%M:%SZ'")
    # status < 4 (Nuevo, Abierto, Pendiente) y sin agente asignado
    query_string = f"created_at:>{timestamp_limite} AND.gitignore status:<4 AND agent_id:null" 
    params = {'query': f'"{query_string}"'}
    response_obj = None
    try:
        response_obj = requests.get(url, auth=(fd_api_key, 'x'), params=params)
        response_obj.raise_for_status()
        data = response_obj.json()
        return data.get('results', [])
    except requests.exceptions.HTTPError as http_err:
        error_msg = f"Error HTTP (fuera horario - obtener tickets): {http_err}"
        if response_obj and hasattr(response_obj, 'text'): error_msg += f"\nServer: {response_obj.text}"
        print(error_msg)
    except Exception as e: print(f"Error (fuera horario - obtener tickets): {e}")
    return []

def _enviar_respuesta_y_cerrar_ticket_fd(fd_domain, fd_api_key, ticket_id, mensaje_body):
    url_reply = f"https://{fd_domain}.freshdesk.com/api/v2/tickets/{ticket_id}/reply"
    headers = {"Content-Type": "application/json"}
    data_reply = {"body": mensaje_body}
    response_obj_reply = None
    try:
        response_obj_reply = requests.post(url_reply, auth=(fd_api_key, 'x'), headers=headers, json=data_reply)
        response_obj_reply.raise_for_status()
        print(f"✅ Mensaje de fuera de horario enviado al ticket #{ticket_id}.")
        url_update = f"https://{fd_domain}.freshdesk.com/api/v2/tickets/{ticket_id}"
        # Payload para cerrar el ticket. Freshdesk podría requerir otros campos obligatorios
        # si se actualiza el estado, pero usualmente status es suficiente.
        data_update = {"status": ESTADO_CERRADO_FRESHDESK} 
        response_obj_update = None
        try:
            response_obj_update = requests.put(url_update, auth=(fd_api_key, 'x'), json=data_update)
            response_obj_update.raise_for_status()
            print(f"✅ Ticket #{ticket_id} cerrado después de enviar mensaje de fuera de horario.")
            return True
        except requests.exceptions.HTTPError as http_err_update:
            error_msg_update = f"❌ Error HTTP cerrando ticket #{ticket_id} (fuera horario): {http_err_update}"
            if response_obj_update and hasattr(response_obj_update, 'text'): error_msg_update += f"\nServer: {response_obj_update.text}"
            print(error_msg_update)
        except Exception as e_update: print(f"❌ Error cerrando ticket #{ticket_id} (fuera horario): {e_update}")
    except requests.exceptions.HTTPError as http_err_reply:
        error_msg_reply = f"❌ Error HTTP enviando respuesta (fuera horario) {ticket_id}: {http_err_reply}"
        if response_obj_reply and hasattr(response_obj_reply, 'text'): error_msg_reply += f"\nServer: {response_obj_reply.text}"
        print(error_msg_reply)
    except Exception as e_reply: print(f"❌ Error enviando respuesta (fuera horario) {ticket_id}: {e_reply}")
    return False

def _get_current_datetime_with_timezone_fh(timezone_str=None): 
    try:
        import pytz
        if timezone_str:
            try:
                tz = pytz.timezone(timezone_str)
                return datetime.datetime.now(tz)
            except pytz.UnknownTimeZoneError:
                print(f"Advertencia (FH): Timezone '{timezone_str}' desconocido. Usando hora local del servidor.")
                return datetime.datetime.now()
        else: 
            return datetime.datetime.now()
    except ImportError:
        if timezone_str: 
            print("Advertencia (FH): Módulo 'pytz' no instalado. Timezone no se aplicará. Usando hora local del servidor.")
        return datetime.datetime.now()

def _esta_fuera_de_horario_atencion(horario_config):
    hora_inicio_str = horario_config.get("hora_inicio")
    hora_fin_str = horario_config.get("hora_fin")
    timezone_str = horario_config.get("timezone")

    if not hora_inicio_str or not hora_fin_str:
        print("Advertencia (FH): Horario de atención general (inicio/fin) no definido. Asumiendo DENTRO de horario.")
        return False 

    ahora_dt = _get_current_datetime_with_timezone_fh(timezone_str)
    
    try:
        hora_actual_t = ahora_dt.time()
        hora_inicio_t = datetime.datetime.strptime(hora_inicio_str, "%H:%M").time()
        hora_fin_t = datetime.datetime.strptime(hora_fin_str, "%H:%M").time()

        if hora_inicio_t > hora_fin_t: 
            if hora_actual_t >= hora_inicio_t or hora_actual_t < hora_fin_t:
                # print(f"Info (FH): Hora actual {ahora_dt.strftime('%H:%M %Z')} DENTRO del horario ({hora_inicio_str}-{hora_fin_str}).")
                return False 
        else: 
            if hora_inicio_t <= hora_actual_t < hora_fin_t:
                # print(f"Info (FH): Hora actual {ahora_dt.strftime('%H:%M %Z')} DENTRO del horario ({hora_inicio_str}-{hora_fin_str}).")
                return False 
        
        print(f"Info (FH): Hora actual {ahora_dt.strftime('%H:%M %Z')} FUERA del horario de atención ({hora_inicio_str} - {hora_fin_str} {timezone_str if timezone_str else 'local'}).")
        return True 

    except ValueError as ve:
        print(f"Error (FH): Formato de hora incorrecto ({hora_inicio_str}/{hora_fin_str}): {ve}. Asumiendo DENTRO.")
        return False
    except Exception as e:
        print(f"Error inesperado (FH) verificando horario: {e}. Asumiendo DENTRO.")
        return False

def ejecutar_proceso_fuera_de_horario(
    fd_config, 
    plantilla_mensaje_fh, 
    config_horario_general, 
    archivos_estado_config, 
    params_app_config, 
    script_dir
):
    print("--- Iniciando Proceso de Fuera de Horario ---")

    fd_api_key = fd_config.get('api_key')
    fd_domain = fd_config.get('domain')
    
    archivo_procesados_nombre = archivos_estado_config.get('fuera_horario_procesados', 'fuera_horario_procesados.txt')
    # Usar el parámetro específico para fuera de horario si existe, sino default.
    minutos_antiguedad_max_busqueda = params_app_config.get('minutos_antiguedad_max_busqueda_fh', 60) 

    if not all([fd_api_key, fd_domain, plantilla_mensaje_fh, config_horario_general]):
        print("Error (FH): Faltan configuraciones esenciales.")
        print("--- Proceso de Fuera de Horario Finalizado ---")
        return

    if not _esta_fuera_de_horario_atencion(config_horario_general):
        print("--- Proceso de Fuera de Horario Finalizado (dentro de horario) ---")
        return
    
    print("Estamos FUERA del horario de atención. Buscando tickets para procesar...")

    ruta_archivo_procesados = os.path.join(script_dir, archivo_procesados_nombre)
    ids_ya_procesados = _cargar_ids_procesados_fuera_horario(ruta_archivo_procesados)

    tickets_a_revisar = _obtener_tickets_recientes_sin_respuesta_agente(
        fd_domain, 
        fd_api_key,
        minutos_antiguedad_max_busqueda
    )

    if not tickets_a_revisar:
        print("No se encontraron tickets recientes (según criterio) para procesar por fuera de horario.")
        print("--- Proceso de Fuera de Horario Finalizado ---")
        return

    procesados_en_esta_ejecucion = 0
    for ticket_info in tickets_a_revisar:
        ticket_id_actual = str(ticket_info['id'])

        if ticket_id_actual in ids_ya_procesados:
            continue
        
        print(f"\nProcesando ticket #{ticket_id_actual} por fuera de horario...")
        
        try:
            mensaje_final_con_ticket_id = plantilla_mensaje_fh.format(ticket_id=ticket_id_actual)
        except KeyError as ke:
            print(f"Advertencia (FH): La plantilla MENSAJE_FUERA_HORARIO no usa {{ticket_id}} o falta otro placeholder. Error: {ke}")
            mensaje_final_con_ticket_id = plantilla_mensaje_fh # Usar sin formatear si falla ticket_id

        if _enviar_respuesta_y_cerrar_ticket_fd(fd_domain, fd_api_key, ticket_id_actual, mensaje_final_con_ticket_id):
            _guardar_id_procesado_fuera_horario(ticket_id_actual, ruta_archivo_procesados)
            procesados_en_esta_ejecucion += 1
        
    if procesados_en_esta_ejecucion > 0:
        print(f"Se procesaron {procesados_en_esta_ejecucion} tickets por fuera de horario.")
    else:
        print("No hubo nuevos tickets (que no estuvieran ya procesados) para fuera de horario en esta ejecución.")
    
    print("--- Proceso de Fuera de Horario Finalizado ---")