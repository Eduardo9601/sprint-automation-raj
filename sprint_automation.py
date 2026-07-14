"""
Sprint Automation - RAJ Board
Automação semanal de sprints com notificação Teams (Adaptive Card) e relatório Confluence.
"""

import os
import sys
import json
import requests
from datetime import datetime, timedelta, timezone


# ============================================================
# CONFIGURAÇÕES
# ============================================================

JIRA_DOMAIN = os.environ.get("JIRA_DOMAIN", "")
JIRA_EMAIL = os.environ.get("JIRA_EMAIL", "")
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN", "")
BOARD_ID = os.environ.get("BOARD_ID", "")
TEAMS_WEBHOOK_URL = os.environ.get("TEAMS_WEBHOOK_URL", "")
CONFLUENCE_SPACE_KEY = os.environ.get("CONFLUENCE_SPACE_KEY", "")
CONFLUENCE_PARENT_PAGE_ID = os.environ.get("CONFLUENCE_PARENT_PAGE_ID", "")

BASE_URL = f"https://{JIRA_DOMAIN}/rest/agile/1.0"
JIRA_BASE_URL = f"https://{JIRA_DOMAIN}/rest/api/3"
AUTH = (JIRA_EMAIL, JIRA_API_TOKEN)
HEADERS = {"Accept": "application/json", "Content-Type": "application/json"}

# Timezone Brasil
TZ_BRASIL = timezone(timedelta(hours=-3))


# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

def agora_brasil():
    """Retorna datetime atual no fuso do Brasil."""
    return datetime.now(TZ_BRASIL)


def log(msg):
    """Print com timestamp."""
    print(f"[{agora_brasil().strftime('%H:%M:%S')}] {msg}")


# ============================================================
# FUNÇÕES JIRA
# ============================================================

def obter_todas_sprints():
    """Busca TODAS as sprints do board (paginando)."""
    todas = []
    start = 0
    while True:
        url = f"{BASE_URL}/board/{BOARD_ID}/sprint?startAt={start}&maxResults=50"
        resp = requests.get(url, auth=AUTH, headers=HEADERS)
        if resp.status_code != 200:
            log(f"❌ Erro ao buscar sprints: {resp.status_code} - {resp.text}")
            sys.exit(1)
        data = resp.json()
        sprints = data.get("values", [])
        todas.extend(sprints)
        if data.get("isLast", True):
            break
        start += len(sprints)
    return todas


def obter_sprint_ativa():
    """Retorna a sprint ativa do board, ou None."""
    todas = obter_todas_sprints()
    ativas = [s for s in todas if s.get("state") == "active"]
    return ativas[0] if ativas else None


def obter_maior_numero_sprint():
    """Retorna o maior número de sprint encontrado (ex: 49 de 'Sprint 49 - 07/2026')."""
    todas = obter_todas_sprints()
    maior = 0
    for s in todas:
        nome = s.get("name", "")
        # Tenta extrair número do nome "Sprint XX ..."
        partes = nome.split()
        for p in partes:
            if p.isdigit():
                num = int(p)
                if num > maior:
                    maior = num
                break
    return maior


def obter_issues_sprint(sprint_id):
    """Retorna todas as issues de uma sprint."""
    issues = []
    start = 0
    while True:
        url = f"{BASE_URL}/sprint/{sprint_id}/issue?startAt={start}&maxResults=50"
        resp = requests.get(url, auth=AUTH, headers=HEADERS)
        if resp.status_code != 200:
            log(f"❌ Erro ao buscar issues: {resp.status_code}")
            return issues
        data = resp.json()
        issues.extend(data.get("issues", []))
        if start + 50 >= data.get("total", 0):
            break
        start += 50
    return issues


