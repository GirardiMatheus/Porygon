"""
Nokia SSH module for OLT management operations.
Provides functions for SSH connection, ONU provisioning, and monitoring.
"""

import os
import time
import re
import csv
import xml.etree.ElementTree as ET
from typing import List, Tuple, Optional, Dict, Any
from contextlib import contextmanager

import pexpect
from dotenv import load_dotenv
from utils.log import get_logger
from textual.app import App, ComposeResult
from textual.widgets import DataTable, Header, Footer
from rich.text import Text

# Constants
DEFAULT_TIMEOUT = 10
EXTENDED_TIMEOUT = 30
STABILIZATION_WAIT_TIME = 3
DISCOVERY_WAIT_TIME = 5
PON_CAPACITY = 128
MAX_MAC_ADDRESSES = 4
COMMITTED_MAC_ADDRESSES = 1
EXTENDED_MAC_ADDRESSES = 10

# Logger configuration
logger = get_logger(__name__)
logger.info("Sistema iniciado")

# Load environment variables
load_dotenv()
SSH_USER = os.getenv('SSH_USER')
SSH_PASSWORD = os.getenv('SSH_PASSWORD')
SSH_PORT = os.getenv('PORT')

class ONUListApp(App):
    def __init__(self, data, **kwargs):
        super().__init__(**kwargs)
        self.onu_data = data

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()
        self.table = DataTable()
        yield self.table

    def on_mount(self):
        self.table.add_columns("Posição", "Serial", "Nome", "Modo", "Admin", "Operacional", "RX (dBm)", "Temperatura (°C)", "distance(km)")
        for row in self.onu_data:
            admin = Text(row[4], style="green" if row[4].lower() == "up" else "red")
            oper = Text(row[5], style="green" if row[5].lower() == "up" else "red")
            self.table.add_row(row[0], row[1], row[2], row[3], admin, oper, row[6], row[7], row[8])


def login_olt_ssh(host: str = None) -> Optional[pexpect.spawn]:
    """Estabelece conexão SSH com a OLT"""
    try:
        logger.info("Iniciando conexão SSH e obtendo variáveis de ambiente")

        if not all([SSH_USER, host, SSH_PASSWORD, SSH_PORT]):
            error_msg = "Variáveis de ambiente não configuradas corretamente"
            logger.error(error_msg)
            raise ValueError(error_msg)

        logger.info(f"Conectando à OLT | Usuário: {SSH_USER} | OLT: {host}")
        child = pexpect.spawn(f"ssh {SSH_USER}@{host} -p {SSH_PORT}", 
                                encoding='utf-8', 
                                timeout=EXTENDED_TIMEOUT)

        index = child.expect([
            "password:", 
            "Are you sure you want to continue connecting", 
            pexpect.TIMEOUT
        ], timeout=DEFAULT_TIMEOUT)

        if index == 1:
            logger.debug("Primeira conexão SSH - Aceitando certificado")
            child.sendline("yes")
            child.expect("password:")

        logger.debug("Enviando senha SSH")
        child.sendline(SSH_PASSWORD)

        login_success = child.expect([
            r"typ:isadmin>#", 
            pexpect.TIMEOUT, 
            pexpect.EOF
        ], timeout=DEFAULT_TIMEOUT)

        if login_success == 0:
            logger.info(f"Autenticado com sucesso na OLT {host}")
            print(f"✅ Conectado com sucesso à OLT {host}")
            
            # Configuração inicial da sessão
            child.sendline("environment inhibit-alarms")
            child.expect("#")
            child.sendline("exit")
            child.expect("#")
            logger.info("Alarmes desativados com sucesso")
            return child
        else:
            logger.error("Falha na autenticação SSH")
            print("❌ Falha na autenticação")
            return None

    except pexpect.EOF:
        logger.error("Conexão fechada inesperadamente")
        print("❌ Conexão encerrada antes da autenticação")
    except pexpect.exceptions.ExceptionPexpect as e:
        logger.error(f"Erro de conexão SSH: {e}")
        print(f"❌ Erro de conexão: {e}")
    except Exception as e:
        logger.error(f"Erro inesperado: {e}")
        print(f"❌ Erro inesperado: {e}")
    
    return None

