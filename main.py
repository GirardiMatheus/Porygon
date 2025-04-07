from parks.parks_ssh import *

conexao = login_ssh()
serial = "prKs00d28ACC"  # Substitua pelo serial desejado

# Consulta a ONU
dados_onu = consult_information(conexao, serial)

if dados_onu:
    print("\nInformações da ONU:")
    print(f"Serial: {dados_onu['serial']}")
    print(f"Modelo: {dados_onu['model']}")
    print(f"Power Level: {dados_onu['power_level']}")
    print(f"Distância: {dados_onu['distance_km']} km")
    print(f"Status: {dados_onu['status']}")
else:
    print("Falha ao consultar ONU.")