def criar_sprint(nome, start_date, end_date):
    """Cria uma nova sprint no board."""
    url = f"{BASE_URL}/sprint"
    payload = {
        "name": nome,
        "startDate": start_date,
        "endDate": end_date,
        "originBoardId": int(BOARD_ID)
    }
    resp = requests.post(url, auth=AUTH, headers=HEADERS, json=payload)
    if resp.status_code in [200, 201]:
        sprint = resp.json()
        log(f"✅ Sprint criada! ID: {sprint['id']} - Nome: {nome}")
        return sprint
    else:
        log(f"❌ Erro ao criar sprint: {resp.status_code} - {resp.text}")
        sys.exit(1)


def ativar_sprint(sprint_id, nome, start_date, end_date):
    """Ativa uma sprint (state = active)."""
    url = f"{BASE_URL}/sprint/{sprint_id}"
    payload = {
        "name": nome,
        "state": "active",
        "startDate": start_date,
        "endDate": end_date
    }
    resp = requests.put(url, auth=AUTH, headers=HEADERS, json=payload)
    if resp.status_code == 200:
        log(f"✅ Sprint ativada com sucesso: {nome}")
    else:
        log(f"❌ Erro ao ativar: {resp.status_code} - Resposta: {resp.text}")
        sys.exit(1)


def fechar_sprint(sprint_id, nome):
    """Fecha/conclui uma sprint."""
    url = f"{BASE_URL}/sprint/{sprint_id}"
    payload = {
        "name": nome,
        "state": "closed"
    }
    resp = requests.put(url, auth=AUTH, headers=HEADERS, json=payload)
    if resp.status_code == 200:
        log(f"✅ Sprint fechada: {nome}")
    else:
        # Tenta com completeDate
        payload["completeDate"] = agora_brasil().strftime("%Y-%m-%dT%H:%M:%S.000-03:00")
        resp2 = requests.put(url, auth=AUTH, headers=HEADERS, json=payload)
        if resp2.status_code == 200:
            log(f"✅ Sprint fechada (com completeDate): {nome}")
        else:
            log(f"❌ Erro ao fechar sprint: {resp2.status_code} - {resp2.text}")
            sys.exit(1)


def mover_issues_para_sprint(sprint_id, issue_keys):
    """Move issues para outra sprint."""
    if not issue_keys:
        return
    url = f"{BASE_URL}/sprint/{sprint_id}/issue"
    payload = {"issues": issue_keys}
    resp = requests.post(url, auth=AUTH, headers=HEADERS, json=payload)
    if resp.status_code == 204:
        log(f"✅ {len(issue_keys)} issues movidas para sprint {sprint_id}")
    else:
        log(f"⚠️ Erro ao mover issues: {resp.status_code} - {resp.text}")


# ============================================================
# NOTIFICAÇÃO TEAMS (ADAPTIVE CARD COM LINKS)
# ============================================================