def check_onu_position(child: pexpect.spawn, serial: str) -> Optional[Tuple[str, str, str]]:
    """Check ONU position on the OLT"""
    try:
        logger.info(f"Verificando posição da ONU com serial: {serial}")
        child.sendline(f"show equipment ont status pon | match match exact:{serial}")
        child.expect("#", timeout=DEFAULT_TIMEOUT)
        output = child.before

        match = re.search(r"(\d+)\/(\d+)\/(\d+)\/(\d+)\/(\d+)", output)
        if not match:
            msg = "ONU não encontrada na OLT. Verifique o serial informado."
            logger.warning(msg)
            print(f"❌ {msg}")
            return None

        slot, pon, position = match.group(3), match.group(4), match.group(5)
        logger.info(f"ONU detectada: Slot {slot}, PON {pon}, Posição {position}")
        print("✅ ONU detectada.")
        return slot, pon, position
        
    except pexpect.exceptions.TIMEOUT:
        logger.error("Timeout ao verificar posição da ONU")
        print("❌ Timeout ao verificar posição da ONU")
        return None
    except Exception as e:
        logger.error(f"Erro ao verificar posição da ONU: {e}")
        print(f"❌ Erro: {e}")
        return None

def list_unauthorized(child: pexpect.spawn) -> List[Tuple[str, str, str]]:
    """Lista as ONUs não autorizadas na OLT"""
    logger.info("Iniciando busca por ONUs não autorizadas...")
    onu_list: List[Tuple[str, str, str]] = []
    
    try:
        cmd = "show pon unprovision-onu"
        child.sendline(cmd)
        logger.info(f"Enviando comando: {cmd}")
        time.sleep(STABILIZATION_WAIT_TIME)
        child.expect("#", timeout=DEFAULT_TIMEOUT)
        output = child.before.decode('utf-8', errors='ignore') if isinstance(child.before, bytes) else child.before
        
        lines = output.splitlines()
        for line in lines:
            if "1/1/" in line:
                parts = line.strip().split()
                for idx, part in enumerate(parts):
                    if "1/1/" in part:
                        try:
                            slot = part.split('/')[2]
                            pon = part.split('/')[3]
                            serial = parts[idx + 1]
                            onu_list.append((serial.strip(), slot, pon))
                        except (IndexError, ValueError) as e:
                            logger.warning(f"Erro ao processar linha: '{line}' -> {e}")
                            continue
        
        # Exibe a lista formatada
        if onu_list:
            print("----------------------------------------")
            print("Serial           | Slot | PON")
            print("----------------------------------------")
            for serial, slot, pon in onu_list:
                print(f"{serial:<16} | {slot:<4} | {pon}")
            print("----------------------------------------")
            print(f"Total de ONUs não autorizadas: {len(onu_list)}\n")
        else:
            print("Nenhuma ONU não autorizada encontrada.\n")
        
        logger.info(f"Busca concluída. Total de ONUs não autorizadas: {len(onu_list)}")
        return onu_list

    except pexpect.exceptions.TIMEOUT as e:
        logger.error(f"Timeout ao listar ONUs não autorizadas: {e}")
        print("❌ Timeout ao listar ONUs não autorizadas.")
        return []
    except Exception as e:
        logger.error(f"Erro inesperado ao listar ONUs não autorizadas: {e}")
        print("❌ Erro inesperado ao listar ONUs não autorizadas.")
        return []

