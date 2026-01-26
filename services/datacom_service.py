"""
Datacom Service module for OLT management operations.
Provides high-level functions for ONU provisioning, configuration, and monitoring.
"""

import csv
import time
import re
from typing import Optional, List, Dict, Tuple, Any
from datetime import datetime

from datacom.datacom_ssh import *

from utils.log import get_logger

# Logger principal
logger = get_logger(__name__)
logger.info("Sistema iniciado")

def get_user_input(prompt: str, validator=None, required: bool = True) -> str:
    """Get validated user input with proper error handling"""
    while True:
        try:
            value = input(prompt).strip()
            if required and not value:
                raise ValueError("Valor não pode estar vazio")
            if validator and not validator(value):
                raise ValueError("Valor inválido")
            return value
        except ValueError as e:
            logger.error(f"Erro na entrada do usuário: {str(e)}")
            print(f"❌ Erro: {str(e)}")
        except KeyboardInterrupt:
            logger.info("Operação cancelada pelo usuário")
            raise

def list_pon_datacom(ip_olt: str) -> None:
    """List PON status with detailed information"""
    try:
        pon = get_user_input("Digite a PON: ", required=True)
        
        logger.info(f"Listando ONUs da PON {pon} na OLT {ip_olt}")
        result = list_pon(ip_olt, pon)
        
        if result is None:
            print("❌ Erro ao listar ONUs da PON")
        elif len(result) == 0:
            print(f"📭 Nenhuma ONU encontrada na PON {pon}")
        else:
            print(f"✅ Encontradas {len(result)} ONUs na PON {pon}")

    except KeyboardInterrupt:
        logger.info("Operação cancelada pelo usuário")
        print("\n🔚 Operação cancelada pelo usuário")
    except Exception as e:
        logger.error(f"Erro durante o processo de listagem: {str(e)}", exc_info=True)
        print("❌ Erro ao executar o processo de listagem de ONUs.")

def normalize_text(text: str) -> str:
    """Normaliza texto removendo acentos, caracteres especiais e substituindo espaços por _"""
    import unicodedata
    import re
    
    # Remove acentos
    normalized = unicodedata.normalize('NFD', text)
    without_accents = ''.join(char for char in normalized if unicodedata.category(char) != 'Mn')
    
    # Remove caracteres especiais e substitui espaços por _
    clean_text = re.sub(r'[^a-zA-Z0-9\s]', '', without_accents)
    clean_text = re.sub(r'\s+', '_', clean_text.strip())
    
    return clean_text.upper()

