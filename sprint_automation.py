"""
Sprint Automation - Grazziotin SA
Board: RAJ (ID: 89)
Executa semanalmente via GitHub Actions
Cria nova sprint, move issues pendentes e fecha a anterior.
REGRA: Apenas UMA sprint criada por execução.
"""

import os
import sys
import requests
from datetime import datetime, timedelta, timezone

# ========== CONFIGURAÇÃO ==========
JIRA_DOMAIN = os.environ.get("JIRA_DOMAIN", "")
JIRA_EMAIL = os.environ.get("JIRA_EMAIL", "")
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN", "")
BOARD_ID = os.environ.get("BOARD_ID", "89")

BASE_URL = f"https://{JIRA_DOMAIN}/rest/agile/1.0"
AUTH = (JIRA_EMAIL, JIRA_API_TOKEN)
HEADERS = {"Content-Type": "application/json", "Accept": "application/json"}

DURACAO_SPRINT_DIAS = 7
FUSO_HORARIO = timezone(timedelta(hours=-3))  # America/Sao_Paulo


def log(msg):
    print(msg)


def validar_config():
    """Valida se todas as variáveis de ambiente estão configuradas."""
    erros = []
    if not JIRA_DOMAIN:
        erros.append("JIRA_DOMAIN")
    if not JIRA_EMAIL:
        erros.append("JIRA_EMAIL")
    if not JIRA_API_TOKEN:
        erros.append("JIRA_API_TOKEN")
    if not BOARD_ID:
        erros.append("BOARD_ID")

    if erros:
        log(f"❌ Variáveis de ambiente faltando: {', '.join(erros)}")
        sys.exit(1)

    log(f"✅ Configuração OK — Board: {BOARD_ID} | Domain: {JIRA_DOMAIN}")


def get_sprints(state):
    """Busca sprints do board por estado."""
    url = f"{BASE_URL}/board/{BOARD_ID}/sprint"
    params = {"state": state, "maxResults": 50}
    resp = requests.get(url, auth=AUTH, headers=HEADERS, params=params)

    if resp.status_code == 200:
        return resp.json().get("values", [])
    else:
        log(f"⚠️ Erro ao buscar sprints ({state}): {resp.status_code}")
        return []


def get_issues_pendentes(sprint_id):
    """Busca issues não concluídas de uma sprint."""
    url = f"{BASE_URL}/sprint/{sprint_id}/issue"
    params = {"maxResults": 200, "fields": "status"}
    resp = requests.get(url, auth=AUTH, headers=HEADERS, params=params)

    if resp.status_code != 200:
        log(f"⚠️ Erro ao buscar issues da sprint {sprint_id}: {resp.status_code}")
        return []

    issues = resp.json().get("issues", [])
    pendentes = []
    for issue in issues:
        categoria = issue["fields"]["status"]["statusCategory"]["key"]
        if categoria != "done":
            pendentes.append(issue["key"])

    return pendentes


def extrair_maior_numero(sprints):
    """Extrai o maior número sequencial das sprints."""
    import re
    maior = 0
    for sprint in sprints:
        match = re.search(r"Sprint\s+(\d+)", sprint.get("name", ""))
        if match:
            num = int(match.group(1))
            if num > maior:
                maior = num
    return maior


def criar_sprint(nome):
    """Cria uma nova sprint no board (estado future)."""
    url = f"{BASE_URL}/sprint"
    payload = {
        "name": nome,
        "originBoardId": int(BOARD_ID),
        "goal": "Sprint criada automaticamente"
    }
    resp = requests.post(url, auth=AUTH, headers=HEADERS, json=payload)

    if resp.status_code == 201:
        sprint_id = resp.json()["id"]
        log(f"✅ Sprint criada! Nome: {nome} | ID: {sprint_id}")
        return sprint_id
    else:
        log(f"❌ Erro ao criar sprint: {resp.status_code}")
        log(f"   Resposta: {resp.text}")
        sys.exit(1)


def mover_issues(sprint_id_destino, issue_keys):
    """Move issues para a sprint de destino."""
    if not issue_keys:
        log("   Nenhuma issue para mover.")
        return True

    url = f"{BASE_URL}/sprint/{sprint_id_destino}/issue"
    payload = {"issues": issue_keys}
    resp = requests.post(url, auth=AUTH, headers=HEADERS, json=payload)

    if resp.status_code in [200, 204]:
        log(f"✅ {len(issue_keys)} issues movidas para sprint {sprint_id_destino}")
        return True
    else:
        log(f"❌ Erro ao mover issues: {resp.status_code}")
        log(f"   Resposta: {resp.text}")
        return False


def fechar_sprint(sprint_id, sprint_name):
    """Fecha uma sprint."""
    url = f"{BASE_URL}/sprint/{sprint_id}"
    payload = {
        "name": sprint_name,
        "state": "closed"
    }
    resp = requests.put(url, auth=AUTH, headers=HEADERS, json=payload)

    if resp.status_code == 200:
        log(f"✅ Sprint fechada: {sprint_name}")
        return True
    else:
        log(f"❌ Erro ao fechar sprint: {resp.status_code}")
        log(f"   Resposta: {resp.text}")
        return False


