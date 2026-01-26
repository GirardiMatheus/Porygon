"""
Datacom SSH module for OLT management operations.
Provides functions for SSH connection, ONU provisioning, and monitoring.
"""

import os
import time
import pexpect
from typing import Optional
from dotenv import load_dotenv
from utils.log import get_logger
from textual.app import App, ComposeResult
from textual.widgets import DataTable, Static
from textual.containers import Container
from rich.text import Text

# Constants
DEFAULT_TIMEOUT = 10
EXTENDED_TIMEOUT = 30

# Logger configuration
logger = get_logger(__name__)
logger.info("Sistema iniciado")

# Load environment variables
load_dotenv()
SSH_USER = os.getenv('SSH_USER_DATACOM')
SSH_PASSWORD = os.getenv('SSH_PASSWORD_DATACOM')
SSH_PORT = os.getenv('PORT')



def login_olt_ssh_datacom(host: str = None) -> Optional[pexpect.spawn]:
    """Estabelece conexão SSH com a OLT Datacom"""
    try:
        logger.info("Iniciando conexão SSH Datacom e obtendo variáveis de ambiente")

        if not all([SSH_USER, host, SSH_PASSWORD, SSH_PORT]):
            error_msg = "Variáveis de ambiente não configuradas corretamente"
            logger.error(error_msg)
            raise ValueError(error_msg)

        logger.info(f"Conectando à OLT Datacom | Usuário: {SSH_USER} | OLT: {host}")
        child = pexpect.spawn(f"ssh {SSH_USER}@{host} -p {SSH_PORT}", 
                                encoding='utf-8', 
                                timeout=EXTENDED_TIMEOUT)

        # Espera pela solicitação de senha da Datacom
        index = child.expect([
            r"\(.*\) Password:", 
            "Are you sure you want to continue connecting", 
            pexpect.TIMEOUT
        ], timeout=DEFAULT_TIMEOUT)

        if index == 1:
            logger.debug("Primeira conexão SSH - Aceitando certificado")
            child.sendline("yes")
            child.expect(r"\(.*\) Password:")

        logger.debug("Enviando senha SSH Datacom")
        child.sendline(SSH_PASSWORD)

        # Aguarda pelo prompt da Datacom que termina com "#"
        login_success = child.expect([
            r".*#\s*$", 
            pexpect.TIMEOUT, 
            pexpect.EOF
        ], timeout=DEFAULT_TIMEOUT)

        if login_success == 0:
            logger.info(f"Autenticado com sucesso na OLT Datacom {host}")
            print(f"Conectado com sucesso à OLT Datacom {host}")
            
            # Aguarda estabilização da sessão
            time.sleep(2)
            
            logger.info("Sessão SSH Datacom estabelecida com sucesso")
            return child
        else:
            logger.error("Falha na autenticação SSH Datacom")
            print("Falha na autenticação Datacom")
            return None

    except pexpect.EOF:
        logger.error("Conexão fechada inesperadamente")
        print("Conexão encerrada antes da autenticação")
    except pexpect.exceptions.ExceptionPexpect as e:
        logger.error(f"Erro de conexão SSH Datacom: {e}")
        print(f"Erro de conexão Datacom: {e}")
    except Exception as e:
        logger.error(f"Erro inesperado na conexão Datacom: {e}")
        print(f"Erro inesperado Datacom: {e}")
    
    return None


