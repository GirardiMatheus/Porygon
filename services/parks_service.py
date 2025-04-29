from parks.parks_ssh import *
import csv
import random
from utils.log import get_logger

# Configura o logger para este módulo
logger = get_logger(__name__)


def provision(ip_olt):
    """Função de provisionamento com logs detalhados"""
    try:
        # Conexão SSH
        logger.info(f"Conectando à OLT {ip_olt}")
        conexao = login_ssh(host=ip_olt)
        logger.info("Conexão SSH estabelecida com sucesso")

        # Listar ONUs não autorizadas
        logger.info("Listando ONUs não autorizadas...")
        blacklist = list_unauthorized(conexao)

        if not blacklist:
            print("Nenhuma ONU ou ONT pedindo autorização...")
            return

        # Listar e exibir ONUs não autorizadas
        print("\nONUs na blacklist:")
        for serial, dados in blacklist.items():
            print(f"Serial: {serial} | Slot: {dados['slot']} | PON: {dados['pon']}")
            logger.info(f"Serial: {serial}, PON: {dados['pon']}")

        # Consulta informações da ONU
        serial = input("\nQual o serial da ONU? ").strip().lower()
        logger.info(f"Serial informado: {serial}")

        # Verificar se o serial existe na blacklist e obter a PON correspondente
        if serial in blacklist:
            pon = blacklist[serial]['pon']
            logger.info(f"PON encontrada para {serial}: {pon}")
            add_onu_to_pon(conexao, serial, pon)
            time.sleep(random.uniform(10, 30))
        else:
            print(f"Erro: Serial {serial} não encontrado na blacklist")
            logger.warning(f"Serial não encontrado: {serial}")
        

        logger.info(f"Consultando informações da ONU {serial}...")
        dados_onu = consult_information(conexao, serial)
        
        if not dados_onu or not dados_onu['model']:
            msg = "Falha ao obter informações da ONU"
            logger.error(msg)
            print(msg)
            return
            
        model = dados_onu['model'].strip()
        logger.info(f"Dados ONU - Modelo: {model}, PON: {pon}")

        # Determinar tipo de ONU
        bridge_models = {"TX-6610", "R1v2", "XZ000-G3", "Fiberlink100", "110", "AN5506-01-A", "FiberLink101"}
        router_models = ["FiberLink611", "121AC", "FiberLink411", "ONU HW01N", "Fiberlink501(Rev2)", "ONU GW24AC", "Fiberlink210"]
        
        if model in bridge_models:
            onu_type = "bridge"
        elif model in router_models:
            onu_type = "router"
        else:
            onu_type = None
            
        logger.info(f"Tipo detectado: {onu_type or 'Desconhecido'}")
        print(model)

        if not onu_type:
            msg = f"Modelo {model} não reconhecido"
            logger.warning(msg)
            print(msg)
            return

        # Carregar configurações do CSV
        csv_path = './csv/parks.csv'
        try:
            logger.info(f"Consultando CSV em {csv_path}...")
            with open(csv_path, mode='r') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    # Converter pon para string para comparação segura
                    csv_pon = str(row['pon']) 
                    input_pon = str(pon)       
                    
                    if (row['olt_ip'] == ip_olt and 
                        csv_pon == input_pon and  
                        row['type'].lower() == onu_type.lower()):
                        
                        vlan = row['vlan']
                        profile = row['profile']
                        logger.info(f"Config CSV - VLAN: {vlan}, Profile: {profile}")
                        break
                else:
                    msg = f"Configuração não encontrada para OLT {ip_olt} PON {pon} Tipo {onu_type}"
                    logger.warning(msg)
                    print(msg)
                    vlan = input("Digite a VLAN: ").strip()
                    profile = input("Digite o profile: ").strip()
                    logger.info(f"Valores manuais - VLAN: {vlan}, Profile: {profile}")
            
        except FileNotFoundError:
            msg = f"Arquivo CSV não encontrado em {csv_path}"
            logger.error(msg)
            print(msg)
            vlan = input("Digite a VLAN: ").strip()
            profile = input("Digite o profile: ").strip()
                    
        except Exception as e:
            msg = f"Erro ao ler CSV: {str(e)}"
            logger.error(msg)
            print(msg)
            vlan = input("Digite a VLAN: ").strip()
            profile = input("Digite o profile: ").strip()
            logger.info(f"Valores manuais - VLAN: {vlan}, Profile: {profile}")

        # Dados adicionais
        nome = str(input("\nDigite o alias/nome da ONU: ")).strip().replace(" ", "_") or serial
        logger.info(f"Alias/Nome definido: {nome}")

        # Provisionamento específico
        logger.info(f"Iniciando provisionamento como {onu_type}...")
        if onu_type == 'bridge':
            logger.info("Executando fluxo Bridge...")
            auth_bridge(conexao, serial, pon, nome, profile, vlan)
        
        elif model in ["ONU HW01N", "Fiberlink210"]:
            logger.info(f"Executando fluxo Default Router para {model}...")
            login_pppoe = input("Qual login PPPoE do cliente? ")
            senha_pppoe = input("Qual a senha do PPPoE do cliente? ")
            logger.info(f"Credenciais PPPoE coletadas (usuário oculto no log)")
            if not vlan.isdigit():
                print("Erro: VLAN deve conter apenas números")
                return
            auth_router_default(conexao, serial, nome, vlan, pon, profile, login_pppoe, senha_pppoe)
            
        elif model == "121AC":
            logger.info(f"Executando fluxo {model}...")
            auth_router_121AC(conexao, serial, pon, nome, profile, vlan)
            print("ALERTA: Configurar PPPoE/WiFi manualmente")
            
        elif model in ["FiberLink411", "ONU GW24AC"]:
            logger.info(f"Executando fluxo {model}...")
            login_pppoe = input("Qual login PPPoE do cliente? ")
            senha_pppoe = input("Qual a senha do PPPoE do cliente? ")
            logger.info(f"Credenciais PPPoE coletadas (usuário oculto no log)")
            auth_router_config2(conexao, serial, pon, nome, vlan, profile, login_pppoe, senha_pppoe)

        elif model == "Fiberlink501(Rev2)":
            logger.info(f"Executando fluxo {model}...")
            login_pppoe = input("Qual login PPPoE do cliente? ")
            senha_pppoe = input("Qual a senha do PPPoE do cliente? ")
            logger.info(f"Credenciais PPPoE coletadas (usuário oculto no log)")
            auth_router_Fiberlink501Rev2(conexao, serial, pon, nome, profile, login_pppoe, senha_pppoe)

        logger.info(f"Provisionamento concluído - ONU {serial} na PON {pon}")
        print(f"\nProvisionamento concluído com sucesso!")

    except Exception as e:
        error_msg = f"ERRO NO PROVISIONAMENTO: {str(e)}"
        if 'conexao' in locals():
            conexao.terminate()
        logger.error(error_msg)
        print(error_msg)
        
    finally:
        if 'conexao' in locals():
            logger.info("Encerrando conexão SSH...")
            conexao.terminate()