def return_signal_temp(child: pexpect.spawn, slot: str, pon: str, position: str) -> bool:
    """Return signal and temperature information for ONU"""
    logger.info("Iniciando verificação de sinal e temperatura da ONU")
    try:
        child.sendline(f"show equipment ont optics 1/1/{slot}/{pon}/{position} detail")
        child.expect("#", timeout=DEFAULT_TIMEOUT)
        sinal_temp = child.before.strip()
        logger.debug(f"Saída do comando optics: {sinal_temp}")

        match = re.search(r"rx-signal-level\s*:\s*(-\d+\.\d{2}).*?ont-temperature\s*:\s*(\d{2})", sinal_temp, re.DOTALL)
        if match:
            rx_signal = match.group(1)
            temperature = match.group(2)
            logger.info(f"Sinal: {rx_signal} dBm | Temperatura: {temperature} ºC")
            print(f"Sinal: {rx_signal}dBm\nTemperatura: {temperature}ºC")
            return True
        else:
            logger.warning("Dados de sinal/temperatura não encontrados")
            print("❌ Dados de sinal/temperatura não encontrados")
            return False

    except pexpect.exceptions.TIMEOUT:
        logger.error("Timeout ao obter informações ópticas")
        print("❌ Timeout ao obter informações ópticas")
        return False
    except Exception as e:
        logger.error(f"Erro ao obter sinal/temperatura: {e}")
        print(f"❌ Erro: {e}")
        return False

def checkfreeposition(child: pexpect.spawn, slot: str, pon: str) -> int:
    """Check free position on PON"""
    logger.info(f"Verificando posição livre na PON {slot}/{pon}")
    posocupadas = []
    capacidade_pon = range(1, PON_CAPACITY + 1)  # 1 até 128 inclusive

    try:
        child.sendline(f'show equipment ont status pon 1/1/{slot}/{pon}')
        child.expect('#', timeout=DEFAULT_TIMEOUT)

        saida = child.before.decode() if isinstance(child.before, bytes) else child.before
        linhas = saida.splitlines()

        for line in linhas:
            if f'1/1/{slot}/{pon}/' in line:
                try:
                    partes = line.split()
                    if len(partes) >= 2:
                        ont_path = partes[1]  # Ex: '1/1/1/1/1'
                        pos = int(ont_path.split('/')[4])
                        posocupadas.append(pos)
                except (IndexError, ValueError):
                    continue

        posicoes_livres = sorted(set(capacidade_pon) - set(posocupadas))
        if not posicoes_livres:
            raise Exception("Nenhuma posição livre disponível")

        menorposlivre = posicoes_livres[0]
        logger.info(f"Menor posição livre encontrada: {menorposlivre}")
        return menorposlivre

    except Exception as e:
        logger.error(f"Erro ao validar posição livre: {e}")
        raise

def add_to_pon(child: pexpect.spawn, slot: str, pon: str, position: str, 
                serial: str, name: str, desc2: str) -> bool:
    """Add ONU to PON for initial provisioning"""
    logger.info("Adicionando a ONT na PON para consultar modelo")
    
    try:
        # Provisionamento inicial
        cmd = (f"configure equipment ont interface 1/1/{slot}/{pon}/{position} "
                f"sernum {serial} sw-ver-pland disabled desc1 \"{name}\" "
                f"desc2 \"{desc2}\" optics-hist enable")
        child.sendline(cmd)
        logger.info(f"Enviando comando de provisionamento: {cmd}")
        child.expect(r"\$")  # Espera pelo prompt $
        logger.info(f"ONU provisionada em 1/1/{slot}/{pon}/{position}")
        
        child.sendline("admin-state up")
        logger.info("Enviando comando: admin-state up")
        child.expect(r"\$")  # Espera pelo prompt $
        
        child.sendline("exit all")
        logger.info("Enviando comando: exit all")
        child.expect("#")  # Espera pelo prompt #
        
        logger.info("ONU está UP e pronta para uso.")
        logger.info("Aguardando 20 segundos para estabilidade...")
        time.sleep(20)
        
        return True
        
    except Exception as e:
        logger.error(f"Erro no provisionamento inicial da ONU: {e}")
        print("Houve um problema ao provisionar a ONU na PON")
        return False

