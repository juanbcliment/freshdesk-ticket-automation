import requests
import os
import datetime
import json

# Tag a ser añadido a los tickets después de enviar la encuesta
TAG_ENCUESTA_ENVIADA = "Encuesta enviada"

# Las funciones _cargar_ids_procesados_encuestas y _guardar_id_procesado_encuesta
# fueron eliminadas en versiones anteriores ya que no se usa el archivo local.

def _obtener_tickets_cerrados_recientemente(fd_domain, fd_api_key, minutos_referencia_creacion):
    """
    Busca tickets cerrados (estados 5, 6, 7) CREADOS EN EL DÍA CALENDARIO
    de hace X minutos, utilizando el filtro de fecha de la API de Freshdesk
    (created_at:'YYYY-MM-DD'). Implementa paginación usando el tamaño de página
    predeterminado de la API (normalmente 30) para obtener hasta 1000 resultados.
    """
    url = f"https://{fd_domain}.freshdesk.com/api/v2/search/tickets"
    
    ahora_utc = datetime.datetime.now(datetime.timezone.utc)
    punto_referencia_utc = ahora_utc - datetime.timedelta(minutes=minutos_referencia_creacion)
    fecha_limite_str = punto_referencia_utc.strftime("'%Y-%m-%d'")

    query_string = f"created_at:{fecha_limite_str} AND (status:5 OR status:6 OR status:7)"
    
    print(f"Intentando búsqueda en API Freshdesk con query: {query_string}")
    print(f"(Esto buscará tickets creados EN EL DÍA {fecha_limite_str} con los estados indicados)")
    
    all_results_from_api = []
    page_num = 1
    DEFAULT_PER_PAGE_ASSUMPTION = 30 
    MAX_API_PAGES_TO_FETCH = 34 

    while page_num <= MAX_API_PAGES_TO_FETCH:
        params = {
            'query': f'"{query_string}"',
            'page': page_num
        }
        response_obj = None
        
        print(f"Solicitando página {page_num} (tamaño de página por defecto, aprox. {DEFAULT_PER_PAGE_ASSUMPTION} tickets)...")
        try:
            response_obj = requests.get(url, auth=(fd_api_key, 'x'), params=params)
            response_obj.raise_for_status() 
            data = response_obj.json()
            results_on_page = data.get('results', [])
            
            if not results_on_page:
                print(f"Página {page_num}: No se encontraron más tickets. Fin de la paginación.")
                break 
            
            all_results_from_api.extend(results_on_page)
            print(f"Página {page_num}: Obtenidos {len(results_on_page)} tickets. Total acumulado: {len(all_results_from_api)}.")
            
            if len(results_on_page) < DEFAULT_PER_PAGE_ASSUMPTION:
                print("Última página de resultados alcanzada (o menos tickets que el default por página).")
                break
            
            page_num += 1
            
        except requests.exceptions.HTTPError as http_err:
            error_msg = f"Error HTTP (encuestas - API filter created_at:'YYYY-MM-DD', pág {page_num}): {http_err}"
            if response_obj and hasattr(response_obj, 'text'):
                error_msg += f"\nServer: {response_obj.text}"
            print(error_msg)
            break 
        except Exception as e:
            print(f"Error (encuestas - API filter created_at:'YYYY-MM-DD', pág {page_num}): {e}")
            break
            
    if page_num > MAX_API_PAGES_TO_FETCH and len(all_results_from_api) >= MAX_API_PAGES_TO_FETCH * DEFAULT_PER_PAGE_ASSUMPTION:
        print(f"ADVERTENCIA: Se alcanzó el límite de {MAX_API_PAGES_TO_FETCH} páginas. "
              "Podría haber más tickets que no se recuperaron debido al límite de la API de búsqueda (aprox. 1000 tickets).")

    print(f"Total de tickets recuperados de la API después de paginación: {len(all_results_from_api)}.")
    return all_results_from_api


def _obtener_detalles_ticket_fd(fd_domain, fd_api_key, ticket_id):
    url = f"https://{fd_domain}.freshdesk.com/api/v2/tickets/{ticket_id}"
    response_obj = None
    try:
        response_obj = requests.get(url, auth=(fd_api_key, 'x'))
        response_obj.raise_for_status()
        return response_obj.json() 
    except requests.exceptions.HTTPError as http_err:
        error_msg = f"Error HTTP obteniendo detalles del ticket #{ticket_id}: {http_err}"
        if response_obj and hasattr(response_obj, 'text'):
            error_msg += f"\nServer: {response_obj.text}"
        print(error_msg)
    except Exception as e:
        print(f"Error obteniendo detalles del ticket #{ticket_id}: {e}")
    return None

