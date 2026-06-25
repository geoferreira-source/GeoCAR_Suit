# GeoCAR_Suit
Este artigo descreve a metodologia de desenvolvimento e instalacao do plugin GeoCAR_Suit-QGIS, um sistema modular em Python integrado ao QGIS para automação do processamento e analise espacial de imoveis registrados no Cadastro Ambiental Rural (CAR), conforme a Lei Federal n. 12.651/2012 (Codigo Florestal Brasileiro).
O trabalho de analise ambiental compreende etapas repetitivas que incluem consulta ao SICAR ou SEMAS-PA, download de arquivos vetoriais, extracao de pacotes ZIP, carregamento de shapefiles e execucao de analises de sobreposicao espacial. A proposta metodologica divide o sistema em oito modulos funcionais independentes, orquestrados por um nucleo central, permitindo processamento em lote de dezenas de imóveis com geração automatica de relatórios em formato xlsx.

<img width="200" height="200" alt="logo" src="https://github.com/user-attachments/assets/179358cf-467d-4626-9db7-61bcf99d96a8" />