def list_unauthorized(host: str) -> Optional[list]:
    """Lista ONUs não autorizadas na OLT Datacom"""
    child = None
    try:
        child = login_olt_ssh_datacom(host)
        if not child:
            return None

        logger.info("Listando ONUs não autorizadas")
        child.sendline("show interface gpon discovered-onus")
        child.expect("#", timeout=EXTENDED_TIMEOUT)

        output = child.before
        logger.info(f"ONUs não autorizadas: {output}")

        # Parse da saída para extrair dados das ONUs não autorizadas
        unauthorized_onus = []
        lines = output.split('\n')
        
        # Verifica se não há entradas
        if "No entries found" in output:
            logger.info("Nenhuma ONU não autorizada encontrada")
            return []
        
        for line in lines:
            line = line.strip()
            # Pula linhas vazias, cabeçalhos, separadores e comandos
            if (not line or 
                line.startswith('show interface gpon') or
                line.startswith('Chassis') or 
                line.startswith('---') or 
                'Serial Number' in line or
                'No entries found' in line or
                line.endswith('#')):
                continue
            
            # Processa linhas que contêm dados de ONUs
            fields = line.split()
            if len(fields) >= 2:
                try:
                    # Formato: Chassis/Slot/Port SerialNumber
                    interface = fields[0]
                    serial_number = fields[1] if len(fields) > 1 else "N/A"
                    
                    # Verifica se é uma interface válida (formato x/x/x)
                    if '/' in interface and len(interface.split('/')) >= 3:
                        onu_info = {
                            "interface": interface,
                            "serial": serial_number,
                            "status": "Discovered"  # ONUs descobertas sempre têm status "Discovered"
                        }
                        unauthorized_onus.append(onu_info)
                        logger.debug(f"ONU não autorizada encontrada: {interface} - {serial_number}")
                        
                except (IndexError, ValueError) as e:
                    logger.warning(f"Erro ao processar linha: {line} - {e}")
                    continue

        logger.info(f"Total de ONUs não autorizadas encontradas: {len(unauthorized_onus)}")
        return unauthorized_onus

    except pexpect.exceptions.ExceptionPexpect as e:
        error_msg = f"Erro de comunicação SSH ao listar ONUs não autorizadas: {e}"
        logger.error(error_msg)
        print(f"{error_msg}")
    except Exception as e:
        error_msg = f"Erro inesperado ao listar ONUs não autorizadas: {e}"
        logger.error(error_msg)
        print(f"{error_msg}")
    finally:
        # Cleanup da sessão SSH
        if child and child.isalive():
            try:
                child.sendline("exit")
                child.close()
                logger.debug("Sessão SSH encerrada com sucesso")
            except:
                logger.warning("Erro ao encerrar sessão SSH graciosamente")

    return None

def check_free_position(host: str, pon: str) -> Optional[int]:
    """Verifica a menor posição livre para provisionamento de ONU na OLT Datacom"""
    try:
        child = login_olt_ssh_datacom(host)
        if not child:
            return None

        logger.info(f"Verificando posição livre na porta {pon}")
        child.sendline(f"show interface gpon 1/1/{pon} onu")
        child.expect("#", timeout=EXTENDED_TIMEOUT)

        output = child.before
        logger.info(f"Saída do comando: {output}")

        all_positions = set(range(128))
        occupied_positions = set()

        lines = output.split('\n')
        for line in lines:
            line = line.strip()
            if not line or line.startswith('Itf') or line.startswith('---') or 'ONU ID' in line:
                continue
            
            fields = line.split()
            if len(fields) >= 2:
                try:
                    onu_id = int(fields[1])
                    if 0 <= onu_id <= 127:
                        occupied_positions.add(onu_id)
                        logger.debug(f"Posição ocupada encontrada: {onu_id}")
                except ValueError:
                    continue

        available_positions = all_positions - occupied_positions
        
        if available_positions:
            smallest_available = min(available_positions)
            logger.info(f"Menor posição livre encontrada: {smallest_available}")
            return smallest_available
        else:
            logger.info("Nenhuma posição livre disponível (0-127)")
            return None

    except Exception as e:
        logger.error(f"Erro ao verificar posição livre: {e}")
        print(f"Erro ao verificar posição livre: {e}")

    return None