def onu_model(child: pexpect.spawn, slot: str, pon: str, position: str) -> Optional[str]:
    """Get ONU model information"""
    try:
        logger.info(f"Verificando modelo da ONU em 1/1/{slot}/{pon}/{position}")
        child.sendline(f"show equipment ont interface 1/1/{slot}/{pon}/{position} detail")
        child.expect("#", timeout=15)
        output = child.before.strip()
        
        # Procura pelo padrão do modelo no output
        match = re.search(r"equip-id\s*:\s*([^\n\r]+?)(?=\s{2,}|$)", output, re.MULTILINE)

        if not match:
            logger.warning("Modelo da ONU não encontrado na saída do comando")
            print("❗ Modelo da ONU não encontrado")
            return None
            
        model = match.group(1).strip()
        logger.info(f"Modelo detectado: {model}")
        print(f"✅ Modelo detectado: {model}")
        return model
        
    except pexpect.exceptions.TIMEOUT:
        logger.error("Tempo esgotado ao tentar obter modelo da ONU")
        print("❗ Tempo esgotado ao verificar modelo da ONU")
        return None
    except pexpect.exceptions.ExceptionPexpect as e:
        logger.error(f"Erro de comunicação: {str(e)}")
        print(f"❗ Erro de comunicação: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Erro inesperado ao obter modelo: {str(e)}")
        print(f"❗ Erro inesperado: {str(e)}")
        return None

def auth_group01_ssh(child: pexpect.spawn, slot: str, pon: str, position: str, vlan: str) -> bool:
    """SSH authentication for Group 01 ONUs"""
    logger.info("Iniciando autorização do grupo 01 via SSH")
    
    try:
        time.sleep(STABILIZATION_WAIT_TIME)
    except Exception as e:
        logger.warning(f"Problema ao esperar: {e}")

    comandos = [
        (f"configure equipment ont slot 1/1/{slot}/{pon}/{position}/1 plndnumdataports 1 plndnumvoiceports 0 planned-card-type ethernet admin-state up", "$", "Configurar slot da ONT"),
        (f"configure interface port uni:1/1/{slot}/{pon}/{position}/1/1 admin-up", "#", "Habilitar porta UNI"),
        (f"configure qos interface 1/1/{slot}/{pon}/{position}/1/1 upstream-queue 0 bandwidth-profile name:HSI_1G_UP", "#", "Configurar QoS na porta UNI"),
        ("exit all", "#", "Sair do modo de configuração"),
        (f"configure bridge port 1/1/{slot}/{pon}/{position}/1/1 max-unicast-mac {MAX_MAC_ADDRESSES} max-committed-mac {COMMITTED_MAC_ADDRESSES}", "$", "Configurar limite de MACs na bridge"),
        (f"configure bridge port 1/1/{slot}/{pon}/{position}/1/1 vlan-id {vlan} tag untagged", "$", "Atribuir VLAN à porta bridge (untagged)"),
        ("exit all", "#", "Sair do modo de configuração"),
        (f"configure bridge port 1/1/{slot}/{pon}/{position}/1/1 pvid {vlan}", "#", "Definir PVID na porta bridge"),
        ("pvid-tagging-flag onu", "#", "Configurar pvid-tagging-flag para ONU"),
    ]

    for cmd, prompt, descricao in comandos:
        try:
            child.sendline(cmd)
            logger.info(f"Enviando comando: {descricao} -> {cmd}")
            child.expect(prompt, timeout=DEFAULT_TIMEOUT)
            logger.info(f"Comando concluído com sucesso: {descricao}")
        except Exception as e:
            logger.error(f"Erro ao executar comando '{descricao}': {e}")
            print(f"Houve um problema durante: {descricao}")
            return False

    logger.info("Configuração do grupo 01 concluída com sucesso.")
    return True