def ativar_sprint(sprint_id, sprint_name, data_inicio, data_fim):
    """Ativa uma sprint com datas."""
    url = f"{BASE_URL}/sprint/{sprint_id}"
    payload = {
        "name": sprint_name,
        "state": "active",
        "startDate": data_inicio,
        "endDate": data_fim
    }
    resp = requests.put(url, auth=AUTH, headers=HEADERS, json=payload)

    if resp.status_code == 200:
        log(f"✅ Sprint ativada: {sprint_name}")
        return True
    else:
        log(f"❌ Erro ao ativar sprint: {resp.status_code}")
        log(f"   Resposta: {resp.text}")
        return False


def main():
    log("=" * 50)
    log("🚀 AUTOMAÇÃO DE SPRINT SEMANAL - GRAZZIOTIN")
    log("=" * 50)

    validar_config()

    # Data atual no fuso de São Paulo
    agora = datetime.now(FUSO_HORARIO)
    hoje_str = agora.strftime("%Y-%m-%d")
    log(f"📅 Data atual: {agora.strftime('%d/%m/%Y %H:%M')} (America/Sao_Paulo)")

    # Buscar sprints
    sprints_ativas = get_sprints("active")
    sprints_fechadas = get_sprints("closed")
    sprints_futuras = get_sprints("future")

    todas_sprints = sprints_ativas + sprints_fechadas + sprints_futuras

    # Calcular próximo número
    maior_numero = extrair_maior_numero(todas_sprints)
    proximo_numero = maior_numero + 1
    mes_atual = agora.strftime("%m")
    ano_atual = agora.strftime("%Y")
    nome_nova_sprint = f"Sprint {proximo_numero} - {mes_atual}/{ano_atual}"

    log(f"📊 Maior número encontrado: {maior_numero}")
    log(f"📝 Próxima sprint: {nome_nova_sprint}")

    # Datas da nova sprint
    data_inicio = agora.strftime("%Y-%m-%dT%H:%M:%S.000-03:00")
    data_fim_dt = agora + timedelta(days=DURACAO_SPRINT_DIAS)
    data_fim = data_fim_dt.strftime("%Y-%m-%dT%H:%M:%S.000-03:00")

    # ========== CENÁRIO 1: Existe sprint ativa vencida ==========
    if sprints_ativas:
        sprint_ativa = sprints_ativas[0]
        end_date_str = sprint_ativa.get("endDate", "")

        if end_date_str:
            # Pega só a parte da data (YYYY-MM-DD)
            end_date = datetime.strptime(end_date_str[:10], "%Y-%m-%d").date()
            hoje_date = agora.date()

            log(f"\n🔍 Sprint ativa: {sprint_ativa['name']} (ID: {sprint_ativa['id']})")
            log(f"   Vence em: {end_date.strftime('%d/%m/%Y')}")
            log(f"   Hoje: {hoje_date.strftime('%d/%m/%Y')}")

            if end_date <= hoje_date:
                log(f"\n⚠️ Sprint vencida! Iniciando rotação...")

                # 1. Buscar issues pendentes
                issues_pendentes = get_issues_pendentes(sprint_ativa["id"])
                log(f"   Issues pendentes: {len(issues_pendentes)}")

                # 2. Criar nova sprint
                nova_sprint_id = criar_sprint(nome_nova_sprint)

                # 3. Mover issues
                if issues_pendentes:
                    mover_issues(nova_sprint_id, issues_pendentes)

                # 4. Fechar sprint antiga
                fechar_sprint(sprint_ativa["id"], sprint_ativa["name"])

                # 5. Ativar nova sprint
                ativar_sprint(nova_sprint_id, nome_nova_sprint, data_inicio, data_fim)

                log(f"\n🎉 AUTOMAÇÃO CONCLUÍDA COM SUCESSO!")
                log(f"   Sprint fechada: {sprint_ativa['name']}")
                log(f"   Sprint ativa: {nome_nova_sprint}")
            else:
                dias_restantes = (end_date - hoje_date).days
                log(f"\n✅ Sprint ainda vigente. Faltam {dias_restantes} dia(s).")
                log("   Nenhuma ação necessária.")

        return

    # ========== CENÁRIO 2: Não existe sprint ativa ==========
    log("\n⚠️ Nenhuma sprint ativa encontrada. Criando nova...")

    nova_sprint_id = criar_sprint(nome_nova_sprint)
    ativar_sprint(nova_sprint_id, nome_nova_sprint, data_inicio, data_fim)

    log(f"\n🎉 AUTOMAÇÃO CONCLUÍDA COM SUCESSO!")
    log(f"   Sprint ativa: {nome_nova_sprint}")


if __name__ == "__main__":
    main()