def _enviar_mensaje_y_actualizar_ticket_fd(fd_domain, fd_api_key, ticket_id, mensaje_body, original_agent_id, original_status, tags_previos_al_envio):
    url_reply = f"https://{fd_domain}.freshdesk.com/api/v2/tickets/{ticket_id}/reply"
    headers_reply = {"Content-Type": "application/json"}
    data_reply = {"body": mensaje_body}
    response_obj_reply = None
    try:
        response_obj_reply = requests.post(url_reply, auth=(fd_api_key, 'x'), headers=headers_reply, json=data_reply)
        response_obj_reply.raise_for_status()
        print(f"✅ Mensaje de encuesta enviado al ticket #{ticket_id}.")
    except requests.exceptions.HTTPError as http_err_reply:
        error_msg_reply = f"❌ Error HTTP enviando mensaje encuesta al ticket #{ticket_id}: {http_err_reply}"
        if response_obj_reply and hasattr(response_obj_reply, 'text'):
            error_msg_reply += f"\nServer: {response_obj_reply.text}"
        print(error_msg_reply)
        return False 
    except Exception as e_reply:
        print(f"❌ Error enviando mensaje encuesta al ticket #{ticket_id}: {e_reply}")
        return False

    url_update = f"https://{fd_domain}.freshdesk.com/api/v2/tickets/{ticket_id}"
    tags_para_actualizar = list(tags_previos_al_envio) 
    if TAG_ENCUESTA_ENVIADA not in tags_para_actualizar:
        tags_para_actualizar.append(TAG_ENCUESTA_ENVIADA)
    data_update = {
        "status": original_status,
        "responder_id": original_agent_id,
        "tags": tags_para_actualizar
    }
    response_obj_update = None
    try:
        response_obj_update = requests.put(url_update, auth=(fd_api_key, 'x'), json=data_update)
        response_obj_update.raise_for_status()
        print(f"✅ Ticket #{ticket_id} actualizado: Estado original ({original_status}), Agente original ({original_agent_id}), Tag '{TAG_ENCUESTA_ENVIADA}' agregado/confirmado.")
        return True
    except requests.exceptions.HTTPError as http_err_update:
        error_msg_update = f"❌ Error HTTP actualizando ticket #{ticket_id} post-encuesta: {http_err_update}"
        if response_obj_update and hasattr(response_obj_update, 'text'):
            error_msg_update += f"\nServer: {response_obj_update.text}"
        print(error_msg_update)
    except Exception as e_update:
        print(f"❌ Error actualizando ticket #{ticket_id} post-encuesta: {e_update}")
    return False

