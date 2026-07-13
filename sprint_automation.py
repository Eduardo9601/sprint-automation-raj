"""
Automação de Sprint Semanal - Jira Cloud
Projeto: RAJ | Board: configurável via env

Executa:
1. Busca sprints existentes para calcular próximo número
2. Cria nova sprint com nomenclatura padrão
3. Move issues pendentes da sprint vencida para a nova
4. Fecha a sprint vencida (somente APÓS mover issues)
"""

import os
import sys
import requests
from datetime import datetime, timedelta

# ============ CONFIGURAÇÃO ============
JIRA_DOMAIN = os.environ.get("JIRA_DOMAIN", "")
JIRA_EMAIL = os.environ.get("JIRA_EMAIL", "")
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN", "")
BOARD_ID = os.environ.get("BOARD_ID", "")
DURACAO_SPRINT_DIAS = int(os.environ.get("DURACAO_SPRINT_DIAS", "7"))

BASE_URL = f"https://{JIRA_DOMAIN}/rest/agile/1.0"
AUTH = (JIRA_EMAIL, JIRA_API_TOKEN)
HEADERS = {"Content-Type": "application/json", "Accept": "application/json"}


def validar_configuracao():
    """Valida se todas as variáveis de ambiente estão configuradas."""
    erros = []
    if not JIRA_DOMAIN:
        erros.append("JIRA_DOMAIN não configurado")
    if not JIRA_EMAIL:
        erros.append("JIRA_EMAIL não configurado")
    if not JIRA_API_TOKEN:
        erros.append("JIRA_API_TOKEN não configurado")
    if not BOARD_ID:
        erros.append("BOARD_ID não configurado")

    if erros:
        print("❌ Erros de configuração:")
        for erro in erros:
            print(f"   - {erro}")
        sys.exit(1)


def buscar_sprints(board_id, states="active,future,closed"):
    """Busca sprints do board por estado."""
    todas_sprints = []
    start_at = 0
    max_results = 50

    while True:
        url = f"{BASE_URL}/board/{board_id}/sprint"
        params = {"state": states, "startAt": start_at, "maxResults": max_results}
        response = requests.get(url, auth=AUTH, headers=HEADERS, params=params)
        response.raise_for_status()

        data = response.json()
        sprints = data.get("values", [])
        todas_sprints.extend(sprints)

        if data.get("isLast", True):
            break
        start_at += max_results

    return todas_sprints


def extrair_maior_numero(sprints):
    """Extrai o maior número sequencial das sprints existentes."""
    import re
    maior = 0
    for sprint in sprints:
        match = re.search(r"Sprint\s+(\d+)", sprint.get("name", ""))
        if match:
            num = int(match.group(1))
            if num > maior:
                maior = num
    return maior


def criar_sprint(board_id, nome, data_inicio, data_fim):
    """Cria uma nova sprint no board."""
    url = f"{BASE_URL}/sprint"
    payload = {
        "name": nome,
        "startDate": data_inicio.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "endDate": data_fim.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "originBoardId": int(board_id),
        "goal": "Sprint criada automaticamente via GitHub Actions"
    }
    response = requests.post(url, auth=AUTH, headers=HEADERS, json=payload)
    response.raise_for_status()
    return response.json()


def buscar_issues_pendentes(sprint_id):
    """Busca issues não concluídas de uma sprint."""
    url = f"{BASE_URL}/sprint/{sprint_id}/issue"
    params = {"maxResults": 200, "fields": "status"}
    response = requests.get(url, auth=AUTH, headers=HEADERS, params=params)
    response.raise_for_status()

    data = response.json()
    issues = data.get("issues", [])

    # Filtra apenas issues que NÃO estão na categoria "done"
    pendentes = [
        issue["key"] for issue in issues
        if issue["fields"]["status"]["statusCategory"]["key"] != "done"
    ]
    return pendentes


def mover_issues_para_sprint(sprint_destino_id, issue_keys):
    """Move uma lista de issues para a sprint de destino."""
    if not issue_keys:
        print("   Nenhuma issue para mover.")
        return True

    url = f"{BASE_URL}/sprint/{sprint_destino_id}/issue"
    payload = {"issues": issue_keys}
    response = requests.post(url, auth=AUTH, headers=HEADERS, json=payload)

    if response.status_code in [200, 204]:
        print(f"   ✅ {len(issue_keys)} issues movidas com sucesso!")
        return True
    else:
        print(f"   ❌ Erro ao mover issues: {response.status_code} - {response.text}")
        return False


def fechar_sprint(sprint_id):
    """Fecha (completa) uma sprint."""
    url = f"{BASE_URL}/sprint/{sprint_id}"
    payload = {
        "state": "closed"
    }
    response = requests.put(url, auth=AUTH, headers=HEADERS, json=payload)
    response.raise_for_status()
    print(f"   ✅ Sprint fechada com sucesso!")
    return True


def ativar_sprint(sprint_id):
    """Ativa uma sprint que está em estado 'future'."""
    url = f"{BASE_URL}/sprint/{sprint_id}"
    payload = {
        "state": "active"
    }
    response = requests.put(url, auth=AUTH, headers=HEADERS, json=payload)
    if response.status_code == 200:
        print(f"   ✅ Sprint ativada com sucesso!")
        return True
    else:
        print(f"   ⚠️ Não foi possível ativar a sprint: {response.status_code} - {response.text}")
        return False


