# 🏦 Extratos Automate

### Automação Inteligente de Extração, Padronização e Consolidação de Extratos Bancários

**Python | PostgreSQL | Streamlit | OCR | PDF | Excel | Automação Financeira**

O **Extratos Automate** é um sistema desenvolvido em Python para automatizar a leitura, interpretação, transformação e consolidação de extratos bancários provenientes de diferentes instituições financeiras.

A solução foi projetada para atender cenários em que informações financeiras são disponibilizadas em formatos distintos, como **XLS, XLSX e PDF**, incluindo documentos digitalizados que necessitam de processamento por **OCR (Optical Character Recognition)**.

Seu principal objetivo é eliminar atividades repetitivas de lançamento e consolidação manual, centralizando movimentações bancárias em planilhas Excel previamente configuradas, com padronização de campos, controle de processamento e gerenciamento das execuções.

O sistema utiliza uma arquitetura modular, composta por agentes de automação, extratores especializados, um orquestrador central, banco de dados PostgreSQL e interface administrativa desenvolvida em Streamlit.

---

## 📋 1. Visão Geral

A consolidação de extratos bancários representa um desafio recorrente em operações financeiras que trabalham com múltiplas instituições, empresas e contas bancárias.

Cada instituição pode disponibilizar seus extratos em estruturas diferentes, apresentando variações como:

- Formatos de arquivos distintos.
- Diferentes nomenclaturas para campos equivalentes.
- Estruturas específicas para identificação de créditos e débitos.
- Layouts de extratos que variam entre instituições.
- Documentos PDF com texto estruturado ou digitalizado.
- Necessidade de identificar contas, períodos e movimentações.
- Consolidação de informações em uma estrutura única.

O Extratos Automate foi desenvolvido para tratar esses cenários de forma automatizada, utilizando mecanismos de identificação de arquivos, extração de dados, normalização de informações e atualização de planilhas consolidadas.

A solução também contempla um modelo de processamento orientado por configurações armazenadas em banco de dados, permitindo cadastrar instituições, layouts, diretórios e relacionamentos entre campos sem concentrar todas essas definições diretamente no código-fonte.

### Objetivos principais

**Automatizar a extração de dados financeiros**

Reduzir a necessidade de abertura manual de arquivos e transcrição de movimentações bancárias.

**Padronizar diferentes layouts**

Transformar informações provenientes de diferentes instituições em uma estrutura de dados comum.

**Consolidar informações financeiras**

Centralizar lançamentos bancários em planilhas Excel previamente configuradas.

**Controlar o processamento**

Registrar solicitações de execução, períodos processados, ações realizadas e resultados das operações.

**Facilitar a administração**

Disponibilizar uma interface para gerenciamento de bancos, diretórios, usuários, mapeamentos e execuções.

---

## 🏗️ 2. Arquitetura da Solução

O sistema utiliza uma arquitetura modular, organizada em componentes com responsabilidades específicas.

### Visão arquitetural

```text
                   EXTRATOS BANCÁRIOS
                  ┌──────────────────┐
                  │ XLS / XLSX / PDF  │
                  │ PDF Digitalizado  │
                  └─────────┬────────┘
                            │
                            ▼
                  ┌──────────────────┐
                  │ AGENTE ANALISTA   │
                  │                  │
                  │ Identificação    │
                  │ Análise          │
                  │ Controle período │
                  └─────────┬────────┘
                            │
                            ▼
                  ┌──────────────────┐
                  │    POSTGRESQL    │
                  │                  │
                  │ Configurações    │
                  │ Controle serviço │
                  │ Mapeamentos      │
                  │ Registros        │
                  └─────────┬────────┘
                            │
                            ▼
                  ┌──────────────────┐
                  │  ORQUESTRADOR    │
                  │                  │
                  │ Processamento    │
                  │ Controle ações   │
                  │ Execução         │
                  └─────────┬────────┘
                            │
                            ▼
                  ┌──────────────────┐
                  │   EXTRATORES     │
                  │                  │
                  │ Banco específico │
                  │ Excel genérico   │
                  │ PDF genérico     │
                  │ OCR              │
                  └─────────┬────────┘
                            │
                            ▼
                  ┌──────────────────┐
                  │ NORMALIZAÇÃO     │
                  │                  │
                  │ Tratamento       │
                  │ DE/PARA          │
                  │ Validação período│
                  └─────────┬────────┘
                            │
                            ▼
                  ┌──────────────────┐
                  │  PLANILHA MÃE    │
                  │                  │
                  │ Consolidação     │
                  │ Atualização      │
                  │ Exclusão período │
                  └──────────────────┘
```

