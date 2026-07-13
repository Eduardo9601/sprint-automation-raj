"""
Sprint Automation - Grazziotin SA
Automação semanal para criar, ativar e fechar sprints no Jira Cloud.
Sem dependências externas além de 'requests'.
"""

import os
import sys
import requests
from datetime import datetime, timedelta, timezone

# ========== CONFIGURAÇÕES ==========
JIRA_DOMAIN = os.environ.get("JIRA_DOMAIN", "")
JIRA_EMAIL = os.environ.get("JIRA_EMAIL", "")
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN", "")
BOARD_ID = os.environ.get("BOARD_ID", "")

BASE_URL = f"https://{JIRA_DOMAIN}/rest/agile/1.0"
AUTH = (JIRA_EMAIL, JIRA_API_TOKEN)
HEADERS = {"Content-Type": "application/json", "Accept": "application/json"}

FUSO_BRASIL = timezone(timedelta(hours=-3))
DURACAO_SPRINT_DIAS = 7


def validar_configuracao():
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
        print(f"❌ Variáveis de ambiente faltando: {', '.join(erros)}")
        sys.exit(1)
    print(f"✅ Configuração OK: {JIRA_DOMAIN}, Board ID: {BOARD_ID}")


def buscar_todas_sprints(state):
    """Busca TODAS as sprints de um estado, paginando até o fim."""
    todas = []
    start_at = 0
    max_results = 50

    while True:
        url = f"{BASE_URL}/board/{BOARD_ID}/sprint?state={state}&startAt={start_at}&maxResults={max_results}"
        resp = requests.get(url, auth=AUTH, headers=HEADERS)

        if resp.status_code != 200:
            print(f"⚠️ Erro ao buscar sprints ({state}): {resp.status_code}")
            break

        data = resp.json()
        valores = data.get("values", [])
        todas.extend(valores)

        # Verifica se há mais páginas
        if data.get("isLast", True) or len(valores) == 0:
            break

        start_at += max_results

    return todas


def encontrar_maior_numero_sprint():
    """Busca TODAS as sprints do board (todos os estados) e retorna o maior número."""
    import re

    maior = 0

    for state in ["active", "future", "closed"]:
        sprints = buscar_todas_sprints(state)
        for sprint in sprints:
            match = re.search(r"Sprint\s+(\d+)", sprint.get("name", ""))
            if match:
                num = int(match.group(1))
                if num > maior:
                    maior = num

    print(f"📊 Maior número de sprint encontrado: {maior}")
    return maior


def buscar_sprint_ativa():
    """Retorna a sprint ativa do board (se houver)."""
    sprints = buscar_todas_sprints("active")
    if sprints:
        return sprints[0]
    return None


def buscar_issues_pendentes(sprint_id):
    """Busca issues não concluídas de uma sprint."""
    url = f"{BASE_URL}/sprint/{sprint_id}/issue?maxResults=500&fields=status"
    resp = requests.get(url, auth=AUTH, headers=HEADERS)

    if resp.status_code != 200:
        print(f"⚠️ Erro ao buscar issues da sprint {sprint_id}: {resp.status_code}")
        return []

    issues = resp.json().get("issues", [])
    pendentes = []

    for issue in issues:
        status_category = issue["fields"]["status"]["statusCategory"]["key"]
        if status_category != "done":
            pendentes.append(issue["key"])

    return pendentes


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
        print(f"✅ Sprint criada! Nome: {nome}, ID: {sprint_id}")
        return sprint_id
    else:
        print(f"❌ Erro ao criar sprint: {resp.status_code}")
        print(f"   Resposta: {resp.text}")
        sys.exit(1)


def mover_issues(sprint_id, issues):
    """Move issues para uma sprint."""
    if not issues:
        print("   Nenhuma issue para mover.")
        return True

    url = f"{BASE_URL}/sprint/{sprint_id}/issue"
    payload = {"issues": issues}

    resp = requests.post(url, auth=AUTH, headers=HEADERS, json=payload)

    if resp.status_code in [200, 204]:
        print(f"✅ {len(issues)} issues movidas com sucesso")
        return True
    else:
        print(f"❌ Erro ao mover issues: {resp.status_code}")
        print(f"   Resposta: {resp.text}")
        return False


def fechar_sprint(sprint_id, nome):
    """Fecha uma sprint."""
    url = f"{BASE_URL}/sprint/{sprint_id}"
    payload = {
        "name": nome,
        "state": "closed"
    }

    resp = requests.put(url, auth=AUTH, headers=HEADERS, json=payload)

    if resp.status_code == 200:
        print(f"✅ Sprint '{nome}' fechada com sucesso")
        return True
    else:
        print(f"❌ Erro ao fechar sprint: {resp.status_code}")
        print(f"   Resposta: {resp.text}")
        return False