def add_onu(host: str, pon: str, onu_id: int, serial_number: str, description: str, vlan: int) -> Optional[str]:
    """Adiciona uma ONU na OLT Datacom"""
    child = None
    try:
        # Validação de parâmetros
        if not all([host, pon, serial_number, description]) or onu_id is None or vlan is None:
            error_msg = "Parâmetros obrigatórios não fornecidos"
            logger.error(error_msg)
            return None

        if not (0 <= onu_id <= 127):
            error_msg = f"ONU ID {onu_id} fora do range válido (0-127)"
            logger.error(error_msg)
            return None

        child = login_olt_ssh_datacom(host)
        if not child:
            return None

        logger.info(f"Iniciando provisionamento - ONU {onu_id} | PON {pon} | VLAN {vlan} | Serial {serial_number}")
        
        # Comandos de configuração em sequência
        commands = [
            ("configure terminal", "Entrando no modo de configuração"),
            (f"interface gpon 1/1/{pon}", f"Acessando interface GPON 1/1/{pon}"),
            (f"onu {onu_id}", f"Criando ONU {onu_id}"),
            (f"serial-number {serial_number}", f"Configurando serial number {serial_number}"),
            (f"name {description}", f"Configurando descrição: {description}"),
            (f"line-profile BRIDGE_VLAN_{vlan}_PON{pon}", f"Aplicando line-profile BRIDGE_VLAN_{vlan}_PON{pon}"),
            ("ethernet 1", "Configurando interface ethernet 1"),
            (f"native vlan vlan-id {vlan}", f"Configurando VLAN nativa {vlan}"),
            ("exit", "Saindo da configuração ethernet"),
            ("snmp profile ONU-ONT", "Aplicando perfil SNMP ONU-ONT"),
            ("top", "Retornando ao nível superior")
        ]

        for command, description in commands:
            logger.debug(f"Executando: {command} - {description}")
            child.sendline(command)
            
            index = child.expect([
                r".*#\s*$",
                r".*\(config.*\)#\s*$", 
                pexpect.TIMEOUT,
                "Error",
                "Invalid"
            ], timeout=EXTENDED_TIMEOUT)
            
            if index in [2, 3, 4]:  # Timeout, Error ou Invalid
                error_msg = f"Erro ao executar comando '{command}': {child.before if hasattr(child, 'before') else 'Timeout'}"
                logger.error(error_msg)
                return None
            
            logger.debug(f"Comando '{command}' executado com sucesso")

        # Aguarda estabilização final
        time.sleep(2)
        
        success_msg = f"ONU {onu_id} provisionada com sucesso na PON {pon} com VLAN {vlan}"
        logger.info(success_msg)
        print(f"{success_msg}")
        
        return success_msg

    except pexpect.exceptions.ExceptionPexpect as e:
        error_msg = f"Erro de comunicação SSH ao adicionar ONU {onu_id}: {e}"
        logger.error(error_msg)
        print(f"{error_msg}")
    except Exception as e:
        error_msg = f"Erro inesperado ao adicionar ONU {onu_id}: {e}"
        logger.error(error_msg)
        print(f"{error_msg}")
    finally:
        # Cleanup da sessão SSH
        if child and child.isalive():
            try:
                child.sendline("exit")
                child.close()
                logger.debug("Sessão SSH encerrada com sucesso")
            except:
                logger.warning("Erro ao encerrar sessão SSH graciosamente")
    
    return None

def set_onu_service(host: str, pon: str, onu_id: int, vlan: int) -> Optional[str]:
    """Configura o serviço de uma ONU na OLT Datacom"""
    child = None
    try:
        # Validação de parâmetros
        if not all([host, pon]) or onu_id is None or vlan is None:
            error_msg = "Parâmetros obrigatórios não fornecidos"
            logger.error(error_msg)
            return None

        if not (0 <= onu_id <= 127):
            error_msg = f"ONU ID {onu_id} fora do range válido (0-127)"
            logger.error(error_msg)
            return None

        child = login_olt_ssh_datacom(host)
        if not child:
            return None

        logger.info(f"Configurando serviço para ONU {onu_id} na PON {pon} com VLAN {vlan}")

        # Comandos de configuração
        commands = [
            ("service-port new", "Iniciando configuração de serviço"),
            (f"gpon 1/1/{pon} onu {onu_id} gem 1 match vlan vlan-id {vlan} action vlan replace vlan-id {vlan}", f"Configurando VLAN {vlan} para ONU {onu_id} na PON {pon}")
        ]

        for command, description in commands:
            logger.debug(f"Executando: {command} - {description}")
            child.sendline(command)
            
            index = child.expect([
                r".*#\s*$",
                r".*\(config.*\)#\s*$", 
                pexpect.TIMEOUT,
                "Error",
                "Invalid"
            ], timeout=EXTENDED_TIMEOUT)
            
            if index in [2, 3, 4]:  
                error_msg = f"Erro ao executar comando '{command}': {child.before if hasattr(child, 'before') else 'Timeout'}"
                logger.error(error_msg)
                return None
            
            logger.debug(f"Comando '{command}' executado com sucesso")

        time.sleep(2)

        success_msg = f"Serviço configurado com sucesso para ONU {onu_id} na PON {pon} com VLAN {vlan}"
        logger.info(success_msg)
        print(f"{success_msg}")
        
        return success_msg

    except pexpect.exceptions.ExceptionPexpect as e:
        error_msg = f"Erro de comunicação SSH ao configurar serviço ONU {onu_id}: {e}"
        logger.error(error_msg)
        print(f"{error_msg}")
    except Exception as e:
        error_msg = f"Erro inesperado ao configurar serviço ONU {onu_id}: {e}"
        logger.error(error_msg)
        print(f"{error_msg}")
    finally:
        # Cleanup da sessão SSH
        if child and child.isalive():
            try:
                child.sendline("exit")
                child.close()
                logger.debug("Sessão SSH encerrada com sucesso")
            except:
                logger.warning("Erro ao encerrar sessão SSH graciosamente")
    
    return None