def ejecutar_proceso_encuestas(
    fd_config, 
    plantilla_mensaje_cierre, 
    archivos_estado_config, 
    params_app_config,
    script_dir, 
    mapa_agentes_cache
):
    print("--- Iniciando Proceso de Envío de Encuestas ---")

    fd_api_key = fd_config.get('api_key')
    fd_domain = fd_config.get('domain')
        
    minutos_para_referencia_creacion = 240 

    if not all([fd_api_key, fd_domain, plantilla_mensaje_cierre]):
        print("Error (Encuestas): Faltan configuraciones esenciales.")
        print("--- Proceso de Envío de Encuestas Finalizado ---")
        return

    tickets_para_procesar = _obtener_tickets_cerrados_recientemente(
        fd_domain, 
        fd_api_key,
        minutos_para_referencia_creacion
    )

    if not tickets_para_procesar:
        print("No se encontraron tickets (según filtro API por DÍA de creación y estado) para enviar encuesta.")
        print("--- Proceso de Envío de Encuestas Finalizado ---")
        return

    procesados_en_esta_ejecucion = 0
    for ticket_info in tickets_para_procesar:
        ticket_id_actual_str = str(ticket_info['id'])
        
        tags_en_resumen = ticket_info.get('tags', [])
        if TAG_ENCUESTA_ENVIADA in tags_en_resumen:
            print(f"Ticket #{ticket_id_actual_str} ya tiene el tag '{TAG_ENCUESTA_ENVIADA}' (detectado en resultado de API). Omitiendo.")
            continue
        
        print(f"\nProcesando ticket #{ticket_id_actual_str} para envío de encuesta...")

        ticket_detalles_completos = _obtener_detalles_ticket_fd(fd_domain, fd_api_key, ticket_id_actual_str)

        if not ticket_detalles_completos:
            print(f"No se pudieron obtener los detalles completos para el ticket #{ticket_id_actual_str}. Omitiendo.")
            continue

        original_status = ticket_detalles_completos.get('status')
        original_responder_id = ticket_detalles_completos.get('responder_id') 
        tags_actuales_del_ticket = ticket_detalles_completos.get('tags', []) 

        # Log de depuración para el responder_id
        print(f"DEBUG: Ticket ID: {ticket_id_actual_str}, Original Responder ID: {original_responder_id}")

        if TAG_ENCUESTA_ENVIADA in tags_actuales_del_ticket:
            print(f"Ticket #{ticket_id_actual_str} ya tiene el tag '{TAG_ENCUESTA_ENVIADA}' (detectado en detalles completos). Omitiendo.")
            continue

        agent_id_str = str(original_responder_id) if original_responder_id is not None else None
        nombre_agente = "nuestro equipo de soporte" 
        if agent_id_str and agent_id_str in mapa_agentes_cache:
            nombre_agente = mapa_agentes_cache[agent_id_str]
            # Log de depuración para el nombre del agente
            print(f"DEBUG: Agente encontrado en caché: ID {agent_id_str} -> Nombre '{nombre_agente}'")
        elif agent_id_str:
            print(f"Advertencia: Agente ID {agent_id_str} del ticket #{ticket_id_actual_str} no encontrado en mapa_agentes_cache. Usando nombre genérico '{nombre_agente}'.")
        else:
            # Log de depuración si no hay responder_id
            print(f"DEBUG: No hay original_responder_id para el ticket #{ticket_id_actual_str}. Usando nombre genérico '{nombre_agente}'.")


        try:
            mensaje_formateado = plantilla_mensaje_cierre.format(
                agent_name=nombre_agente,
                ticket_id=ticket_id_actual_str
            )
            # Log de depuración para el mensaje
            print(f"DEBUG: Mensaje formateado para enviar (primeros 100 chars): '{mensaje_formateado[:100]}...'")
        except KeyError as e:
            print(f"Error al formatear plantilla de encuesta para ticket #{ticket_id_actual_str}: Falta la clave {e}. Usando plantilla sin formato.")
            mensaje_formateado = plantilla_mensaje_cierre 

        if _enviar_mensaje_y_actualizar_ticket_fd(
            fd_domain, 
            fd_api_key, 
            ticket_id_actual_str, 
            mensaje_formateado, 
            original_responder_id, 
            original_status,
            tags_actuales_del_ticket 
        ):
            procesados_en_esta_ejecucion += 1
        else:
            print(f"Hubo un problema al procesar el ticket #{ticket_id_actual_str} para encuesta.")
        
    if procesados_en_esta_ejecucion > 0:
        print(f"Se procesaron {procesados_en_esta_ejecucion} tickets para envío de encuesta.")
    else:
        print("No hubo nuevos tickets (que no tuvieran ya encuesta enviada y cumplieran filtro API) para procesar en esta ejecución.")
    
    print("--- Proceso de Envío de Encuestas Finalizado ---")

if __name__ == "__main__":
    print("Ejecutando prueba local de survey_sender.py...")
    
    mock_script_dir = os.path.dirname(os.path.abspath(__file__))
    mock_config_path = os.path.join(mock_script_dir, 'config.json')
    mock_cache_config_global_path = os.path.join(mock_script_dir, 'cache_configuracion_global.json')
    mock_cache_mapa_agentes_path = os.path.join(mock_script_dir, 'cache_mapa_agentes.json')

    if not os.path.exists(mock_config_path) or \
       not os.path.exists(mock_cache_config_global_path) or \
       not os.path.exists(mock_cache_mapa_agentes_path):
        print("ERROR: Faltan archivos de configuración/caché para la prueba.")
        exit()

    try:
        with open(mock_config_path, 'r', encoding='utf-8') as f: config_principal = json.load(f)
        with open(mock_cache_config_global_path, 'r', encoding='utf-8') as f: configuracion_global_cache = json.load(f)
        with open(mock_cache_mapa_agentes_path, 'r', encoding='utf-8') as f: mapa_agentes_cache = json.load(f)
    except Exception as e:
        print(f"Error cargando archivos de configuración/caché para prueba: {e}")
        exit()

    mock_fd_config = config_principal.get('freshdesk', {})
    mock_archivos_estado_config = config_principal.get('archivos_estado', {}) 
    mock_params_app_config = config_principal.get('parametros_aplicacion', {}) 
    mock_plantilla_mensaje_cierre = configuracion_global_cache.get('MENSAJE_CIERRE_ENCUESTA')
    
    if not all([mock_fd_config, mock_archivos_estado_config, mock_params_app_config, mock_plantilla_mensaje_cierre, mapa_agentes_cache]):
        print("Faltan configuraciones esenciales en los mocks para la prueba.")
    else:
        print("\n--- INICIANDO EJECUCIÓN DE PRUEBA DEL MÓDULO DE ENCUESTAS (con logs de depuración de agente) ---")
        ejecutar_proceso_encuestas(
            mock_fd_config,
            mock_plantilla_mensaje_cierre,
            mock_archivos_estado_config, 
            mock_params_app_config,
            mock_script_dir,
            mapa_agentes_cache
        )
        print("--- FIN DE EJECUCIÓN DE PRUEBA DEL MÓDULO DE ENCUESTAS ---\n")

    print("Prueba de survey_sender.py finalizada.")