def read_datacom_csv(pon: str) -> Optional[int]:
    """Lê o arquivo datacom.csv para obter a VLAN da PON especificada"""
    try:
        csv_path = "csv/datacom.csv"  
        
        with open(csv_path, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                if row.get('PON') == pon:
                    vlan = row.get('VLAN')
                    if vlan and vlan.isdigit():
                        logger.info(f"VLAN {vlan} encontrada para PON {pon}")
                        return int(vlan)
        
        logger.warning(f"VLAN não encontrada para PON {pon} no arquivo CSV")
        return None
        
    except FileNotFoundError:
        logger.error("Arquivo datacom.csv não encontrado")
        print("Arquivo de configuração datacom.csv não encontrado")
        return None
    except Exception as e:
        logger.error(f"Erro ao ler arquivo CSV: {e}")
        print(f"Erro ao ler configurações: {e}")
        return None

def provision_onu_datacom(ip_olt: str) -> None:
    """Provision a new ONU on Datacom OLT"""
    try:
        # Step 1: List unauthorized ONUs
        print("🔍 Listando ONUs não autorizadas...")
        unauthorized_onus = list_unauthorized(ip_olt)
        
        if unauthorized_onus is None:
            print("Erro ao listar ONUs não autorizadas")
            return
        elif len(unauthorized_onus) == 0:
            print("Nenhuma ONU não autorizada encontrada")
            return
        
        # Display unauthorized ONUs
        print(f"\nEncontradas {len(unauthorized_onus)} ONUs não autorizadas:")
        print("="*50)
        print(f"{'#':<3} {'PON':<8} {'Serial Number':<20}")
        print("="*50)
        for i, onu in enumerate(unauthorized_onus, 1):
            # Extract PON from interface (1/1/8 -> 8)
            pon_number = onu['interface'].split('/')[-1]
            print(f"{i:<3} {pon_number:<8} {onu['serial']:<20}")
        print("="*50)
        
        # Step 2: Get serial number from user
        while True:
            serial_number = get_user_input("\nDigite o Serial Number da ONU a ser autorizada: ", required=True)
            serial_number = serial_number.upper()  # Convert to uppercase
            
            # Check if serial exists in unauthorized list
            found_onu = None
            for onu in unauthorized_onus:
                if onu['serial'].upper() == serial_number:
                    found_onu = onu
                    break
            
            if found_onu:
                pon_display = found_onu['interface'].split('/')[-1]
                print(f"ONU encontrada: PON {pon_display} - {found_onu['serial']}")
                break
            else:
                print(f"Serial {serial_number} não encontrado na lista de ONUs não autorizadas")
                continue_choice = input("Deseja tentar novamente? (s/n): ").strip().lower()
                if continue_choice != 's':
                    return
        
        # Step 3: Get customer name and normalize it
        customer_name = get_user_input("Digite o nome do cliente (será normalizado automaticamente): ", required=True)
        normalized_name = normalize_text(customer_name)
        print(f"Nome normalizado: {normalized_name}")
        
        # Step 4: Extract PON from interface
        interface = found_onu['interface']
        pon = interface.split('/')[-1]  # Extract PON number from interface
        print(f"PON identificada: {pon}")

        # Step 5: Read VLAN from CSV
        vlan = read_datacom_csv(pon)
        if vlan is None:
            print("Não foi possível obter a VLAN para esta PON")
            return
        
        print(f"VLAN configurada para PON {pon}: {vlan}")
        
        # Step 6: Find available position
        print(f"Verificando posição livre na PON {pon}...")
        onu_id = check_free_position(ip_olt, pon)
        
        if onu_id is None:
            print("Nenhuma posição livre disponível na PON")
            return
        
        print(f"Posição livre encontrada: {onu_id}")
        
        # Step 7: Provision ONU
        print(f"\nIniciando provisionamento...")
        print(f"   Serial: {serial_number}")
        print(f"   Nome: {normalized_name}")
        print(f"   PON: {pon}")
        print(f"   Posição: {onu_id}")
        print(f"   VLAN: {vlan}")
        
        confirmation = input("\nConfirma o provisionamento? (s/n): ").strip().lower()
        if confirmation != 's':
            print("Provisionamento cancelado pelo usuário")
            return
        
        # Add ONU
        logger.info(f"Provisionando ONU {onu_id} na PON {pon}")
        result = add_onu(ip_olt, pon, onu_id, serial_number, normalized_name, vlan)
        
        if not result:
            print("Erro ao provisionar ONU")
            return
        
        print(result)
        
        # Step 8: Configure service
        print("Configurando serviço da ONU...")
        service_result = set_onu_service(ip_olt, pon, onu_id, vlan)
        
        if service_result:
            print(service_result)
            print("\nProvisionamento completo realizado com sucesso!")
        else:
            print("ONU provisionada, mas houve erro na configuração do serviço")

    except KeyboardInterrupt:
        logger.info("Operação cancelada pelo usuário")
        print("\nOperação cancelada pelo usuário")
    except Exception as e:
        logger.error(f"Erro durante o provisionamento: {str(e)}", exc_info=True)
        print("Erro ao executar o provisionamento da ONU.")

def list_unauthorized_onus_datacom(ip_olt: str) -> None:
    """List unauthorized ONUs"""
    try:
        logger.info("Listando ONUs não autorizadas")
        result = list_unauthorized(ip_olt)
        
        if result is None:
            print("Erro ao listar ONUs não autorizadas")
        elif len(result) == 0:
            print("Nenhuma ONU não autorizada encontrada")
        else:
            print(f"Encontradas {len(result)} ONUs não autorizadas:")
            print("\n" + "="*40)
            print(f"{'PON':<8} {'Serial Number':<20}")
            print("="*40)
            for onu in result:
                # Extract PON from interface (1/1/8 -> 8)
                pon_number = onu['interface'].split('/')[-1]
                print(f"{pon_number:<8} {onu['serial']:<20}")
            print("="*40)

    except Exception as e:
        logger.error(f"Erro ao listar ONUs não autorizadas: {str(e)}", exc_info=True)
        print("Erro ao listar ONUs não autorizadas.")