O PostgreSQL atua como repositório central de configurações e controle operacional.

A interface Streamlit permite administrar parte dessas configurações e executar operações manualmente.

O processamento pode ser iniciado por diferentes caminhos, incluindo o script principal, o orquestrador e os componentes de execução.

---

## 🤖 3. Arquitetura Baseada em Agentes

Uma das principais características do projeto é a separação das responsabilidades de análise e execução.

Essa abordagem permite organizar o processamento em etapas independentes.

### 3.1 Agente Analista

**Arquivo:** `agente_analista.py`

O Agente Analista é responsável por identificar situações que necessitam de processamento.

Entre suas responsabilidades estão:

- Consultar configurações de bancos e diretórios.
- Identificar arquivos disponíveis para processamento.
- Reconhecer os layouts cadastrados.
- Analisar os períodos existentes nos arquivos.
- Verificar informações de execuções anteriores.
- Identificar períodos ainda não processados.
- Evitar a criação de solicitações redundantes para períodos já contemplados.
- Registrar solicitações de execução no PostgreSQL.

O agente atua como uma camada de análise e preparação das atividades.

Em vez de executar diretamente todas as operações de consolidação, ele registra as necessidades de processamento para posterior execução pelo sistema.

Essa separação facilita a organização do fluxo e o acompanhamento das operações.

### 3.2 Agente Estagiário

**Arquivo:** `agente_estagiario.py`

O Agente Estagiário funciona como um componente de execução das atividades pendentes.

Suas principais responsabilidades incluem:

- Consultar solicitações registradas no banco de dados.
- Identificar execuções pendentes.
- Acionar o orquestrador.
- Acompanhar o resultado da execução.
- Registrar informações de saída e eventuais falhas.

O componente utiliza execução de processos Python para iniciar o orquestrador.

A implementação contempla verificações periódicas, permitindo sua utilização em cenários de automação recorrente.

### 3.3 Orquestrador

**Arquivo:** `orquestrador.py`

O Orquestrador representa o núcleo operacional do sistema.

Ele coordena o processamento dos extratos e a atualização das planilhas consolidadas.

Suas responsabilidades incluem:

- Consultar configurações armazenadas no PostgreSQL.
- Identificar diretórios e arquivos bancários.
- Determinar o layout correspondente.
- Selecionar o extrator apropriado.
- Executar o processamento dos arquivos.
- Aplicar regras de normalização.
- Consultar mapeamentos entre campos.
- Filtrar registros por período.
- Atualizar a Planilha Mãe.
- Registrar informações das execuções.
- Controlar o resultado das operações.

O orquestrador também contempla diferentes ações de processamento, incluindo:

| Operação | Finalidade |
|---|---|
| INSERT | Inserção de registros na planilha consolidada. |
| UPDATE | Atualização ou substituição de informações conforme o período e a lógica de processamento. |
| DELETE | Remoção de registros correspondentes ao período selecionado. |

A separação entre análise, controle e execução permite manter a lógica operacional organizada e facilita a manutenção dos componentes.

---

## 🏦 4. Mecanismo de Extração Bancária

O Extratos Automate utiliza módulos especializados para interpretar diferentes layouts de extratos.

Cada extrator é responsável por compreender a estrutura de determinado formato bancário e transformar suas informações em registros que possam ser processados pelo orquestrador.

### 4.1 Extratores especializados

O projeto contém diversos módulos de extração, como:

```text
extrator_aden_dist.py
extrator_bb.py
extrator_bb_dist.py
extrator_br_dist.py
extrator_cl_dist.py
extrator_conta_simples_dist.py
extrator_daycoval_dist.py
extrator_feat_dist.py
extrator_it.py
extrator_it_dist.py
extrator_only_dist.py
extrator_our_dist.py
extrator_pl_dist.py
extrator_rend_dist.py
extrator_saf_dist.py
extrator_santander.py
extrator_sicoob_dist.py
extrator_ssg.py
extrator_st_dist.py
```

