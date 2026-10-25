# PRD · Painel de Variabilidade em Cirurgias Eletivas

> Cópia do PRD mantido no Confluence.

| | |
| --- | --- |
| Status | v1 entregue · v2 em discovery |
| Autor | Ygor Taramelli |
| Dados | SIH/SUS (DATASUS) · São Paulo · competências de jan. a dez. de 2024 |
| Atualizado em | 25/10/2026 |

**Em uma frase:** para o mesmo procedimento, hospitais do SUS-SP mantêm o paciente internado por tempos muito diferentes. Se cada hospital operasse na mediana dos seus pares, o estado liberaria cerca de **153 mil leitos-dia por ano (~420 leitos)**. Este produto mostra onde está esse excedente e o que precisa ser checado antes de agir.

## 1. Problema

Cirurgias eletivas dependem de leito livre. Quando a permanência pós-operatória passa do necessário, o leito fica ocupado, cirurgias são remarcadas e a fila cresce. Hoje o gestor não tem uma visão simples de **quanto** da permanência é excedente, **em quais procedimentos** e **em quais hospitais**, e por isso não consegue priorizar onde padronizar protocolos.

## 2. Para quem

| Persona | O que precisa decidir | Pergunta que o painel responde |
| --- | --- | --- |
| **Gestor de regulação** (secretaria estadual ou regional) | Em quais hospitais e procedimentos atuar primeiro | "Onde estão os leitos-dia que posso recuperar?" |
| **Diretor de centro cirúrgico** (hospital) | Se o protocolo do hospital está fora do padrão | "Para este procedimento, meu hospital está acima dos pares? Por quê?" |

## 3. Evidências (discovery com dados)

- **Volume:** 733.473 cirurgias eletivas em 477 hospitais, R$ 1,46 bi pagos pelo SUS em 2024.
- **Variabilidade alta em procedimentos simples:** na hernioplastia inguinal, a permanência média vai de 0 a 25 dias entre hospitais; o hospital típico fica 1 dia. Na colecistectomia por vídeo, 98 hospitais estão acima da mediana dos pares (1,2 dia).
- **Concentração:** os 20 hospitais com mais excedente respondem por 51% dos leitos-dia excedentes.
- **Perfil de risco diferente:** esses 20 hospitais recebem pacientes mais graves (UTI 6,5% × 2,3%; alta complexidade 29% × 18%; idade média 51 × 47 anos).

## 4. Hipóteses

| # | Hipótese | Como validar | Status |
| --- | --- | --- | --- |
| H1 | O excedente é concentrado o bastante para que atuar em poucos hospitais gere a maior parte do ganho | Curva de concentração do excedente por hospital | Confirmada |
| H2 | Parte do excedente é explicada pelo perfil do paciente, e não pelo protocolo | Comparar UTI, complexidade e idade entre hospitais acima e abaixo do padrão | Parcial |
| H3 | Padronizar protocolos de alta nos procedimentos de maior volume reduz a permanência sem piorar desfechos | Piloto em 3 hospitais com acompanhamento de permanência e readmissão | Não testada |

## 5. Objetivo e métricas

- **Métrica principal:** leitos-dia excedentes por ano, total e por hospital.
- **Métricas de uso:** gestores que abrem o painel ao menos uma vez por mês; hospitais prioritários com plano de ação registrado.
- **Guarda-corpos:** taxa de óbito e de UTI por procedimento não podem subir nos hospitais que reduzirem permanência.

## 6. Escopo

**Na v1**

- Visão geral do estado com KPIs e tendência mensal
- Variabilidade por procedimento: mediana dos pares, permanência prevista na SIGTAP e hospitais acima do padrão
- Ranking de hospitais com o excedente ao lado do perfil de risco

**Fora da v1**

- Ajuste estatístico por risco do paciente (v2)
- Readmissão em 30 dias: exige ligar AIHs do mesmo paciente
- Outros estados e série histórica
- Fila de espera: o SIH só registra quem foi operado

## 7. Requisitos e critérios de aceite

| ID | Requisito | Critério de aceite |
| --- | --- | --- |
| RF1 | Mostrar o volume e o excedente do estado | Dado o ano de 2024, quando o gestor abre a visão geral, então vê cirurgias, hospitais, valor pago, permanência média, leitos-dia excedentes e leitos equivalentes, e os números batem com a base de origem. |
| RF2 | Comparar hospitais em um procedimento | Dado um procedimento elegível, quando o gestor o seleciona, então vê a mediana dos pares, a permanência SIGTAP e a lista de hospitais acima do padrão, considerando só hospitais com 20 cirurgias ou mais desse procedimento. |
| RF3 | Priorizar hospitais sem esconder o perfil de risco | Dado o ranking por excedente, então cada hospital aparece com taxa de UTI, % de alta complexidade, idade média e taxa de óbito na mesma linha. |
| RF4 | Comparar apenas o que é comparável | Procedimentos com menos de 300 cirurgias, menos de 10 hospitais ou códigos guarda-chuva (forma 0415) não entram no benchmark nem no excedente. |
| RF5 | Reprodutibilidade | Dado o repositório, quando os scripts 01, 02 e 03 são executados, então o mesmo painel é gerado a partir dos dados públicos. |

## 8. Definições

- **Mediana dos pares:** mediana das permanências médias dos hospitais comparáveis, por procedimento. Representa o "hospital típico".
- **Leitos-dia excedentes:** (permanência média do hospital − mediana dos pares) × nº de cirurgias, quando positivo.
- **Leitos equivalentes:** leitos-dia excedentes ÷ 365.

## 9. Riscos e limitações

**Excedente não é sinônimo de ineficiência.** Hospitais-escola e de referência recebem casos mais graves, e há motivos não clínicos para permanência (ex.: o hospital do sistema penitenciário, com 274 cirurgias comparáveis e 5,8 mil dias excedentes, por logística de escolta). Usar o painel para punir hospitais, sem conversa, é o principal risco do produto.

- O valor pago pelo SUS é tabelado: o painel não mede custo real do hospital.
- O período é por competência (mês de faturamento), não por data da cirurgia.

## 10. Próximos passos

- [ ] Validar o painel com 2 gestores de regulação e 2 diretores de centro cirúrgico
- [ ] v2: excedente ajustado por idade, UTI e complexidade
- [ ] v2: readmissão em 30 dias como guarda-corpo