def auth_group02_ssh(child: pexpect.spawn, slot: str, pon: str, position: str, vlan: str) -> bool:
    """SSH authentication for Group 02 ONUs"""
    logger.info("Iniciando autorização do grupo 02 via SSH")
    
    try:
        time.sleep(STABILIZATION_WAIT_TIME)
    except Exception as e:
        logger.warning(f"Problema ao aguardar: {e}")

    comandos = [
        (f"configure equipment ont slot 1/1/{slot}/{pon}/{position}/1 plndnumdataports 1 plndnumvoiceports 0 planned-card-type ethernet admin-state up", "$", "Configurar slot da ONT"),
        (f"configure interface port uni:1/1/{slot}/{pon}/{position}/1/1 admin-up", "#", "Habilitar porta UNI"),
        (f"configure qos interface 1/1/{slot}/{pon}/{position}/1/1 upstream-queue 0 bandwidth-profile name:HSI_1G_UP", "#", "Configurar QoS na porta UNI"),
        ("exit all", "#", "Sair do modo de configuração"),
        (f"configure bridge port 1/1/{slot}/{pon}/{position}/1/1 max-unicast-mac {MAX_MAC_ADDRESSES} max-committed-mac {COMMITTED_MAC_ADDRESSES}", "$", "Configurar limite de MACs na bridge"),
        (f"configure bridge port 1/1/{slot}/{pon}/{position}/1/1 vlan-id {vlan} tag untagged", "$", "Atribuir VLAN à porta bridge (untagged)"),
        ("exit all", "#", "Sair do modo de configuração"),
        (f"configure bridge port 1/1/{slot}/{pon}/{position}/1/1 pvid {vlan}", "#", "Definir PVID na porta bridge"),
        ("pvid-tagging-flag olt", "#", "Configurar pvid-tagging-flag para OLT"),
    ]

    for cmd, prompt, descricao in comandos:
        try:
            child.sendline(cmd)
            logger.info(f"Enviando comando: {descricao} -> {cmd}")
            child.expect(prompt, timeout=DEFAULT_TIMEOUT)
            logger.info(f"Comando concluído com sucesso: {descricao}")
        except Exception as e:
            logger.error(f"Erro ao executar comando '{descricao}': {e}")
            print(f"Houve um problema durante: {descricao}")
            return False

    logger.info("Configuração do grupo 02 concluída com sucesso.")
    return True

def auth_group03_ssh(child: pexpect.spawn, slot: str, pon: str, position: str, vlan: str, model: Optional[str] = None) -> bool:
    """SSH authentication for Group 03 ONUs"""
    logger.info("Iniciando autorização do grupo 03 via SSH")
    
    try:
        time.sleep(STABILIZATION_WAIT_TIME)
    except Exception as e:
        logger.warning(f"Problema ao aguardar: {e}")

    comandos = [
        (f"configure qos interface ont:1/1/{slot}/{pon}/{position} ds-queue-sharing", "$", "Configurar qos da ONT"),
        ("exit all", "#", "Sair do modo de configuração"),
        (f"configure equipment ont slot 1/1/{slot}/{pon}/{position}/1 plndnumdataports 1 plndnumvoiceports 0 planned-card-type ethernet admin-state up", "$", "Configurar slot da ONT"),
        (f"configure interface port uni:1/1/{slot}/{pon}/{position}/1/1 admin-up", "#", "Habilitar porta UNI"),
        (f"configure qos interface 1/1/{slot}/{pon}/{position}/1/1 upstream-queue 0 bandwidth-profile name:HSI_1G_UP", "#", "Configurar QoS na porta UNI"),
        (f"configure qos interface 1/1/{slot}/{pon}/{position} queue 0 shaper-profile name:HSI_1G_DOWN", "#", "Configurar QoS na porta UNI"),
        ("exit all", "#", "Sair do modo de configuração"),
        (f"configure bridge port 1/1/{slot}/{pon}/{position}/1/1 max-unicast-mac {EXTENDED_MAC_ADDRESSES}", "$", "Configurar limite de MACs na bridge"),
        (f"configure bridge port 1/1/{slot}/{pon}/{position}/1/1 vlan-id {vlan} tag untagged", "$", "Atribuir VLAN à porta bridge (untagged)"),
        ("exit all", "#", "Sair do modo de configuração"),
        (f"configure bridge port 1/1/{slot}/{pon}/{position}/1/1 pvid {vlan}", "#", "Definir PVID na porta bridge"),
    ]

    for cmd, prompt, descricao in comandos:
        try:
            child.sendline(cmd)
            logger.info(f"Enviando comando: {descricao} -> {cmd}")
            child.expect(prompt, timeout=DEFAULT_TIMEOUT)
            logger.info(f"Comando concluído com sucesso: {descricao}")
        except Exception as e:
            logger.error(f"Erro ao executar comando '{descricao}': {e}")
            print(f"Houve um problema durante: {descricao}")
            return False

    logger.info("Configuração do grupo 03 concluída com sucesso.")
    return True