A existência de módulos especializados permite tratar particularidades de cada layout sem concentrar todas as regras de interpretação em um único arquivo.

Entre os tratamentos encontrados nos extratores analisados estão:

- Identificação de cabeçalhos.
- Localização de colunas relevantes.
- Interpretação de datas.
- Tratamento de valores monetários.
- Identificação de movimentações.
- Extração de informações de contas bancárias.
- Normalização de dados extraídos.
- Tratamento de variações de layout.

A disponibilidade de um módulo especializado não significa necessariamente que todos os arquivos de uma instituição utilizem o mesmo formato.

Por esse motivo, o sistema mantém o conceito de identificação de layouts e configuração de arquivos bancários.

### 4.2 Extratores genéricos

Além dos módulos especializados, o projeto contém extratores genéricos:

```text
extrator_pdf_generico.py
extrator_xls_generico.py
extrator_xlsx_generico.py
```

Esses componentes fazem parte da estrutura destinada ao tratamento de formatos de arquivos, complementando os extratores específicos.

A abordagem modular permite ampliar o conjunto de layouts atendidos por meio da inclusão de novos módulos.

---

## 📄 5. Processamento de PDF e OCR

O sistema contempla a extração de informações de documentos PDF, incluindo situações em que o conteúdo não está disponível diretamente como texto selecionável.

### Extração de PDFs com texto

Para documentos que possuem uma camada de texto, os extratores podem utilizar bibliotecas de leitura de PDF para recuperar informações.

O processamento envolve a interpretação do conteúdo extraído e sua transformação em registros estruturados.

### Extração de PDFs digitalizados

Quando o documento não apresenta texto diretamente utilizável, determinados extratores especializados implementam mecanismos alternativos baseados em OCR.

O OCR permite reconhecer caracteres presentes em imagens, ampliando os cenários de processamento.

### Tecnologias utilizadas

Entre as bibliotecas identificadas nos módulos analisados estão:

| Tecnologia | Aplicação |
|---|---|
| pdfplumber | Extração de texto de documentos PDF. |
| PyMuPDF | Manipulação e renderização de páginas PDF. |
| Tesseract OCR | Reconhecimento óptico de caracteres. |
| pytesseract | Integração do Python com o Tesseract. |
| Pillow | Manipulação de imagens utilizadas no processamento. |

A utilização de OCR é especialmente relevante em documentos digitalizados ou em layouts nos quais a extração convencional não consegue recuperar adequadamente o conteúdo.

**Observação:** o OCR depende da qualidade do documento, da resolução da imagem e da estrutura do extrato. Portanto, os resultados devem ser validados conforme o layout utilizado.

---

## 🔄 6. Padronização e Mapeamento DE/PARA

Instituições financeiras podem utilizar nomenclaturas diferentes para representar informações equivalentes.

Por exemplo:

| Campo de origem | Campo de destino |
|---|---|
| Histórico | Descritivo Bancário |
| Data Movimento | Data |
| Valor Movimento | Valor |
| Documento | Documento |

*Os campos acima são exemplos ilustrativos de mapeamento.*

Para resolver essas diferenças, o Extratos Automate utiliza configurações DE/PARA armazenadas no PostgreSQL.

### Funcionamento

O relacionamento entre os campos de origem e destino é armazenado na tabela:

```sql
extratos.de_para_banco_planilha_mae
```

O sistema consulta os mapeamentos correspondentes ao layout utilizado e aplica essas definições durante a preparação dos registros para a Planilha Mãe.

### Benefícios

- Padronização de campos.
- Centralização dos relacionamentos.
- Redução de regras fixas no código.
- Facilidade de manutenção.
- Suporte a diferentes layouts.
- Administração dos mapeamentos pela interface.

A interface permite cadastrar, consultar e excluir relacionamentos entre campos.

---

## 🗄️ 7. Integração com PostgreSQL

O PostgreSQL é utilizado como banco de dados de configuração e controle operacional.

A conexão é realizada por meio da biblioteca `psycopg`, utilizando parâmetros obtidos de variáveis de ambiente.

### Principais tabelas utilizadas