def onu_list(ip_olt):
    conexao = None
    try:
        # Conexão SSH
        logger.info(f"Conectando à OLT {ip_olt}")
        conexao = login_ssh(host=ip_olt)
        logger.info("Conexão SSH estabelecida com sucesso")

        # Listar ONUs não autorizadas
        logger.info("Listando ONUs não autorizadas...")
        blacklist = list_unauthorized(conexao)

        if not blacklist:
            print("Nenhuma ONU ou ONT pedindo autorização...")
            return

        print("\nONUs na blacklist:")
        for serial, dados in blacklist.items():
            print(f"Serial: {serial} | Slot: {dados['slot']} | PON: {dados['pon']}")
    
    except Exception as e:
        error_msg = f"ERRO AO LISTAR ONU's: {str(e)}"
        logger.error(error_msg)
        print(error_msg)

    finally:
        if conexao:
            logger.info("Encerrando conexão SSH...")
            conexao.terminate()

def unauthorized_complete(ip_olt):
    conexao = None
    try:
        # 1. Conexão SSH
        logger.info(f"Iniciando processo para desautorizar ONU na OLT {ip_olt}")
        conexao = login_ssh(host=ip_olt)
        if not conexao:
            print("Falha ao conectar na OLT")
            logger.error("Conexão SSH falhou")
            return False

        # 2. Consulta ONU
        serial = input("Qual o serial da ONU? ").strip().lower()
        logger.info(f"Serial informado: {serial}")
        
        dados_onu = consult_information(conexao, serial)
        if not dados_onu:
            print("ONU/ONT não encontrada na OLT")
            logger.warning(f"ONU {serial} não encontrada")
            return False

        pon = dados_onu.get('pon')
        if not pon:
            print("Falha ao obter informação da PON")
            logger.error("Dados da PON não encontrados")
            return False

        # Formata PON (extrai apenas o número)
        pon_numero = pon.split('/')[-1] if '/' in pon else pon
        logger.info(f"Dados obtidos - Serial: {serial}, PON: {pon_numero}")

        # 3. Reboot
        logger.info(f"Iniciando reboot da ONU {serial}")
        if not reboot(conexao, pon_numero, serial):
            print("Falha no reboot da ONU")
            logger.error("Reboot falhou")
            return False

        print("ONU reiniciada com sucesso, aguardando 10 segundos...")
        time.sleep(10)  

        # 4. Desautorização
        logger.info(f"Iniciando desautorização da ONU {serial}")
        if not unauthorized(conexao, pon_numero, serial):
            print("Falha na desautorização da ONU")
            logger.error("Desautorização falhou")
            return False

        print("✅ ONU desautorizada com sucesso")
        logger.info(f"Processo completo concluído para ONU {serial}")
        return True

    except Exception as e:
        error_msg = f"Erro no processo: {str(e)}"
        print(f"⚠️ Erro: {error_msg}")
        logger.error(error_msg)
        return False

    finally:
        # 5. Encerra conexão
        if conexao:
            logger.info("Encerrando conexão SSH")
            conexao.terminate()