def auth_especific_model_AN5506_ssh(child: pexpect.spawn, slot: str, pon: str, position: str, vlan: str, model: Optional[str] = None) -> bool:
    """SSH authentication for Fiberhome AN5506-01-A Grande ONUs"""
    logger.info("Iniciando autorização de Fiberhome AN5506-01-A Grande via SSH")

    try:
        time.sleep(STABILIZATION_WAIT_TIME)
    except Exception as e:
        logger.warning(f"Problema ao aguardar: {e}")

    try:
        print("Provisionando a ONU no modo correto para o Hardware...")
        comandos = [
            (f"configure qos interface ont:1/1/{slot}/{pon}/{position} ds-queue-sharing", "#", "Configurar qos da ONT"),
            (f"configure equipment ont slot 1/1/{slot}/{pon}/{position}/1 plndnumdataports 1 plndnumvoiceports 0 planned-card-type ethernet admin-state up", "$", "Configurar slot da ONT"),
            (f"configure qos interface 1/1/{slot}/{pon}/{position}/1/1 upstream-queue 0 bandwidth-profile name:HSI_1G_UP", "#", "Configurar QoS upstream"),
            (f"configure qos interface ont:1/1/{slot}/{pon}/{position} queue 0 shaper-profile name:HSI_1G_DOWN", "#", "Configurar QoS downstream"),
            (f"configure interface port uni:1/1/{slot}/{pon}/{position}/1/1 admin-up", "#", "Habilitar porta UNI"),
            (f"configure bridge port 1/1/{slot}/{pon}/{position}/1/1 max-unicast-mac {EXTENDED_MAC_ADDRESSES}", "$", "Configurar limite de MACs"),
            (f"configure bridge port 1/1/{slot}/{pon}/{position}/1/1 vlan-id {vlan} tag untagged", "$", "Atribuir VLAN"),
            (f"configure bridge port 1/1/{slot}/{pon}/{position}/1/1 pvid {vlan}", "#", "Definir PVID na porta bridge"),
            ("exit all", "#", "Sair do modo de configuração"),
        ]

        for cmd, prompt, descricao in comandos:
            try:
                child.sendline(cmd)
                logger.info(f"Enviando comando: {descricao} -> {cmd}")
                child.expect(prompt, timeout=DEFAULT_TIMEOUT)
                logger.info(f"Comando concluído com sucesso: {descricao}")
                time.sleep(1)
            except Exception as e:
                logger.error(f"Erro ao executar comando '{descricao}': {e}")
                print(f"Houve um problema durante: {descricao}")
                return False

    except Exception as e:
        logger.error(f"Erro no bloco de reprovisionamento: {e}")
        return False

    logger.info("Configuração da Fiberhome Grande concluída com sucesso.")
    return True