| Tabela | Responsabilidade |
|---|---|
| `extratos.arquivos_bancos` | Cadastro de instituições e layouts bancários. |
| `extratos.diretorios` | Configuração dos diretórios utilizados pelo sistema. |
| `extratos.de_para_banco_planilha_mae` | Relacionamento entre campos de origem e destino. |
| `extratos.controle_servico` | Controle de solicitações e execuções. |
| `extratos.usuarios` | Cadastro e gerenciamento de usuários da interface. |

O sistema também utiliza rotinas de consulta e registro relacionadas à identificação de empresas e ao acompanhamento do processamento.

### Controle de execução

A tabela `extratos.controle_servico` participa do fluxo de automação.

Ela permite armazenar informações relacionadas a:

- Identificação da execução.
- Arquivo ou layout bancário.
- Período inicial.
- Período final.
- Ação solicitada.
- Data de registro.
- Situação de execução.

Essas informações são utilizadas pelos agentes, pelo orquestrador e pela interface administrativa.

### Conexão com o banco

O módulo `inicial.py` centraliza a conexão com PostgreSQL.

A configuração utiliza variáveis como:

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=nome_do_banco
DB_USER=usuario
DB_PASSWORD=senha
```

Os valores apresentados são apenas exemplos.

As credenciais reais devem ser mantidas fora do repositório.

---

## 🖥️ 8. Interface Administrativa com Streamlit

O projeto disponibiliza uma interface desenvolvida em Streamlit para gerenciamento das principais configurações e operações.

A aplicação utiliza autenticação de usuários e navegação entre módulos.

### 8.1 Tela principal

**Arquivo:** `front_main.py`

Responsável por:

- Autenticação de usuários.
- Inicialização da sessão.
- Apresentação da página inicial.
- Organização da navegação.
- Identificação do perfil do usuário.
- Encerramento da sessão.

A navegação contempla módulos de operação, cadastro e administração.

### 8.2 Cadastro de bancos

**Arquivo:** `front_bancos.py`

Permite administrar os layouts bancários cadastrados.

Entre as informações configuráveis estão:

- Nome do banco ou layout.
- Prefixo de identificação do arquivo.
- Extensão.
- Situação ativa ou inativa.

O cadastro contempla os formatos:

```text
PDF
XLS
XLSX
```

A interface também permite consultar e atualizar os registros existentes.

### 8.3 Configuração DE/PARA

**Arquivo:** `front_de_para.py`

Permite configurar o relacionamento entre campos de extratos bancários e colunas da Planilha Mãe.

As operações disponíveis incluem:

- Seleção do banco ou layout.
- Consulta dos mapeamentos cadastrados.
- Inclusão de novos relacionamentos.
- Exclusão de relacionamentos existentes.

### 8.4 Configuração de diretórios

**Arquivo:** `front_configuracao.py`

Responsável pelo gerenciamento dos diretórios utilizados no processamento.

A interface permite:

- Cadastrar diretórios.
- Identificar diretórios locais ou de rede.
- Informar configurações de acesso.
- Ativar ou desativar registros.
- Atualizar configurações.
- Excluir diretórios cadastrados.

### 8.5 Controle de execução

**Arquivo:** `front_executor.py`

Disponibiliza recursos para acompanhamento e acionamento manual do processamento.

Entre suas funcionalidades estão:

- Consulta de execuções pendentes.
- Visualização de informações dos períodos.
- Execução das solicitações pendentes.
- Consulta da última execução por banco.
- Solicitação de reexecução.
- Apresentação das saídas do orquestrador.
- Visualização de mensagens de erro.

### 8.6 Gerenciamento de usuários

**Arquivo:** `front_usuarios.py`

Permite administrar usuários da aplicação.

As funcionalidades incluem:

- Cadastro de usuários.
- Identificação de administradores.
- Ativação e desativação de contas.
- Atualização de dados.
- Redefinição de senhas.

O módulo possui verificação de acesso administrativo.

**Nota de segurança:** a implementação atual utiliza hash SHA-256 para senhas. Para implantação em ambientes expostos, recomenda-se evoluir para um mecanismo de armazenamento de senhas com salt e algoritmo específico para esse propósito, como Argon2id.

---

## 📊 9. Consolidação na Planilha Mãe

A Planilha Mãe representa o destino das informações processadas.

O sistema utiliza a biblioteca `openpyxl` para trabalhar com arquivos Excel.

### Etapas de consolidação

**1. Identificação do arquivo**

O sistema localiza o extrato bancário e identifica o layout correspondente.

**2. Extração dos registros**

O extrator recupera as movimentações disponíveis no documento.

**3. Normalização**

As informações são tratadas para adequação à estrutura esperada.

**4. Aplicação do DE/PARA**

Os campos são relacionados às colunas da planilha de destino.

**5. Filtragem por período**

Os registros são selecionados conforme as datas definidas para a execução.

**6. Atualização da planilha**

O orquestrador aplica a operação correspondente ao processamento.

**7. Registro da execução**

As informações de controle são atualizadas conforme o resultado da operação.

### Tratamento de períodos

O projeto contempla mecanismos de filtragem de registros por intervalo de datas e de remoção de informações correspondentes a determinados períodos.

Esses recursos são importantes para cenários de reprocessamento, correção e atualização de movimentações.

---

## ⚙️ 10. Fluxo Operacional

O processamento pode ser organizado em sete etapas principais.

### Etapa 1 — Configuração

O administrador cadastra:

- Bancos e layouts.
- Prefixos de arquivos.
- Extensões.
- Diretórios.
- Relacionamentos DE/PARA.
- Usuários da interface.

### Etapa 2 — Disponibilização dos extratos

Os arquivos bancários são disponibilizados nos diretórios configurados.

### Etapa 3 — Análise

O Agente Analista consulta os arquivos e identifica os períodos que necessitam de processamento.

### Etapa 4 — Registro da solicitação

As operações identificadas são registradas no PostgreSQL.

### Etapa 5 — Execução

O orquestrador é acionado pelo fluxo principal, pelo agente responsável pela execução ou pela interface administrativa.

### Etapa 6 — Consolidação

Os registros são extraídos, normalizados e encaminhados à Planilha Mãe.

### Etapa 7 — Controle

O resultado do processamento é registrado para acompanhamento das operações.

---

## 🧰 11. Tecnologias Utilizadas

| Tecnologia | Aplicação no projeto |
|---|---|
| Python | Linguagem principal. |
| PostgreSQL | Persistência de configurações e controles. |
| psycopg | Conexão Python com PostgreSQL. |
| Streamlit | Interface administrativa. |
| pandas | Manipulação e transformação de dados. |
| openpyxl | Leitura e atualização de planilhas Excel. |
| pdfplumber | Extração de conteúdo de PDFs. |
| PyMuPDF | Manipulação de documentos PDF. |
| pytesseract | Integração com OCR. |
| Tesseract OCR | Reconhecimento de texto em imagens. |
| Pillow | Processamento de imagens. |
| python-dotenv | Carregamento de variáveis de ambiente. |
| subprocess | Execução de componentes Python. |

A utilização dessas tecnologias permite combinar processamento de arquivos, persistência relacional e interface administrativa em uma solução integrada.

---

## 📂 12. Estrutura do Projeto

A estrutura abaixo apresenta os principais componentes do código-fonte.

```text
Extratos-Automate/
│
├── main.py
├── inicial.py
├── orquestrador.py
│
├── agente_analista.py
├── agente_estagiario.py
│
├── front_main.py
├── front_bancos.py
├── front_configuracao.py
├── front_de_para.py
├── front_executor.py
├── front_usuarios.py
│
├── extrator_aden_dist.py
├── extrator_bb.py
├── extrator_bb_dist.py
├── extrator_br_dist.py
├── extrator_cl_dist.py
├── extrator_conta_simples_dist.py
├── extrator_daycoval_dist.py
├── extrator_feat_dist.py
├── extrator_it.py
├── extrator_it_dist.py
├── extrator_only_dist.py
├── extrator_our_dist.py
├── extrator_pdf_generico.py
├── extrator_pl_dist.py
├── extrator_rend_dist.py
├── extrator_saf_dist.py
├── extrator_santander.py
├── extrator_sicoob_dist.py
├── extrator_ssg.py
├── extrator_st_dist.py
├── extrator_xls_generico.py
├── extrator_xlsx_generico.py
│
├── apagador.py
├── teste_br.py
│
├── .gitignore
└── README.md
```

### Organização lógica

**Agentes:** análise e acionamento das atividades.

**Orquestrador:** coordenação do processamento.

**Extratores:** interpretação dos documentos bancários.

**Frontend:** administração e acompanhamento operacional.

**Banco de dados:** configurações e controle das execuções.

**Utilitários:** rotinas auxiliares de manutenção e testes.

---

## 🚀 13. Instalação e Configuração

### Pré-requisitos

Para executar o projeto, são necessários:

- Python instalado.
- PostgreSQL disponível.
- Bibliotecas Python utilizadas pelos módulos.
- Diretórios de entrada e saída configurados.
- Estrutura de banco de dados compatível com as tabelas utilizadas.
- Tesseract OCR instalado, quando necessário para os layouts que utilizam reconhecimento óptico.

### 13.1 Clonar o repositório

```bash
git clone https://github.com/felipenunescardoso/Extratos-Automate.git