def consult_information_complete(ip_olt):
    conexao = None
    try:
        logger.info(f"Iniciando consulta completa para OLT {ip_olt}")
        
        # Estabelece conexão SSH
        conexao = login_ssh(host=ip_olt)
        logger.info("Conexão SSH estabelecida com sucesso")
        
        # Solicita serial da ONU
        serial = input("Qual o serial da ONU? ").strip().lower()
        logger.info(f"Serial informado pelo usuário: {serial}")
        
        # Consulta informações da ONU
        logger.info(f"Consultando informações da ONU {serial}")
        dados_onu = consult_information(conexao, serial)
        
        if not dados_onu:
            msg = "Falha ao consultar informações da ONU/ONT ou ONU não encontrada"
            print(msg)
            logger.warning(msg)
            return
            
        # Extrai dados
        model = dados_onu.get('model', 'N/A')
        alias = dados_onu.get('alias', 'N/A')
        power_level = dados_onu.get('power_level', 'N/A')
        distance_km = dados_onu.get('distance_km', 'N/A')
        pon = dados_onu.get('pon', 'N/A')
        if pon != 'N/A':
            pon = pon.split('/')[-1]  
        status = dados_onu.get('status', 'N/A')
        
        # Prepara e exibe informações formatadas
        info_formatada = (
            f"\n=== Informações da ONU {serial} ===\n"
            f"Modelo: {model}\n"
            f"Nome/Descrição: {alias}\n"
            f"Nível do Sinal: {power_level}\n"
            f"Distância da OLT: {distance_km} KM\n"
            f"PON: {pon}\n"  
            f"Status: {status}\n"
            "======================================="
        )
        
        print(info_formatada)
        logger.info(f"Informações exibidas para o usuário:\n{info_formatada}")
        
    except Exception as e:
        error_msg = f"Erro durante consulta: {str(e)}"
        print(f"\nErro: {error_msg}")
        logger.error(error_msg)
        
    finally:
        if conexao:
            logger.info("Encerrando conexão SSH")
            conexao.terminate()

def reboot_complete(ip_olt):
    conexao = None
    try:
        # 1. Conexão SSH
        logger.info(f"Iniciando processo para desautorizar ONU na OLT {ip_olt}")
        conexao = login_ssh(host=ip_olt)
        if not conexao:
            print("Falha ao conectar na OLT")
            logger.error("Conexão SSH falhou")
            return False

        # 2. Consulta ONU
        serial = input("Qual o serial da ONU? ").strip().lower()
        logger.info(f"Serial informado: {serial}")
        
        dados_onu = consult_information(conexao, serial)
        if not dados_onu:
            print("ONU/ONT não encontrada na OLT")
            logger.warning(f"ONU {serial} não encontrada")
            return False

        pon = dados_onu.get('pon')
        if not pon:
            print("Falha ao obter informação da PON")
            logger.error("Dados da PON não encontrados")
            return False

        # Formata PON (extrai apenas o número)
        pon_numero = pon.split('/')[-1] if '/' in pon else pon
        logger.info(f"Dados obtidos - Serial: {serial}, PON: {pon_numero}")

        # 3. Reboot
        logger.info(f"Iniciando reboot da ONU {serial}")
        if not reboot(conexao, pon_numero, serial):
            print("Falha no reboot da ONU")
            logger.error("Reboot falhou")
            return False
        
        print("✅ ONU desautorizada com sucesso")
        logger.info(f"Processo completo concluído para ONU {serial}")
        return True
            
    except Exception as e:
        error_msg = f"Erro no processo: {str(e)}"
        print(f"⚠️ Erro: {error_msg}")
        logger.error(error_msg)
        return False

    finally:
        if conexao:
            logger.info("Encerrando conexão SSH")
            conexao.terminate()

def list_of_compatible_models():
    """Exibe os modelos suportados divididos por categoria"""
    bridge_models = ["TX-6610", "R1v2", "XZ000-G3", "Fiberlink100", 
                    "110", "AN5506-01-A", "FiberLink101"]
    router_models = ["FiberLink611", "121AC", "FiberLink411", "ONU HW01N", 
                    "Fiberlink501(Rev2)", "ONU GW24AC", "Fiberlink210"]

    print("\n=== MODELOS SUPORTADOS ===")
    print("\n🔷 BRIDGE:")
    for modelo in bridge_models:
        print(f"  → {modelo}")
    
    print("\n🔶 ROUTER:")
    for modelo in router_models:
        print(f"  → {modelo}")
    
    input("\nPressione Enter para voltar...")