def unauthorized(child: pexpect.spawn, serial_ssh: str, slot: str, pon: str, position: str) -> bool:
    """Unauthorize an ONU from the OLT"""
    try:
        logger.info(f"Iniciando desautorização da ONU {serial_ssh}")
        commands = [
            f"configure equipment ont interface 1/1/{slot}/{pon}/{position} admin-state down",
            f"configure equipment ont no interface 1/1/{slot}/{pon}/{position}",
            "exit all"
        ]

        for cmd in commands:
            try:
                child.sendline(cmd)
                child.expect("#", timeout=DEFAULT_TIMEOUT)
                if "error" in child.before.lower():
                    logger.error(f"Erro no comando: {cmd} - Saída: {child.before}")
                    print(f"❌ Falha ao executar comando na OLT")
                    return False
            except pexpect.TIMEOUT:
                logger.error(f"Timeout no comando: {cmd}")
                print("❌ Tempo esgotado na execução do comando")
                return False

        logger.info(f"ONU {serial_ssh} desautorizada com sucesso")
        return True

    except pexpect.ExceptionPexpect as e:
        logger.error(f"Erro de comunicação: {str(e)}", exc_info=True)
        print("❌ Erro de comunicação com a OLT")
        return False
    except Exception as e:
        logger.error(f"Erro inesperado: {str(e)}", exc_info=True)
        print("❌ Erro inesperado no processo")
        return False

def format_ssh_serial(serial: str) -> str:
    """Format serial for SSH protocol"""
    logger.info(f"Iniciando formatação do serial: {serial}")

    try:
        serial = serial.upper()[:12]
        if len(serial) > 4:
            serial = serial[:4] + ':' + serial[4:]
        logger.info(f"Serial formatado para SSH: {serial}")
        return serial
    except Exception as e:
        logger.error(f"Erro ao formatar o serial '{serial}': {e}")
        return ""

def list_onu(child: pexpect.spawn, slot: str, pon: str) -> bool:
    """List ONUs on a specific PON and save to CSV"""
    try:
        logger.info(f"Iniciando listagem das ONUs da PON 1/1/{slot}/{pon}")
        child.sendline(f"show equipment ont status pon 1/1/{slot}/{pon} xml")
        time.sleep(DISCOVERY_WAIT_TIME)
        child.expect("#", timeout=15)
        output = child.before
        logger.debug("Saída recebida da OLT:\n" + output)

        # Extract XML content
        start_index = output.find("<?xml")
        if start_index == -1:
            logger.error("Início do XML ('<?xml') não encontrado na saída.")
            print("❌ XML não encontrado na resposta da OLT")
            return False

        end_tag = "</runtime-data>"
        end_index = output.find(end_tag, start_index)
        if end_index == -1:
            logger.error("Tag de fechamento do XML não encontrada na saída.")
            print("❌ XML incompleto na resposta da OLT")
            return False

        xml_content = output[start_index:end_index + len(end_tag)]
        logger.debug(f"Conteúdo XML extraído:\n{xml_content}")

        # Parse XML
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as e:
            logger.error(f"Falha ao fazer parse do XML: {e}, conteúdo XML:\n{xml_content}")
            print("❌ Erro ao interpretar o XML")
            return False

        # Process ONU data
        data = []
        for instance in root.findall(".//instance"):
            serial = instance.findtext(".//info[@name='sernum']", default="").strip()
            ont_id = instance.findtext(".//res-id[@name='ont']", default="").strip()
            position = ont_id.split('/')[-1] if ont_id else ""
            name = instance.findtext(".//info[@name='desc1']", default="").strip().replace('"', '')
            model = instance.findtext(".//info[@name='desc2']", default="").strip()  

            if not serial or serial.lower() == "undefined":
                continue

            data.append([serial.replace(":", ""), pon, position, name, model])
            logger.debug(f"ONU - SERIAL: {serial}, PON: {pon}, POSIÇÃO: {position}, NAME: {name}, MODEL: {model}")

        if not data:
            logger.warning(f"Nenhuma ONU encontrada na PON 1/1/{slot}/{pon}")
            print(f"⚠️ Nenhuma ONU encontrada na PON 1/1/{slot}/{pon}")
            return False

        # Create CSV file
        os.makedirs("csv", exist_ok=True)
        file_path = os.path.join("csv", f"onulist_slot{slot}_pon{pon}.csv")

        with open(file_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["SERIAL", "PON", "POSITION", "NAME", "MODEL"])
            writer.writerows(data)

        logger.info(f"✅ CSV gerado com sucesso: {file_path} ({len(data)} ONUs)")
        print(f"✅ CSV gerado: {file_path}")
        return True

    except pexpect.TIMEOUT:
        logger.error(f"Timeout ao esperar resposta da OLT na PON 1/1/{slot}/{pon}")
        print("❌ Timeout na comunicação com a OLT")
        return False
    except pexpect.ExceptionPexpect as e:
        logger.error(f"Erro de comunicação com a OLT: {e}", exc_info=True)
        print("❌ Erro de comunicação com a OLT")
        return False
    except Exception as e:
        logger.error(f"Erro inesperado: {e}", exc_info=True)
        print("❌ Erro inesperado ao listar ONUs")
        return False