cd Extratos-Automate
```

### 13.2 Criar um ambiente virtual

No Windows:

```powershell
python -m venv .venv
```

Ativar:

```powershell
.\.venv\Scripts\Activate.ps1
```

### 13.3 Instalar as dependências

As dependências principais identificadas nos componentes analisados podem ser instaladas com:

```powershell
pip install psycopg[binary] python-dotenv pandas openpyxl streamlit pdfplumber pymupdf pytesseract pillow xlrd
```

A relação acima representa as principais bibliotecas identificadas e pode precisar de complementos conforme os extratores utilizados.

### 13.4 Configurar o PostgreSQL

Crie um arquivo `.env` na raiz do projeto com os parâmetros de conexão:

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=nome_do_banco
DB_USER=usuario
DB_PASSWORD=senha
```

**Nunca publique credenciais reais no GitHub.**

### 13.5 Preparar o banco de dados

O sistema depende de estruturas existentes no schema `extratos`, incluindo tabelas de configuração, mapeamento, usuários e controle de execução.

A instalação em um ambiente novo exige que essas estruturas sejam previamente criadas.

O repositório de código-fonte, isoladamente, não substitui a configuração do banco de dados.

### 13.6 Testar a conexão

Execute:

```powershell
python inicial.py
```

O módulo realiza uma tentativa de conexão com PostgreSQL e informa o resultado no terminal.

