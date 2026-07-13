"""
Automação de Sprint Semanal - Projeto RAJ
Cria nova sprint, move issues pendentes e fecha sprint vencida.
Executado via GitHub Actions toda segunda-feira.
"""

import os
import sys
import requests
from datetime import datetime, timedelta
import re

# ========== CONFIGURAÇÕES ==========
JIRA_DOMAIN = os.environ.get("JIRA_DOMAIN")
JIRA_EMAIL = os.environ.get("JIRA_EMAIL")
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN")
BOARD_ID = os.environ.get("BOARD_ID")
DURACAO_SPRINT_DIAS = int(os.environ.get("DURACAO_SPRINT_DIAS", "7"))

# Validação
if not all([JIRA_DOMAIN, JIRA_EMAIL, JIRA_API_TOKEN, BOARD_ID]):
    print("❌ Erro: Variáveis de ambiente não configuradas!")
    print(f"   JIRA_DOMAIN: {'✅' if JIRA_DOMAIN else '❌ FALTANDO'}")
    print(f"   JIRA_EMAIL: {'✅' if JIRA_EMAIL else '❌ FALTANDO'}")
    print(f"   JIRA_API_TOKEN: {'✅' if JIRA_API_TOKEN else '❌ FALTANDO'}")
    print(f"   BOARD_ID: {'✅' if BOARD_ID else '❌ FALTANDO'}")
    sys.exit(1)

BASE_URL = f"https://{JIRA_DOMAIN}/rest/agile/1.0"
AUTH = (JIRA_EMAIL, JIRA_API_TOKEN)
HEADERS = {"Content-Type": "application/json", "Accept": "application/json"}


def log(emoji, msg, indent=0):
    prefix = "   " * indent
    print(f"{prefix}{emoji} {msg}")


def get_sprints(board_id, state):
    """Busca sprints do board por estado."""
    sprints = []
    start_at = 0
    while True:
        url = f"{BASE_URL}/board/{board_id}/sprint?state={state}&startAt={start_at}&maxResults=50"
        resp = requests.get(url, auth=AUTH, headers=HEADERS)
        if resp.status_code != 200:
            log("❌", f"Erro ao buscar sprints ({state}): {resp.status_code}")
            break
        data = resp.json()
        sprints.extend(data.get("values", []))
        if data.get("isLast", True):
            break
        start_at += 50
    return sprints


def get_issues_pendentes(sprint_id):
    """Busca issues não concluídas de uma sprint."""
    issues = []
    start_at = 0
    while True:
        url = f"{BASE_URL}/sprint/{sprint_id}/issue?startAt={start_at}&maxResults=100&fields=status,key"
        resp = requests.get(url, auth=AUTH, headers=HEADERS)
        if resp.status_code != 200:
            log("❌", f"Erro ao buscar issues da sprint {sprint_id}: {resp.status_code}", 1)
            break
        data = resp.json()
        for issue in data.get("issues", []):
            status_category = issue["fields"]["status"]["statusCategory"]["key"]
            if status_category != "done":
                issues.append(issue["key"])
        if start_at + 100 >= data.get("total", 0):
            break
        start_at += 100
    return issues


def criar_sprint(nome, inicio, fim, board_id):
    """Cria uma nova sprint."""
    url = f"{BASE_URL}/sprint"
    body = {
        "name": nome,
        "startDate": inicio,
        "endDate": fim,
        "originBoardId": int(board_id),
        "goal": "Sprint criada automaticamente via GitHub Actions"
    }
    resp = requests.post(url, auth=AUTH, headers=HEADERS, json=body)
    if resp.status_code == 201:
        return resp.json()
    else:
        log("❌", f"Erro ao criar sprint: {resp.status_code} - {resp.text}")
        return None


def mover_issues(sprint_id, issue_keys):
    """Move issues para uma sprint."""
    url = f"{BASE_URL}/sprint/{sprint_id}/issue"
    body = {"issues": issue_keys}
    resp = requests.post(url, auth=AUTH, headers=HEADERS, json=body)
    if resp.status_code in [200, 204]:
        return True
    else:
        log("❌", f"Erro ao mover issues: {resp.status_code} - {resp.text}", 1)
        return False


def fechar_sprint(sprint_id, nova_sprint_id):
    """Fecha uma sprint, movendo issues restantes para a nova sprint."""
    url = f"{BASE_URL}/sprint/{sprint_id}"
    
    # Formato ISO 8601 completo com timezone
    now = datetime.now()
    complete_date = now.strftime("%Y-%m-%dT%H:%M:%S.000-0300")
    
    body = {
        "state": "closed",
        "completeDate": complete_date,
        "moveUnfixedIssuesTo": nova_sprint_id
    }
    resp = requests.put(url, auth=AUTH, headers=HEADERS, json=body)
    if resp.status_code == 200:
        return True
    else:
        log("❌", f"Erro ao fechar sprint: {resp.status_code} - {resp.text}", 1)
        return False


def ativar_sprint(sprint_id, nome, inicio, fim):
    """Ativa uma sprint (muda estado para active)."""
    url = f"{BASE_URL}/sprint/{sprint_id}"
    body = {
        "state": "active",
        "name": nome,
        "startDate": inicio,
        "endDate": fim
    }
    resp = requests.put(url, auth=AUTH, headers=HEADERS, json=body)
    if resp.status_code == 200:
        return True
    else:
        log("❌", f"Erro ao ativar sprint: {resp.status_code} - {resp.text}", 1)
        return False