def enviar_notificacao_teams(sprint_fechada_nome, sprint_nova_nome, issues_concluidas, issues_movidas):
    """Envia resumo semanal para o Teams via Adaptive Card com links clicáveis."""
    if not TEAMS_WEBHOOK_URL:
        log("ℹ️ TEAMS_WEBHOOK_URL não configurado. Pulando notificação.")
        return

    agora = agora_brasil().strftime("%d/%m/%Y às %H:%M")

    # Monta lista de concluídas com links
    lista_concluidas = ""
    for issue in issues_concluidas:
        key = issue.get("key", "???")
        summary = issue.get("fields", {}).get("summary", "Sem título")
        link = f"https://{JIRA_DOMAIN}/browse/{key}"
        lista_concluidas += f"- ✅ [{key}]({link}) — {summary}\n"

    if not lista_concluidas:
        lista_concluidas = "- Nenhuma tarefa finalizada nesta sprint\n"

    # Monta lista de transferidas com links
    lista_movidas = ""
    for issue in issues_movidas:
        key = issue.get("key", "???")
        summary = issue.get("fields", {}).get("summary", "Sem título")
        link = f"https://{JIRA_DOMAIN}/browse/{key}"
        lista_movidas += f"- 🔄 [{key}]({link}) — {summary}\n"

    if not lista_movidas:
        lista_movidas = "- Nenhuma tarefa transferida\n"

    # Percentual de conclusão
    total = len(issues_concluidas) + len(issues_movidas)
    percentual = round((len(issues_concluidas) / total * 100)) if total > 0 else 0

    # Monta o Adaptive Card
    card = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "contentUrl": None,
                "content": {
                    "type": "AdaptiveCard",
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "version": "1.4",
                    "body": [
                        {
                            "type": "TextBlock",
                            "text": f"🏁 Sprint Concluída: {sprint_fechada_nome}",
                            "weight": "Bolder",
                            "size": "Large",
                            "wrap": True
                        },
                        {
                            "type": "TextBlock",
                            "text": f"📅 Resumo gerado em {agora}",
                            "isSubtle": True,
                            "spacing": "None",
                            "wrap": True
                        },
                        {
                            "type": "TextBlock",
                            "text": f"📊 **Resumo:** {len(issues_concluidas)} concluídas | {len(issues_movidas)} transferidas | {percentual}% de conclusão",
                            "wrap": True,
                            "spacing": "Medium"
                        },
                        {
                            "type": "TextBlock",
                            "text": f"**✅ Tarefas Finalizadas ({len(issues_concluidas)}):**",
                            "weight": "Bolder",
                            "spacing": "Large",
                            "wrap": True
                        },
                        {
                            "type": "TextBlock",
                            "text": lista_concluidas,
                            "wrap": True,
                            "spacing": "Small"
                        },
                        {
                            "type": "TextBlock",
                            "text": f"**🔄 Transferidas → {sprint_nova_nome} ({len(issues_movidas)}):**",
                            "weight": "Bolder",
                            "spacing": "Large",
                            "wrap": True
                        },
                        {
                            "type": "TextBlock",
                            "text": lista_movidas,
                            "wrap": True,
                            "spacing": "Small"
                        }
                    ],
                    "actions": [
                        {
                            "type": "Action.OpenUrl",
                            "title": "📋 Ver Board no Jira",
                            "url": f"https://{JIRA_DOMAIN}/jira/software/c/projects/RAJ/boards/{BOARD_ID}"
                        }
                    ]
                }
            }
        ]
    }

    try:
        resp = requests.post(TEAMS_WEBHOOK_URL, json=card, headers={"Content-Type": "application/json"})
        if resp.status_code in [200, 202]:
            log("✅ Notificação enviada para o Teams!")
        else:
            log(f"⚠️ Teams respondeu com status {resp.status_code}: {resp.text}")
    except Exception as e:
        log(f"⚠️ Erro ao enviar para Teams: {e}")


# ============================================================
# RELATÓRIO CONFLUENCE
# ============================================================