### 13.7 Executar o processamento

O script principal inicia o Agente Analista e, posteriormente, o Orquestrador.

```powershell
python main.py
```

Também é possível executar diretamente o orquestrador:

```powershell
python orquestrador.py
```

### 13.8 Iniciar a interface administrativa

```powershell
streamlit run front_main.py
```

Após iniciar o Streamlit, acesse o endereço local apresentado no terminal.

O acesso à aplicação depende de um usuário previamente cadastrado no banco de dados.

**Observação:** alguns componentes utilizam caminhos locais específicos. A implantação em outro ambiente pode exigir ajustes de diretórios e configurações.

---

## 🔐 14. Segurança e Boas Práticas

O Extratos Automate trabalha com informações financeiras e configurações de acesso.

Por esse motivo, a implantação deve considerar medidas de proteção compatíveis com a sensibilidade dos dados.

### Proteção de credenciais

As credenciais de conexão com PostgreSQL são obtidas por variáveis de ambiente.

Arquivos `.env` não devem ser versionados.

### Controle de usuários

A interface possui autenticação e diferenciação entre perfis administrativos e usuários comuns.

### Proteção dos extratos

Arquivos bancários reais não devem ser incluídos em repositórios públicos.

### Proteção das planilhas

As planilhas consolidadas podem conter informações financeiras e devem permanecer em diretórios com acesso controlado.

### Auditoria e execução

O sistema mantém registros operacionais de processamento no PostgreSQL, permitindo consultar solicitações e acompanhar execuções.

### Recomendações para implantação

- Utilizar credenciais com permissões mínimas necessárias.
- Restringir o acesso ao PostgreSQL.
- Proteger os diretórios de entrada e saída.
- Evitar armazenamento de senhas de rede em texto simples.
- Revisar o mecanismo de armazenamento de senhas dos usuários.
- Realizar backups das planilhas consolidadas.
- Validar os resultados de extração por OCR.
- Não utilizar dados financeiros reais em testes públicos.
- Revisar os scripts antes de disponibilizar o sistema em redes externas.

---

## 📈 15. Benefícios da Automação

### Redução de atividades manuais

A leitura e consolidação automatizadas diminuem a necessidade de transcrição de lançamentos.

### Padronização das informações

O mapeamento DE/PARA permite trabalhar com estruturas de origem diferentes e um destino comum.