def list_pon(child: pexpect.spawn, slot: str, pon: str) -> bool:
    """List PON status with detailed ONU information"""
    try:
        print(f"Iniciando listagem da PON 1/1/{slot}/{pon}")
        child.sendline(f"show equipment ont status pon 1/1/{slot}/{pon} xml")
        time.sleep(DISCOVERY_WAIT_TIME)
        child.expect("#", timeout=EXTENDED_TIMEOUT)
        output = child.before

        start_index = output.find("<?xml")
        end_index = output.find("</runtime-data>") + len("</runtime-data>")
        if start_index == -1 or end_index == -1:
            print("❌ XML não encontrado ou incompleto")
            return False

        xml_content = output[start_index:end_index]
        root = ET.fromstring(xml_content)
        data = []

        for instance in root.findall(".//instance"):
            ont_id = instance.findtext(".//res-id[@name='ont']")
            position = ont_id.split('/')[-1] if ont_id else ""
            serial = instance.findtext(".//info[@name='sernum']", default="").replace(":", "")
            name = instance.findtext(".//info[@name='desc1']", default="").replace('"', '').strip()
            modo = instance.findtext(".//info[@name='desc2']", default="").strip()
            admin_status = instance.findtext(".//info[@name='admin-status']", default="").strip()
            oper_status = instance.findtext(".//info[@name='oper-status']", default="").strip()
            distance = instance.findtext(".//info[@name='ont-olt-distance(km)']", default="").strip()

            if not serial or serial.lower() == "undefined":
                continue

            # Get optical information for each ONU
            try:
                # Clear buffer
                try:
                    child.read_nonblocking(size=1024, timeout=1)
                except:
                    pass

                child.sendline(f"show equipment ont optics 1/1/{slot}/{pon}/{position} detail")
                child.expect([r"#", pexpect.TIMEOUT], timeout=EXTENDED_TIMEOUT)
                optics_output = child.before

                match = re.search(r"rx-signal-level\s*:\s*(-\d+\.\d{2}).*?ont-temperature\s*:\s*(\d{2})", optics_output, re.DOTALL)
                rx_signal = match.group(1) if match else "N/A"
                temperature = match.group(2) if match else "N/A"

            except Exception as optics_err:
                print(f"⚠️ Falha ao obter óticos da ONU {position}: {optics_err}")
                rx_signal = "Erro"
                temperature = "Erro"

            print(f"✅ ONU {position}")
            data.append([position, serial, name, modo, admin_status, oper_status, rx_signal, temperature, distance])

        if not data:
            print(f"⚠️ Nenhuma ONU encontrada na PON 1/1/{slot}/{pon}")
            return False

        ONUListApp(data).run()
        return True

    except Exception as e:
        print(f"❌ Erro geral: {e}")
        return False