def criar_relatorio_confluence(sprint_fechada_nome, sprint_nova_nome, issues_concluidas, issues_movidas):
    """Cria uma página no Confluence com o relatório da sprint."""
    if not CONFLUENCE_SPACE_KEY or not CONFLUENCE_PARENT_PAGE_ID:
        log("ℹ️ Confluence não configurado (CONFLUENCE_SPACE_KEY ou CONFLUENCE_PARENT_PAGE_ID ausente). Pulando relatório.")
        return

    agora = agora_brasil()
    titulo = f"Relatório Sprint - {sprint_fechada_nome} ({agora.strftime('%d/%m/%Y')})"

    # Percentual
    total = len(issues_concluidas) + len(issues_movidas)
    percentual = round((len(issues_concluidas) / total * 100)) if total > 0 else 0

    # Monta tabela de concluídas
    tabela_concluidas = ""
    for issue in issues_concluidas:
        key = issue.get("key", "???")
        summary = issue.get("fields", {}).get("summary", "Sem título")
        assignee = issue.get("fields", {}).get("assignee", {})
        assignee_name = assignee.get("displayName", "Não atribuído") if assignee else "Não atribuído"
        tabela_concluidas += f"<tr><td><a href='https://{JIRA_DOMAIN}/browse/{key}'>{key}</a></td><td>{summary}</td><td>{assignee_name}</td><td>✅ Concluída</td></tr>"

    # Monta tabela de transferidas
    tabela_movidas = ""
    for issue in issues_movidas:
        key = issue.get("key", "???")
        summary = issue.get("fields", {}).get("summary", "Sem título")
        assignee = issue.get("fields", {}).get("assignee", {})
        assignee_name = assignee.get("displayName", "Não atribuído") if assignee else "Não atribuído"
        tabela_movidas += f"<tr><td><a href='https://{JIRA_DOMAIN}/browse/{key}'>{key}</a></td><td>{summary}</td><td>{assignee_name}</td><td>🔄 Transferida</td></tr>"

    # HTML da página
    corpo = f"""
    <h2>📊 Resumo</h2>
    <table>
        <tr><th>Métrica</th><th>Valor</th></tr>
        <tr><td>Sprint Concluída</td><td>{sprint_fechada_nome}</td></tr>
        <tr><td>Nova Sprint</td><td>{sprint_nova_nome}</td></tr>
        <tr><td>Data</td><td>{agora.strftime('%d/%m/%Y %H:%M')}</td></tr>
        <tr><td>Tarefas Finalizadas</td><td>{len(issues_concluidas)}</td></tr>
        <tr><td>Tarefas Transferidas</td><td>{len(issues_movidas)}</td></tr>
        <tr><td>% Conclusão</td><td>{percentual}%</td></tr>
    </table>

    <h2>✅ Tarefas Finalizadas ({len(issues_concluidas)})</h2>
    <table>
        <tr><th>Chave</th><th>Título</th><th>Responsável</th><th>Status</th></tr>
        {tabela_concluidas if tabela_concluidas else "<tr><td colspan='4'>Nenhuma tarefa finalizada</td></tr>"}
    </table>

    <h2>🔄 Tarefas Transferidas para {sprint_nova_nome} ({len(issues_movidas)})</h2>
    <table>
        <tr><th>Chave</th><th>Título</th><th>Responsável</th><th>Status</th></tr>
        {tabela_movidas if tabela_movidas else "<tr><td colspan='4'>Nenhuma tarefa transferida</td></tr>"}
    </table>

    <hr/>
    <p><em>Relatório gerado automaticamente pela automação de sprints.</em></p>
    """

    # Cria a página no Confluence
    url = f"https://{JIRA_DOMAIN}/wiki/rest/api/content"
    payload = {
        "type": "page",
        "title": titulo,
        "space": {"key": CONFLUENCE_SPACE_KEY},
        "ancestors": [{"id": CONFLUENCE_PARENT_PAGE_ID}],
        "body": {
            "storage": {
                "value": corpo,
                "representation": "storage"
            }
        }
    }

    try:
        resp = requests.post(url, auth=AUTH, headers=HEADERS, json=payload)
        if resp.status_code in [200, 201]:
            page_url = resp.json().get("_links", {}).get("base", "") + resp.json().get("_links", {}).get("webui", "")
            log(f"✅ Relatório criado no Confluence: {page_url}")
        else:
            log(f"⚠️ Erro ao criar página no Confluence: {resp.status_code} - {resp.text}")
    except Exception as e:
        log(f"⚠️ Erro ao criar relatório Confluence: {e}")


# ============================================================
# LÓGICA PRINCIPAL
# ============================================================