### Escalabilidade funcional

Novos layouts podem ser incorporados por meio de extratores adicionais e configurações correspondentes.

### Centralização operacional

O PostgreSQL reúne configurações e informações de controle utilizadas pelos componentes.

### Flexibilidade de processamento

O sistema contempla execução automatizada e acionamento manual.

### Facilidade de manutenção

A separação entre agentes, orquestrador, extratores e interface reduz o acoplamento entre diferentes responsabilidades.

### Tratamento de documentos digitalizados

O suporte a OCR em extratores específicos amplia os formatos de documentos que podem ser processados.

---

## 🧩 16. Diferenciais Técnicos

O Extratos Automate reúne características relevantes para projetos de automação de processos e engenharia de dados.

**Arquitetura modular**

Separação entre análise, execução, extração e administração.

**Automação orientada por configurações**

Utilização de PostgreSQL para controlar layouts, diretórios e mapeamentos.

**Suporte a múltiplos formatos**

Processamento de arquivos XLS, XLSX e PDF.

**Integração com OCR**

Tratamento de documentos que não possuem texto diretamente acessível.

**Processamento por período**

Identificação e tratamento de movimentações conforme intervalos de datas.

**Controle de reexecução**

Possibilidade de solicitar novamente o processamento de execuções existentes.

**Interface administrativa**

Gerenciamento de configurações e operações por meio de Streamlit.

**Consolidação em Excel**

Integração com planilhas previamente estruturadas para centralização das informações.

---

## 🔧 17. Evolução e Possíveis Melhorias

O projeto possui uma arquitetura que permite incorporar novas funcionalidades.

Entre as possibilidades de evolução estão:

- Ampliação do catálogo de extratores bancários.
- Aprimoramento do reconhecimento automático de layouts.
- Evolução dos mecanismos de OCR.
- Implementação de testes automatizados.
- Ampliação das validações de integridade dos lançamentos.
- Criação de indicadores operacionais de processamento.
- Implementação de notificações de falhas.
- Centralização das configurações de caminhos locais.
- Evolução dos mecanismos de autenticação e segurança.
- Disponibilização de scripts de instalação do banco de dados.
- Criação de um pacote de implantação com dependências versionadas.

Esses itens representam oportunidades de evolução e não funcionalidades necessariamente implementadas na versão atual.

---

## 🎯 18. Aplicações

A solução foi desenvolvida para cenários que necessitam de consolidação recorrente de extratos bancários.

Entre as possíveis aplicações estão:

- Departamentos financeiros.
- Tesouraria.
- Controladoria.
- Consolidação bancária de múltiplas empresas.
- Automatização de rotinas administrativas.
- Preparação de informações para conciliação financeira.
- Processamento de documentos financeiros digitalizados.
- Centralização de movimentações provenientes de diferentes instituições.

---

## 👨‍💻 19. Desenvolvimento

**Desenvolvedor:** Felipe Nunes Cardoso

**Projeto:** Extratos Automate

**Linguagem principal:** Python

**Banco de dados:** PostgreSQL

**Interface:** Streamlit

**Área de aplicação:** Automação Financeira e Engenharia de Dados

O projeto demonstra a aplicação prática de conceitos de:

- Automação de processos.
- Integração de sistemas.
- Processamento e transformação de dados.
- Manipulação de arquivos estruturados e semiestruturados.
- Modelagem e utilização de bancos de dados relacionais.
- Desenvolvimento de interfaces administrativas.
- Organização modular de aplicações Python.
- Controle de processamento e execução de tarefas.

---

## 📌 20. Considerações Finais

O **Extratos Automate** representa uma solução de automação voltada à integração e consolidação de informações bancárias provenientes de diferentes formatos e instituições.

Sua arquitetura combina agentes de processamento, extratores especializados, mecanismos de normalização, controle operacional em PostgreSQL e interface administrativa em Streamlit.

O projeto demonstra como tecnologias de código aberto podem ser utilizadas para reduzir atividades manuais, organizar processos financeiros e transformar documentos bancários heterogêneos em informações estruturadas.

A separação de responsabilidades entre os componentes também estabelece uma base para manutenção e evolução contínua do sistema.

---

**Extratos Automate — Automação, padronização e consolidação inteligente de informações bancárias.**
