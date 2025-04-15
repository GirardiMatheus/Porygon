from nokia.nokia_ssh import *
from nokia.nokia_tl1 import *
import csv
import random
from utils.log import get_logger

# Logger principal
logger = get_logger(__name__)
logger.info("Sistema iniciado")


def onu_list_nokia(ip_olt):
    conexao = None
    try:
        logger.info(f"Conectando à OLT {ip_olt}...")
        conexao = login_olt_ssh(host=ip_olt)
        if not conexao:
            logger.error(f"Falha na conexão com a OLT {ip_olt}")
            return

        logger.info("Conexão SSH estabelecida com sucesso")
        logger.info("Listando ONUs não autorizadas...")
        blacklist = list_unauthorized(conexao)

        if not blacklist:
            print("Nenhuma ONU ou ONT pedindo autorização...")
            logger.info("Nenhuma ONU ou ONT encontrada na blacklist")
            return

        print("\nONUs na blacklist:")
        for serial, dados in blacklist.items():
            print(f"Serial: {serial} | Slot: {dados['slot']} | PON: {dados['pon']}")
        logger.info(f"{len(blacklist)} ONUs encontradas na blacklist")

    except Exception as e:
        logger.error(f"ERRO AO LISTAR ONU's: {str(e)}")
        print(f"❌ ERRO AO LISTAR ONU's: {str(e)}")

    finally:
        if conexao:
            logger.info("Encerrando conexão SSH...")
            try:
                conexao.terminate()
                logger.info("Conexão encerrada com sucesso")
            except Exception as e:
                logger.warning(f"Erro ao encerrar a conexão: {str(e)}")


def list_of_compatible_models_nokia():
    bridge_models = ["TP-Link - TX-6610, XZ000-G3", "Intelbras - R1v2, 110Gb", 
                    "Fiberhome - AN5506-01-A", "PARKS - Fiberlink100, FiberLink101"]
    router_models = ["NOKIA - G-1425G-A, G-1425G-B, G-1426G-A"]

    print("\n=== MODELOS SUPORTADOS ===")
    
    print("\n🔶 BRIDGE:")
    for modelo in bridge_models:
        print(f"  → {modelo}")
    
    print("\n🔷 ROUTER:")
    for modelo in router_models:
        print(f"  → {modelo}")

    logger.info("Modelos compatíveis exibidos com sucesso")
    input("\nPressione Enter para voltar...")