def list_pon(host: str, pon: str) -> Optional[list]:
    """Lista ONUs na PON especificada da OLT Datacom"""
    child = None
    try:
        child = login_olt_ssh_datacom(host)
        if not child:
            return None

        logger.info(f"Listando ONUs na PON {pon}")
        child.sendline(f"show interface gpon 1/1/{pon} onu")
        child.expect("#", timeout=EXTENDED_TIMEOUT)

        output = child.before
        logger.info(f"Saída do comando: {output}")

        onus_data = []
        lines = output.split('\n')
        
        for line in lines:
            line = line.strip()
            if (not line or 
                line.startswith('Itf') or 
                line.startswith('---') or 
                'ONU ID' in line or
                line.startswith('show interface gpon') or  
                'interface' in line.lower() and 'gpon' in line.lower()):  
                continue
            
            fields = line.split()
            if len(fields) >= 5:
                try:
                    interface = fields[0]
                    if not ('/' in interface and len(interface.split('/')) >= 3):
                        continue
                    
                    pon_number = interface.split('/')[-1]  
                    onu_id = fields[1]  
                    serial_number = fields[2]  
                    oper_state = fields[3]  
                    
                    if not onu_id.isdigit():
                        continue
                    
                    name = ' '.join(fields[5:]) if len(fields) > 5 else fields[4] if len(fields) > 4 else "N/A"
                    
                    status_color = "green" if oper_state.lower() == "up" else "red"
                    
                    onu_info = {
                        "pon": pon_number,
                        "posicao": onu_id,
                        "serial": serial_number,
                        "status": oper_state,
                        "status_color": status_color,
                        "name": name
                    }
                    
                    onus_data.append(onu_info)
                    logger.debug(f"ONU encontrada: PON {pon_number}, Posição {onu_id}, Status {oper_state}")
                    
                except (IndexError, ValueError) as e:
                    logger.warning(f"Erro ao processar linha: {line} - {e}")
                    continue

        logger.info(f"Total de ONUs encontradas na PON {pon}: {len(onus_data)}")
        
        if onus_data:
            _display_onu_table(onus_data, pon)
        else:
            print(f"📭 Nenhuma ONU encontrada na PON {pon}")
        
        return onus_data

    except pexpect.exceptions.ExceptionPexpect as e:
        error_msg = f"Erro de comunicação SSH ao listar PON {pon}: {e}"
        logger.error(error_msg)
        print(error_msg)
    except Exception as e:
        error_msg = f"Erro inesperado ao listar PON {pon}: {e}"
        logger.error(error_msg)
        print(error_msg)
    finally:
        if child and child.isalive():
            try:
                child.sendline("exit")
                child.close()
                logger.debug("Sessão SSH encerrada com sucesso")
            except:
                logger.warning("Erro ao encerrar sessão SSH graciosamente")

    return None

def _display_onu_table(onus_data: list, pon: str):
    """Exibe tabela de ONUs usando Textual"""
    
    class OnuTableApp(App):
        
        CSS = """
        #title {
            text-align: center;
            margin: 1;
            color: cyan;
        }
        
        #onu_table {
            margin: 1;
        }
        """
        
        def compose(self) -> ComposeResult:
            yield Static(f"ONUs da PON {pon}", id="title")
            yield DataTable(id="onu_table")
        
        def on_mount(self) -> None:
            table = self.query_one("#onu_table", DataTable)
            
            table.add_column("PON", width=8)
            table.add_column("Posição", width=12)
            table.add_column("Serial", width=18)
            table.add_column("Status", width=12)
            table.add_column("Nome", width=35)
            
            for onu in onus_data:
                status_text = Text(str(onu["status"]))
                if onu["status_color"] == "green":
                    status_text.stylize("bold green")
                else:
                    status_text.stylize("bold red")
                
                table.add_row(
                    str(onu["pon"]),
                    str(onu["posicao"]),
                    str(onu["serial"]),
                    status_text,
                    str(onu["name"])[:30]  
                )
            
            table.focus()
    
    app = OnuTableApp()
    try:
        app.run()
    except KeyboardInterrupt:
        print("\nTabela fechada pelo usuário")
    except Exception as e:
        logger.error(f"Erro ao exibir tabela Textual: {e}")
        print(f"\nErro ao exibir tabela: {e}")