def main():
    print("🚀 AUTOMAÇÃO DE SPRINT SEMANAL - RAJ")
    print("=" * 50)
    print()

    # Validar configuração
    validar_configuracao()

    # Data atual
    agora = datetime.now()
    print(f"📅 Data atual: {agora.strftime('%d/%m/%Y %H:%M')}")
    print()

    # 1. Buscar todas as sprints
    print("📋 Buscando sprints existentes...")
    todas_sprints = buscar_sprints(BOARD_ID)
    print(f"   Total de sprints encontradas: {len(todas_sprints)}")
    print()

    # 2. Calcular próximo número
    maior_numero = extrair_maior_numero(todas_sprints)
    proximo_numero = maior_numero + 1
    mes_atual = agora.strftime("%m")
    ano_atual = agora.strftime("%Y")
    nome_nova_sprint = f"Sprint {proximo_numero} - {mes_atual}/{ano_atual}"

    # Datas da nova sprint
    data_inicio = agora
    data_fim = agora + timedelta(days=DURACAO_SPRINT_DIAS)

    print(f"🔵 Nova sprint: {nome_nova_sprint}")
    print(f"   Início: {data_inicio.strftime('%Y-%m-%d')} | Fim: {data_fim.strftime('%Y-%m-%d')}")
    print()

    # 3. Verificar sprints ativas vencidas ANTES de criar a nova
    print("🔍 Verificando sprints ativas vencidas...")
    sprints_ativas = [s for s in todas_sprints if s.get("state") == "active"]

    sprint_vencida = None
    issues_pendentes = []

    for sprint in sprints_ativas:
        end_date_str = sprint.get("endDate", "")
        if end_date_str:
            # Parse da data (formato ISO)
            end_date = datetime.fromisoformat(end_date_str.replace("Z", "+00:00")).replace(tzinfo=None)
            if end_date <= agora:
                sprint_vencida = sprint
                print(f"   ⚠️ Sprint vencida: {sprint['name']} (ID: {sprint['id']})")
                print(f"      Venceu em: {end_date.strftime('%d/%m/%Y')}")

                # Buscar issues pendentes
                issues_pendentes = buscar_issues_pendentes(sprint["id"])
                print(f"      Issues pendentes: {len(issues_pendentes)}")
                break
    
    if not sprint_vencida:
        print("   Nenhuma sprint vencida encontrada.")
    print()

    # 4. Criar a nova sprint
    print("🆕 Criando nova sprint...")
    try:
        nova_sprint = criar_sprint(BOARD_ID, nome_nova_sprint, data_inicio, data_fim)
        nova_sprint_id = nova_sprint["id"]
        print(f"   ✅ Sprint criada: {nome_nova_sprint} (ID: {nova_sprint_id})")
    except requests.exceptions.HTTPError as e:
        print(f"   ❌ Erro ao criar sprint: {e}")
        print(f"      Response: {e.response.text if e.response else 'N/A'}")
        sys.exit(1)
    print()

    # 5. Se há sprint vencida, PRIMEIRO mover issues, DEPOIS fechar
    if sprint_vencida:
        # PASSO A: Mover issues pendentes para a nova sprint
        if issues_pendentes:
            print(f"📦 Movendo {len(issues_pendentes)} issues para {nome_nova_sprint}...")
            print(f"   Issues: {', '.join(issues_pendentes)}")
            move_ok = mover_issues_para_sprint(nova_sprint_id, issues_pendentes)

            if not move_ok:
                print("   ❌ Falha ao mover issues. Abortando fechamento da sprint antiga.")
                print("   ⚠️ A nova sprint foi criada, mas a antiga permanece aberta.")
                sys.exit(1)
        else:
            print("📦 Nenhuma issue pendente para mover.")
            move_ok = True
        print()

        # PASSO B: SOMENTE AGORA fechar a sprint vencida (já sem issues pendentes)
        print(f"🔒 Fechando sprint: {sprint_vencida['name']}...")
        try:
            fechar_sprint(sprint_vencida["id"])
        except requests.exceptions.HTTPError as e:
            print(f"   ❌ Erro ao fechar sprint: {e}")
            print(f"      Response: {e.response.text if e.response else 'N/A'}")
            print("   ⚠️ A nova sprint foi criada e as issues movidas, mas a sprint antiga não foi fechada.")
            sys.exit(1)
        print()

        # PASSO C: Ativar a nova sprint (já que a anterior foi fechada)
        print(f"▶️ Ativando sprint: {nome_nova_sprint}...")
        ativar_sprint(nova_sprint_id)
        print()

    # Resumo final
    print("=" * 50)
    print("✅ AUTOMAÇÃO CONCLUÍDA COM SUCESSO!")
    print(f"   📌 Nova sprint: {nome_nova_sprint}")
    if sprint_vencida:
        print(f"   📦 Issues movidas: {len(issues_pendentes)}")
        print(f"   🔒 Sprint fechada: {sprint_vencida['name']}")
    print("=" * 50)


if __name__ == "__main__":
    main()