def main():
    log("=" * 50)
    log("🚀 AUTOMAÇÃO DE SPRINT - RAJ")
    log("=" * 50)

    # Validações
    if not all([JIRA_DOMAIN, JIRA_EMAIL, JIRA_API_TOKEN, BOARD_ID]):
        log("❌ Variáveis de ambiente obrigatórias não configuradas!")
        sys.exit(1)

    # Busca sprint ativa
    sprint_ativa = obter_sprint_ativa()

    if sprint_ativa:
        nome_ativa = sprint_ativa["name"]
        sprint_id = sprint_ativa["id"]
        end_date_str = sprint_ativa.get("endDate", "")

        log(f"✅ Sprint ativa encontrada: {nome_ativa} (ID: {sprint_id})")

        # Verifica se venceu
        if not end_date_str:
            log("⚠️ Sprint ativa sem data de fim. Nenhuma ação.")
            return

        # Parse da data de fim
        end_date = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
        hoje = agora_brasil()

        if end_date.date() <= hoje.date():
            log(f"⏰ Sprint vencida! (venceu em {end_date.strftime('%d/%m/%Y')})")

            # 1. Buscar issues da sprint
            issues = obter_issues_sprint(sprint_id)
            log(f"📋 Total de issues na sprint: {len(issues)}")

            # Separar concluídas e pendentes
            issues_concluidas = []
            issues_pendentes = []
            for issue in issues:
                status_category = issue.get("fields", {}).get("status", {}).get("statusCategory", {}).get("key", "")
                if status_category == "done":
                    issues_concluidas.append(issue)
                else:
                    issues_pendentes.append(issue)

            log(f"✅ Concluídas: {len(issues_concluidas)}")
            log(f"🔄 Pendentes (serão movidas): {len(issues_pendentes)}")

            # 2. Criar nova sprint
            maior_numero = obter_maior_numero_sprint()
            novo_numero = maior_numero + 1
            mes_ano = hoje.strftime("%m/%Y")
            novo_nome = f"Sprint {novo_numero} - {mes_ano}"

            # Datas da nova sprint (1 semana)
            nova_start = hoje.strftime("%Y-%m-%dT09:00:00.000-03:00")
            nova_end = (hoje + timedelta(days=7)).strftime("%Y-%m-%dT09:00:00.000-03:00")

            nova_sprint = criar_sprint(novo_nome, nova_start, nova_end)
            nova_sprint_id = nova_sprint["id"]

            # 3. Mover issues pendentes para nova sprint
            if issues_pendentes:
                issue_keys = [i["key"] for i in issues_pendentes]
                mover_issues_para_sprint(nova_sprint_id, issue_keys)

            # 4. Fechar sprint antiga
            fechar_sprint(sprint_id, nome_ativa)

            # 5. Ativar nova sprint
            ativar_sprint(nova_sprint_id, novo_nome, nova_start, nova_end)

            # 6. Notificar Teams
            enviar_notificacao_teams(nome_ativa, novo_nome, issues_concluidas, issues_pendentes)

            # 7. Criar relatório no Confluence
            criar_relatorio_confluence(nome_ativa, novo_nome, issues_concluidas, issues_pendentes)

            log("")
            log("✅ ========== AUTOMAÇÃO CONCLUÍDA ==========")

        else:
            log(f"ℹ️ Sprint ainda não venceu (vence em {end_date.strftime('%d/%m/%Y')}). Nenhuma ação necessária.")

    else:
        log("⚠️ Nenhuma sprint ativa encontrada. Criando nova sprint...")

        # Criar e ativar nova sprint
        maior_numero = obter_maior_numero_sprint()
        novo_numero = maior_numero + 1
        hoje = agora_brasil()
        mes_ano = hoje.strftime("%m/%Y")
        novo_nome = f"Sprint {novo_numero} - {mes_ano}"

        nova_start = hoje.strftime("%Y-%m-%dT09:00:00.000-03:00")
        nova_end = (hoje + timedelta(days=7)).strftime("%Y-%m-%dT09:00:00.000-03:00")

        nova_sprint = criar_sprint(novo_nome, nova_start, nova_end)
        nova_sprint_id = nova_sprint["id"]

        ativar_sprint(nova_sprint_id, novo_nome, nova_start, nova_end)

        log("")
        log("✅ ========== AUTOMAÇÃO CONCLUÍDA ==========")


if __name__ == "__main__":
    main()