def ativar_sprint(sprint_id, nome, data_inicio, data_fim):
    """Ativa uma sprint com datas."""
    url = f"{BASE_URL}/sprint/{sprint_id}"
    payload = {
        "name": nome,
        "state": "active",
        "startDate": data_inicio,
        "endDate": data_fim
    }

    resp = requests.put(url, auth=AUTH, headers=HEADERS, json=payload)

    if resp.status_code == 200:
        print(f"✅ Sprint '{nome}' ativada com sucesso ({data_inicio} → {data_fim})")
        return True
    else:
        print(f"❌ Erro ao ativar sprint: {resp.status_code}")
        print(f"   Resposta: {resp.text}")
        return False


def main():
    print("=" * 60)
    print("🚀 AUTOMAÇÃO DE SPRINT SEMANAL - GRAZZIOTIN SA")
    print("=" * 60)

    # Validar configuração
    validar_configuracao()

    # Data atual no fuso do Brasil
    agora = datetime.now(FUSO_BRASIL)
    hoje_str = agora.strftime("%Y-%m-%d")
    print(f"📅 Data atual: {hoje_str} ({agora.strftime('%A')})")

    # Buscar sprint ativa
    sprint_ativa = buscar_sprint_ativa()

    if sprint_ativa:
        nome_ativa = sprint_ativa["name"]
        sprint_id_ativa = sprint_ativa["id"]
        end_date_str = sprint_ativa.get("endDate", "")

        print(f"\n📋 Sprint ativa: {nome_ativa} (ID: {sprint_id_ativa})")
        print(f"   Data fim: {end_date_str}")

        # Verificar se está vencida
        if end_date_str:
            end_date = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
            hoje_date = agora.replace(hour=23, minute=59, second=59)

            if end_date <= hoje_date:
                print(f"\n⚠️ Sprint vencida! Processando...")

                # 1. Encontrar maior número para a próxima sprint
                maior_numero = encontrar_maior_numero_sprint()
                proximo_numero = maior_numero + 1

                # Calcular mês/ano
                mes_atual = agora.strftime("%m")
                ano_atual = agora.strftime("%Y")
                nome_nova = f"Sprint {proximo_numero} - {mes_atual}/{ano_atual}"

                # 2. Criar nova sprint
                print(f"\n📝 Criando: {nome_nova}")
                nova_sprint_id = criar_sprint(nome_nova)

                # 3. Mover issues pendentes
                print(f"\n🔄 Buscando issues pendentes da sprint antiga...")
                issues_pendentes = buscar_issues_pendentes(sprint_id_ativa)
                print(f"   Encontradas: {len(issues_pendentes)} issues pendentes")

                if issues_pendentes:
                    mover_issues(nova_sprint_id, issues_pendentes)

                # 4. Fechar sprint antiga
                print(f"\n🔒 Fechando sprint: {nome_ativa}")
                fechar_sprint(sprint_id_ativa, nome_ativa)

                # 5. Ativar nova sprint
                data_inicio = agora.strftime("%Y-%m-%dT%H:%M:%S.000-03:00")
                data_fim = (agora + timedelta(days=DURACAO_SPRINT_DIAS)).strftime("%Y-%m-%dT%H:%M:%S.000-03:00")

                print(f"\n▶️ Ativando sprint: {nome_nova}")
                ativar_sprint(nova_sprint_id, nome_nova, data_inicio, data_fim)

                print("\n" + "=" * 60)
                print("✅ AUTOMAÇÃO CONCLUÍDA COM SUCESSO!")
                print(f"   Sprint fechada: {nome_ativa}")
                print(f"   Sprint nova: {nome_nova}")
                print(f"   Issues movidas: {len(issues_pendentes)}")
                print("=" * 60)
            else:
                print(f"\n✅ Sprint ainda vigente. Nada a fazer.")
                print(f"   Vence em: {end_date_str[:10]}")
        else:
            print("\n⚠️ Sprint ativa sem data de fim definida. Nada a fazer.")

    else:
        # Nenhuma sprint ativa — criar e ativar uma nova
        print("\n⚠️ Nenhuma sprint ativa encontrada. Criando nova...")

        # Encontrar maior número
        maior_numero = encontrar_maior_numero_sprint()
        proximo_numero = maior_numero + 1

        mes_atual = agora.strftime("%m")
        ano_atual = agora.strftime("%Y")
        nome_nova = f"Sprint {proximo_numero} - {mes_atual}/{ano_atual}"

        # Criar
        print(f"\n📝 Criando: {nome_nova}")
        nova_sprint_id = criar_sprint(nome_nova)

        # Ativar
        data_inicio = agora.strftime("%Y-%m-%dT%H:%M:%S.000-03:00")
        data_fim = (agora + timedelta(days=DURACAO_SPRINT_DIAS)).strftime("%Y-%m-%dT%H:%M:%S.000-03:00")

        print(f"\n▶️ Ativando sprint: {nome_nova}")
        ativar_sprint(nova_sprint_id, nome_nova, data_inicio, data_fim)

        print("\n" + "=" * 60)
        print("✅ AUTOMAÇÃO CONCLUÍDA COM SUCESSO!")
        print(f"   Sprint criada e ativada: {nome_nova}")
        print("=" * 60)


if __name__ == "__main__":
    main()