# ========== EXECUÇÃO PRINCIPAL ==========
def main():
    print("\n🚀 AUTOMAÇÃO DE SPRINT SEMANAL - RAJ")
    print("=" * 50)
    
    agora = datetime.now()
    log("📅", f"Data atual: {agora.strftime('%d/%m/%Y %H:%M')}")
    print()
    
    # 1. Buscar todas as sprints para encontrar o maior número
    log("📋", "Buscando sprints existentes...")
    todas_sprints = []
    for state in ["active", "future", "closed"]:
        todas_sprints.extend(get_sprints(BOARD_ID, state))
    
    log("", f"Total de sprints encontradas: {len(todas_sprints)}", 1)
    print()
    
    # 2. Encontrar o maior número de sprint
    maior_numero = 0
    for sprint in todas_sprints:
        match = re.search(r"Sprint\s+(\d+)", sprint.get("name", ""))
        if match:
            num = int(match.group(1))
            if num > maior_numero:
                maior_numero = num
    
    # 3. Calcular próximo número e mês
    proximo_numero = maior_numero + 1
    mes_atual = agora.strftime("%m")
    ano_atual = agora.strftime("%Y")
    
    nome_nova_sprint = f"Sprint {proximo_numero} - {mes_atual}/{ano_atual}"
    data_inicio = agora.strftime("%Y-%m-%d")
    data_fim = (agora + timedelta(days=DURACAO_SPRINT_DIAS)).strftime("%Y-%m-%d")
    
    log("🔵", f"Nova sprint: {nome_nova_sprint}")
    log("", f"Início: {data_inicio} | Fim: {data_fim}", 1)
    print()
    
    # 4. Verificar sprints ativas vencidas
    log("🔍", "Verificando sprints ativas vencidas...")
    sprints_ativas = get_sprints(BOARD_ID, "active")
    
    sprint_vencida = None
    issues_pendentes = []
    
    for sprint in sprints_ativas:
        end_date_str = sprint.get("endDate", "")
        if end_date_str:
            end_date = datetime.strptime(end_date_str[:10], "%Y-%m-%d")
            if end_date <= agora:
                sprint_vencida = sprint
                log("⚠️", f"Sprint vencida: {sprint['name']} (ID: {sprint['id']})", 1)
                log("", f"Venceu em: {end_date.strftime('%d/%m/%Y')}", 2)
                
                # Buscar issues pendentes
                issues_pendentes = get_issues_pendentes(sprint["id"])
                log("", f"Issues pendentes: {len(issues_pendentes)}", 2)
                break
    
    if not sprint_vencida:
        log("✅", "Nenhuma sprint vencida encontrada", 1)
    
    print()
    
    # 5. Criar a nova sprint
    log("📋", "Criando nova sprint...")
    nova_sprint = criar_sprint(nome_nova_sprint, data_inicio, data_fim, BOARD_ID)
    
    if not nova_sprint:
        log("❌", "FALHA: Não foi possível criar a sprint. Abortando.")
        sys.exit(1)
    
    nova_sprint_id = nova_sprint["id"]
    log("✅", f"Sprint criada: {nome_nova_sprint} (ID: {nova_sprint_id})", 1)
    print()
    
    # 6. Mover issues pendentes para a nova sprint
    if issues_pendentes:
        log("🔀", f"Movendo {len(issues_pendentes)} issues para {nome_nova_sprint}...")
        log("", f"Issues: {', '.join(issues_pendentes)}", 1)
        
        if mover_issues(nova_sprint_id, issues_pendentes):
            log("✅", f"{len(issues_pendentes)} issues movidas com sucesso!", 1)
        else:
            log("⚠️", "Problemas ao mover algumas issues", 1)
        print()
    
    # 7. Fechar a sprint vencida (DEPOIS de mover as issues)
    if sprint_vencida:
        log("🔒", f"Fechando sprint: {sprint_vencida['name']}...")
        
        if fechar_sprint(sprint_vencida["id"], nova_sprint_id):
            log("✅", f"Sprint {sprint_vencida['name']} fechada com sucesso!", 1)
        else:
            log("⚠️", "Não foi possível fechar a sprint antiga.", 1)
            log("", "A nova sprint foi criada e as issues movidas.", 2)
            log("", "Feche a sprint anterior manualmente se necessário.", 2)
        print()
    
    # 8. Ativar a nova sprint
    log("▶️", f"Ativando {nome_nova_sprint}...")
    if ativar_sprint(nova_sprint_id, nome_nova_sprint, data_inicio, data_fim):
        log("✅", "Sprint ativada com sucesso!", 1)
    else:
        log("⚠️", "Sprint criada mas não foi possível ativá-la automaticamente.", 1)
        log("", "Ative manualmente no board se necessário.", 2)
    
    print()
    print("=" * 50)
    log("🎉", "Automação concluída com sucesso!")
    log("", f"Sprint ativa: {nome_nova_sprint}", 1)
    if issues_pendentes:
        log("", f"Issues migradas: {len(issues_pendentes)}", 1)


if __name__ == "__main__":
    main()
