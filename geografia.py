# -*- coding: utf-8 -*-
"""
A GEOGRAFIA da rota.

O planner nao pode mandar o vendedor para Castanhal na segunda,
Belem na terca e Castanhal de novo na quarta. Para isso ele precisa saber
o que e perto do que - e e isso que este arquivo guarda:

  CIDADES  a coordenada (latitude e longitude) de cada municipio das 6 UFs
           que a BAP atende, mais as cidades soltas que aparecem na base.
           Fonte: tabela de municipios do IBGE.

  BAIRROS  em Manaus, a ZONA administrativa de cada bairro oficial da
           Prefeitura (Norte, Sul, Leste, Oeste, Centro-Sul e
           Centro-Oeste). Bairro escrito errado ou com numero na ponta
           ("CACHOEIRNHA", "CIDADE NOVA 2") e reconhecido assim mesmo.

Com isso a rota fecha a cidade inteira antes de ir para a proxima, e
dentro da cidade grande anda por regiao, sem atravessar Manaus duas vezes
no mesmo dia.

Nada aqui vai a internet: a tabela ja vem pronta no arquivo.
"""
from __future__ import annotations

import difflib
import math
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

# ==========================================================================
# municipios: UF|CIDADE|latitude|longitude   (IBGE)
# ==========================================================================
_CIDADES_TEXTO = """\
AM|ALVARAES|-3.2273|-64.8007
AM|AMATURA|-3.3746|-68.2005
AM|ANAMA|-3.5670|-61.3963
AM|ANORI|-3.7460|-61.6575
AM|APUI|-7.1941|-59.8960
AM|ATALAIA DO NORTE|-4.3705|-70.1967
AM|AUTAZES|-3.5857|-59.1256
AM|BARCELOS|-0.9834|-62.9311
AM|BARREIRINHA|-2.7989|-57.0679
AM|BENJAMIN CONSTANT|-4.3777|-70.0342
AM|BERURI|-3.8987|-61.3616
AM|BOA VISTA DO RAMOS|-2.9741|-57.5873
AM|BOCA DO ACRE|-8.7423|-67.3919
AM|BORBA|-4.3915|-59.5874
AM|CAAPIRANGA|-3.3154|-61.2206
AM|CANUTAMA|-6.5258|-64.3953
AM|CARAUARI|-4.8816|-66.9086
AM|CAREIRO DA VARZEA|-3.3140|-59.5557
AM|CAREIRO|-3.7680|-60.3690
AM|COARI|-4.0941|-63.1441
AM|CODAJAS|-3.8305|-62.0658
AM|EIRUNEPE|-6.6568|-69.8662
AM|ENVIRA|-7.4379|-70.0281
AM|FONTE BOA|-2.5234|-66.0942
AM|GUAJARA|-7.5380|-72.5907
AM|HUMAITA|-7.5117|-63.0327
AM|IPIXUNA|-7.0479|-71.6934
AM|IRANDUBA|-3.2748|-60.1900
AM|ITACOATIARA|-3.1386|-58.4449
AM|ITAMARATI|-6.4385|-68.2437
AM|ITAPIRANGA|-2.7408|-58.0293
AM|JAPURA|-1.8824|-66.9291
AM|JURUA|-3.4844|-66.0718
AM|JUTAI|-2.7581|-66.7595
AM|LABREA|-7.2641|-64.7948
AM|MANACAPURU|-3.2907|-60.6216
AM|MANAQUIRI|-3.4408|-60.4612
AM|MANAUS|-3.1187|-60.0212
AM|MANICORE|-5.8046|-61.2895
AM|MARAA|-1.8531|-65.5730
AM|MAUES|-3.3929|-57.7067
AM|NHAMUNDA|-2.2079|-56.7112
AM|NOVA OLINDA DO NORTE|-3.9004|-59.0940
AM|NOVO AIRAO|-2.6364|-60.9434
AM|NOVO ARIPUANA|-5.1259|-60.3732
AM|PARINTINS|-2.6374|-56.7290
AM|PAUINI|-7.7131|-66.9920
AM|PRESIDENTE FIGUEIREDO|-2.0298|-60.0234
AM|RIO PRETO DA EVA|-2.7045|-59.6858
AM|SANTA ISABEL DO RIO NEGRO|-0.4108|-65.0092
AM|SANTO ANTONIO DO ICA|-3.0954|-67.9463
AM|SAO GABRIEL DA CACHOEIRA|-0.1191|-67.0840
AM|SAO PAULO DE OLIVENCA|-3.4729|-68.9646
AM|SAO SEBASTIAO DO UATUMA|-2.5591|-57.8731
AM|SILVES|-2.8175|-58.2480
AM|TABATINGA|-4.2416|-69.9383
AM|TAPAUA|-5.6208|-63.1808
AM|TEFE|-3.3682|-64.7193
AM|TONANTINS|-2.8658|-67.7919
AM|UARINI|-2.9961|-65.1133
AM|URUCARA|-2.5294|-57.7538
AM|URUCURITUBA|-3.1284|-58.1496
AP|AMAPA|2.0527|-50.7957
AP|CALCOENE|2.5048|-50.9512
AP|CUTIAS|0.9708|-50.8005
AP|FERREIRA GOMES|0.8573|-51.1795
AP|ITAUBAL|0.6022|-50.6996
AP|LARANJAL DO JARI|-0.8049|-52.4530
AP|MACAPA|0.0349|-51.0694
AP|MAZAGAO|-0.1134|-51.2891
AP|OIAPOQUE|3.8407|-51.8331
AP|PEDRA BRANCA DO AMAPARI|0.7774|-51.9503
AP|PORTO GRANDE|0.7124|-51.4155
AP|PRACUUBA|1.7454|-50.7892
AP|SANTANA|-0.0454|-51.1729
AP|SERRA DO NAVIO|0.9014|-52.0036
AP|TARTARUGALZINHO|1.5065|-50.9087
AP|VITORIA DO JARI|-0.9380|-52.4240
GO|GOIANIA|-16.6864|-49.2643
MA|ACAILANDIA|-4.9471|-47.5004
MA|AFONSO CUNHA|-4.1363|-43.3275
MA|AGUA DOCE DO MARANHAO|-2.8405|-42.1189
MA|ALCANTARA|-2.3957|-44.4062
MA|ALDEIAS ALTAS|-4.6262|-43.4689
MA|ALTAMIRA DO MARANHAO|-4.1660|-45.4706
MA|ALTO ALEGRE DO MARANHAO|-4.2130|-44.4460
MA|ALTO ALEGRE DO PINDARE|-3.6669|-45.8421
MA|ALTO PARNAIBA|-9.1027|-45.9303
MA|AMAPA DO MARANHAO|-1.6752|-46.0024
MA|AMARANTE DO MARANHAO|-5.5691|-46.7473
MA|ANAJATUBA|-3.2627|-44.6126
MA|ANAPURUS|-3.6758|-43.1014
MA|APICUM ACU|-1.4586|-45.0864
MA|ARAGUANA|-2.9464|-45.6589
MA|ARAIOSES|-2.8909|-41.9050
MA|ARAME|-4.8835|-46.0032
MA|ARARI|-3.4521|-44.7665
MA|AXIXA|-2.8394|-44.0620
MA|BACABAL|-4.2245|-44.7832
MA|BACABEIRA|-2.9645|-44.3164
MA|BACURITUBA|-2.7100|-44.7329
MA|BACURI|-1.6965|-45.1328
MA|BALSAS|-7.5321|-46.0372
MA|BARAO DE GRAJAU|-6.7446|-43.0261
MA|BARRA DO CORDA|-5.4968|-45.2485
MA|BARREIRINHAS|-2.7586|-42.8232
MA|BELA VISTA DO MARANHAO|-3.7262|-45.3075
MA|BELAGUA|-3.1549|-43.5122
MA|BENEDITO LEITE|-7.2104|-44.5577
MA|BEQUIMAO|-2.4416|-44.7842
MA|BERNARDO DO MEARIM|-4.6267|-44.7608
MA|BOA VISTA DO GURUPI|-1.7761|-46.3002
MA|BOM JARDIM|-3.5413|-45.6060
MA|BOM JESUS DAS SELVAS|-4.4764|-46.8641
MA|BOM LUGAR|-4.3731|-45.0326
MA|BREJO DE AREIA|-4.3340|-45.5810
MA|BREJO|-3.6780|-42.7527
MA|BURITI BRAVO|-5.8324|-43.8353
MA|BURITICUPU|-4.3238|-46.4409
MA|BURITIRANA|-5.5982|-47.0131
MA|BURITI|-3.9417|-42.9179
MA|CACHOEIRA GRANDE|-2.9307|-44.0528
MA|CAJAPIO|-2.8733|-44.6741
MA|CAJARI|-3.3274|-45.0145
MA|CAMPESTRE DO MARANHAO|-6.1707|-47.3625
MA|CANDIDO MENDES|-1.4326|-45.7161
MA|CANTANHEDE|-3.6376|-44.3830
MA|CAPINZAL DO NORTE|-4.7236|-44.3280
MA|CAROLINA|-7.3358|-47.4634
MA|CARUTAPERA|-1.1970|-46.0085
MA|CAXIAS|-4.8651|-43.3617
MA|CEDRAL|-2.0003|-44.5281
MA|CENTRAL DO MARANHAO|-2.1983|-44.8254
MA|CENTRO DO GUILHERME|-2.4489|-46.0345
MA|CENTRO NOVO DO MARANHAO|-2.1270|-46.1228
MA|CHAPADINHA|-3.7388|-43.3538
MA|CIDELANDIA|-5.1746|-47.7781
MA|CODO|-4.4556|-43.8924
MA|COELHO NETO|-4.2524|-43.0108
MA|COLINAS|-6.0320|-44.2543
MA|CONCEICAO DO LAGO ACU|-3.8514|-44.8895
MA|COROATA|-4.1344|-44.1244
MA|CURURUPU|-1.8148|-44.8644
MA|DAVINOPOLIS|-5.5464|-47.4217
MA|DOM PEDRO|-5.0352|-44.4409
MA|DUQUE BACELAR|-4.1500|-42.9477
MA|ESPERANTINOPOLIS|-4.8794|-44.6926
MA|ESTREITO|-6.5608|-47.4431
MA|FEIRA NOVA DO MARANHAO|-6.9651|-46.6786
MA|FERNANDO FALCAO|-6.1621|-44.8979
MA|FORMOSA DA SERRA NEGRA|-6.4402|-46.1916
MA|FORTALEZA DOS NOGUEIRAS|-6.9598|-46.1749
MA|FORTUNA|-5.7279|-44.1565
MA|GODOFREDO VIANA|-1.4026|-45.7795
MA|GONCALVES DIAS|-5.1475|-44.3013
MA|GOVERNADOR ARCHER|-5.0208|-44.2754
MA|GOVERNADOR EDISON LOBAO|-5.7497|-47.3646
MA|GOVERNADOR EUGENIO BARROS|-5.3190|-44.2469
MA|GOVERNADOR LUIZ ROCHA|-5.4783|-44.0774
MA|GOVERNADOR NEWTON BELLO|-3.4324|-45.6619
MA|GOVERNADOR NUNES FREIRE|-2.1290|-45.8777
MA|GRACA ARANHA|-5.4055|-44.3358
MA|GRAJAU|-5.8137|-46.1462
MA|GUIMARAES|-2.1275|-44.6020
MA|HUMBERTO DE CAMPOS|-2.5983|-43.4649
MA|ICATU|-2.7721|-44.0501
MA|IGARAPE DO MEIO|-3.6577|-45.2114
MA|IGARAPE GRANDE|-4.6625|-44.8558
MA|IMPERATRIZ|-5.5185|-47.4777
MA|ITAIPAVA DO GRAJAU|-5.1425|-45.7877
MA|ITAPECURU MIRIM|-3.4020|-44.3508
MA|ITINGA DO MARANHAO|-4.4529|-47.5235
MA|JATOBA|-5.8228|-44.2153
MA|JENIPAPO DOS VIEIRAS|-5.3624|-45.6356
MA|JOAO LISBOA|-5.4436|-47.4064
MA|JOSELANDIA|-4.9861|-44.6958
MA|JUNCO DO MARANHAO|-1.8389|-46.0900
MA|LAGO DA PEDRA|-4.5697|-45.1319
MA|LAGO DO JUNCO|-4.6090|-45.0490
MA|LAGO DOS RODRIGUES|-4.6117|-44.9798
MA|LAGO VERDE|-3.9466|-44.8260
MA|LAGOA DO MATO|-6.0502|-43.5333
MA|LAGOA GRANDE DO MARANHAO|-4.9889|-45.3816
MA|LAJEADO NOVO|-6.1854|-47.0293
MA|LIMA CAMPOS|-4.5184|-44.4646
MA|LORETO|-7.0811|-45.1451
MA|LUIS DOMINGUES|-1.2749|-45.8670
MA|MAGALHAES DE ALMEIDA|-3.3923|-42.2117
MA|MARACACUME|-2.0492|-45.9587
MA|MARAJA DO SENA|-4.6281|-45.4531
MA|MARANHAOZINHO|-2.2408|-45.8507
MA|MATA ROMA|-3.6204|-43.1112
MA|MATINHA|-3.0985|-45.0350
MA|MATOES DO NORTE|-3.6244|-44.5468
MA|MATOES|-5.5136|-43.2018
MA|MILAGRES DO MARANHAO|-3.5744|-42.6131
MA|MIRADOR|-6.3745|-44.3683
MA|MIRANDA DO NORTE|-3.5631|-44.5814
MA|MIRINZAL|-2.0709|-44.7787
MA|MONCAO|-3.4813|-45.2496
MA|MONTES ALTOS|-5.8307|-47.0673
MA|MORROS|-2.8538|-44.0357
MA|NINA RODRIGUES|-3.4679|-43.9134
MA|NOVA COLINAS|-7.1226|-46.2607
MA|NOVA IORQUE|-6.7305|-44.0471
MA|NOVA OLINDA DO MARANHAO|-2.8423|-45.6953
MA|OLHO D AGUA DAS CUNHAS|-4.1342|-45.1163
MA|OLINDA NOVA DO MARANHAO|-2.9929|-44.9897
MA|PACO DO LUMIAR|-2.5166|-44.1019
MA|PALMEIRANDIA|-2.6443|-44.8933
MA|PARAIBANO|-6.4264|-43.9792
MA|PARNARAMA|-5.6737|-43.1011
MA|PASSAGEM FRANCA|-6.1775|-43.7755
MA|PASTOS BONS|-6.6030|-44.0745
MA|PAULINO NEVES|-2.7209|-42.5258
MA|PAULO RAMOS|-4.4448|-45.2398
MA|PEDREIRAS|-4.5648|-44.6006
MA|PEDRO DO ROSARIO|-2.9727|-45.3493
MA|PENALVA|-3.2767|-45.1768
MA|PERI MIRIM|-2.5768|-44.8504
MA|PERITORO|-4.3746|-44.3369
MA|PINDARE MIRIM|-3.6098|-45.3420
MA|PINHEIRO|-2.5222|-45.0788
MA|PIO XII|-3.8931|-45.1759
MA|PIRAPEMAS|-3.7204|-44.2216
MA|POCAO DE PEDRAS|-4.7463|-44.9432
MA|PORTO FRANCO|-6.3415|-47.3962
MA|PORTO RICO DO MARANHAO|-1.8593|-44.5842
MA|PRESIDENTE DUTRA|-5.2898|-44.4950
MA|PRESIDENTE JUSCELINO|-2.9187|-44.0715
MA|PRESIDENTE MEDICI|-2.3899|-45.8200
MA|PRESIDENTE SARNEY|-2.5880|-45.3595
MA|PRESIDENTE VARGAS|-3.4079|-44.0234
MA|PRIMEIRA CRUZ|-2.5057|-43.4232
MA|RAPOSA|-2.4254|-44.0973
MA|RIACHAO|-7.3582|-46.6225
MA|RIBAMAR FIQUENE|-5.9307|-47.3888
MA|ROSARIO|-2.9344|-44.2531
MA|SAMBAIBA|-7.1345|-45.3515
MA|SANTA FILOMENA DO MARANHAO|-5.4967|-44.5638
MA|SANTA HELENA|-2.2443|-45.2900
MA|SANTA INES|-3.6511|-45.3774
MA|SANTA LUZIA DO PARUA|-2.5112|-45.7801
MA|SANTA LUZIA|-4.0687|-45.6900
MA|SANTA QUITERIA DO MARANHAO|-3.4931|-42.5688
MA|SANTA RITA|-3.1424|-44.3211
MA|SANTANA DO MARANHAO|-3.1090|-42.4064
MA|SANTO AMARO DO MARANHAO|-2.5007|-43.2380
MA|SANTO ANTONIO DOS LOPES|-4.8661|-44.3653
MA|SAO BENEDITO DO RIO PRETO|-3.3352|-43.5287
MA|SAO BENTO|-2.6978|-44.8289
MA|SAO BERNARDO|-3.3722|-42.4191
MA|SAO DOMINGOS DO AZEITAO|-6.8147|-44.6509
MA|SAO DOMINGOS DO MARANHAO|-5.5809|-44.3822
MA|SAO FELIX DE BALSAS|-7.0754|-44.8092
MA|SAO FRANCISCO DO BREJAO|-5.1258|-47.3890
MA|SAO FRANCISCO DO MARANHAO|-6.2516|-42.8668
MA|SAO JOAO BATISTA|-2.9540|-44.7953
MA|SAO JOAO DO CARU|-3.5503|-46.2507
MA|SAO JOAO DO PARAISO|-6.4563|-47.0594
MA|SAO JOAO DO SOTER|-5.1082|-43.8163
MA|SAO JOAO DOS PATOS|-6.4934|-43.7036
MA|SAO JOSE DE RIBAMAR|-2.5470|-44.0597
MA|SAO JOSE DOS BASILIOS|-5.0549|-44.5809
MA|SAO LUIS GONZAGA DO MARANHAO|-4.3854|-44.6654
MA|SAO LUIS|-2.5387|-44.2825
MA|SAO MATEUS DO MARANHAO|-4.0374|-44.4707
MA|SAO PEDRO DA AGUA BRANCA|-5.0847|-48.4291
MA|SAO PEDRO DOS CRENTES|-6.8239|-46.5319
MA|SAO RAIMUNDO DAS MANGABEIRAS|-7.0218|-45.4809
MA|SAO RAIMUNDO DO DOCA BEZERRA|-5.1105|-45.0696
MA|SAO ROBERTO|-5.0231|-45.0010
MA|SAO VICENTE FERRER|-2.8949|-44.8681
MA|SATUBINHA|-4.0491|-45.2457
MA|SENADOR ALEXANDRE COSTA|-5.2510|-44.0533
MA|SENADOR LA ROCQUE|-5.4461|-47.2959
MA|SERRANO DO MARANHAO|-1.8523|-45.1207
MA|SITIO NOVO|-5.8760|-46.7033
MA|SUCUPIRA DO NORTE|-6.4784|-44.1919
MA|SUCUPIRA DO RIACHAO|-6.4086|-43.5455
MA|TASSO FRAGOSO|-8.4662|-45.7536
MA|TIMBIRAS|-4.2560|-43.9320
MA|TIMON|-5.0977|-42.8329
MA|TRIZIDELA DO VALE|-4.5380|-44.6280
MA|TUFILANDIA|-3.6736|-45.6238
MA|TUNTUM|-5.2548|-44.6444
MA|TURIACU|-1.6589|-45.3798
MA|TURILANDIA|-2.2164|-45.3044
MA|TUTOIA|-2.7614|-42.2755
MA|URBANO SANTOS|-3.2064|-43.3878
MA|VARGEM GRANDE|-3.5364|-43.9170
MA|VIANA|-3.2045|-44.9912
MA|VILA NOVA DOS MARTIRIOS|-5.1889|-48.1336
MA|VITORIA DO MEARIM|-3.4512|-44.8643
MA|VITORINO FREIRE|-4.2818|-45.2505
MA|ZE DOCA|-3.2701|-45.6553
MT|ACORIZAL|-15.1940|-56.3632
MT|AGUA BOA|-14.0510|-52.1601
MT|ALTA FLORESTA|-9.8667|-56.0867
MT|ALTO ARAGUAIA|-17.3153|-53.2181
MT|ALTO BOA VISTA|-11.6732|-51.3883
MT|ALTO GARCAS|-16.9462|-53.5272
MT|ALTO PARAGUAI|-14.5137|-56.4776
MT|ALTO TAQUARI|-17.8241|-53.2792
MT|APIACAS|-9.5398|-57.4587
MT|ARAGUAIANA|-15.7291|-51.8341
MT|ARAGUAINHA|-16.8570|-53.0318
MT|ARAPUTANGA|-15.4641|-58.3425
MT|ARENAPOLIS|-14.4472|-56.8437
MT|ARIPUANA|-10.1723|-59.4568
MT|BARAO DE MELGACO|-16.2067|-55.9623
MT|BARRA DO BUGRES|-15.0702|-57.1878
MT|BARRA DO GARCAS|-15.8804|-52.2640
MT|BOA ESPERANCA DO NORTE|-13.5067|-55.1486
MT|BOM JESUS DO ARAGUAIA|-12.1706|-51.5032
MT|BRASNORTE|-12.1474|-57.9833
MT|CACERES|-16.0764|-57.6818
MT|CAMPINAPOLIS|-14.5162|-52.8930
MT|CAMPO NOVO DO PARECIS|-13.6587|-57.8907
MT|CAMPO VERDE|-15.5450|-55.1626
MT|CAMPOS DE JULIO|-13.7242|-59.2858
MT|CANABRAVA DO NORTE|-11.0556|-51.8209
MT|CANARANA|-13.5515|-52.2705
MT|CARLINDA|-9.9491|-55.8417
MT|CASTANHEIRA|-11.1251|-58.6081
MT|CHAPADA DOS GUIMARAES|-15.4643|-55.7499
MT|CLAUDIA|-11.5075|-54.8835
MT|COCALINHO|-14.3903|-51.0001
MT|COLIDER|-10.8135|-55.4610
MT|COLNIZA|-9.4612|-59.2252
MT|COMODORO|-13.6614|-59.7848
MT|CONFRESA|-10.6437|-51.5699
MT|CONQUISTA D OESTE|-14.5381|-59.5444
MT|COTRIGUACU|-9.8566|-58.4192
MT|CUIABA|-15.6010|-56.0974
MT|CURVELANDIA|-15.6084|-57.9133
MT|DENISE|-14.7324|-57.0583
MT|DIAMANTINO|-14.4037|-56.4366
MT|DOM AQUINO|-15.8099|-54.9223
MT|FELIZ NATAL|-12.3850|-54.9227
MT|FIGUEIROPOLIS D OESTE|-15.4439|-58.7391
MT|GAUCHA DO NORTE|-13.2443|-53.0809
MT|GENERAL CARNEIRO|-15.7094|-52.7574
MT|GLORIA D OESTE|-15.7680|-58.3108
MT|GUARANTA DO NORTE|-9.9622|-54.9121
MT|GUIRATINGA|-16.3460|-53.7575
MT|INDIAVAI|-15.4921|-58.5802
MT|IPIRANGA DO NORTE|-12.2408|-56.1531
MT|ITANHANGA|-12.2259|-56.6463
MT|ITAUBA|-11.0614|-55.2766
MT|ITIQUIRA|-17.2147|-54.1422
MT|JACIARA|-15.9548|-54.9733
MT|JANGADA|-15.2350|-56.4917
MT|JAURU|-15.3342|-58.8723
MT|JUARA|-11.2639|-57.5244
MT|JUINA|-11.3728|-58.7483
MT|JURUENA|-10.3178|-58.3592
MT|JUSCIMEIRA|-16.0633|-54.8859
MT|LAMBARI D OESTE|-15.3188|-58.0046
MT|LUCAS DO RIO VERDE|-13.0588|-55.9042
MT|LUCIARA|-11.2219|-50.6676
MT|MARCELANDIA|-11.0463|-54.4377
MT|MATUPA|-10.1821|-54.9467
MT|MIRASSOL D OESTE|-15.6759|-58.0951
MT|NOBRES|-14.7192|-56.3284
MT|NORTELANDIA|-14.4540|-56.7945
MT|NOSSA SENHORA DO LIVRAMENTO|-15.7720|-56.3432
MT|NOVA BANDEIRANTES|-9.8498|-57.8139
MT|NOVA BRASILANDIA|-14.9612|-54.9685
MT|NOVA CANAA DO NORTE|-10.5580|-55.9530
MT|NOVA GUARITA|-10.3120|-55.4061
MT|NOVA LACERDA|-14.4727|-59.6001
MT|NOVA MARILANDIA|-14.3568|-56.9696
MT|NOVA MARINGA|-13.0136|-57.0908
MT|NOVA MONTE VERDE|-10.0000|-57.5261
MT|NOVA MUTUM|-13.8374|-56.0743
MT|NOVA NAZARE|-13.9486|-51.8002
MT|NOVA OLIMPIA|-14.7889|-57.2886
MT|NOVA SANTA HELENA|-10.8651|-55.1872
MT|NOVA UBIRATA|-12.9834|-55.2556
MT|NOVA XAVANTINA|-14.6771|-52.3502
MT|NOVO HORIZONTE DO NORTE|-11.4089|-57.3488
MT|NOVO MUNDO|-9.9562|-55.2029
MT|NOVO SANTO ANTONIO|-12.2875|-50.9686
MT|NOVO SAO JOAQUIM|-14.9054|-53.0194
MT|PARANAITA|-9.6584|-56.4786
MT|PARANATINGA|-14.4265|-54.0524
MT|PEDRA PRETA|-16.6245|-54.4722
MT|PEIXOTO DE AZEVEDO|-10.2262|-54.9794
MT|PLANALTO DA SERRA|-14.6518|-54.7819
MT|POCONE|-16.2660|-56.6261
MT|PONTAL DO ARAGUAIA|-15.9274|-52.3273
MT|PONTE BRANCA|-16.7584|-52.8369
MT|PONTES E LACERDA|-15.2219|-59.3435
MT|PORTO ALEGRE DO NORTE|-10.8761|-51.6357
MT|PORTO DOS GAUCHOS|-11.5330|-57.4132
MT|PORTO ESPERIDIAO|-15.8570|-58.4619
MT|PORTO ESTRELA|-15.3235|-57.2204
MT|POXOREU|-15.8299|-54.4208
MT|PRIMAVERA DO LESTE|-15.5440|-54.2811
MT|QUERENCIA|-12.6093|-52.1821
MT|RESERVA DO CABACAL|-15.0743|-58.4585
MT|RIBEIRAO CASCALHEIRA|-12.9367|-51.8244
MT|RIBEIRAOZINHO|-16.4856|-52.6924
MT|RIO BRANCO|-15.2483|-58.1259
MT|RONDOLANDIA|-10.8376|-61.4697
MT|RONDONOPOLIS|-16.4673|-54.6372
MT|ROSARIO OESTE|-14.8259|-56.4236
MT|SALTO DO CEU|-15.1303|-58.1317
MT|SANTA CARMEM|-11.9125|-55.2263
MT|SANTA CRUZ DO XINGU|-10.1532|-52.3953
MT|SANTA RITA DO TRIVELATO|-13.8146|-55.2706
MT|SANTA TEREZINHA|-10.4704|-50.5140
MT|SANTO AFONSO|-14.4945|-57.0091
MT|SANTO ANTONIO DO LESTE|-14.8050|-53.6075
MT|SANTO ANTONIO DO LEVERGER|-15.8632|-56.0788
MT|SAO FELIX DO ARAGUAIA|-11.6150|-50.6706
MT|SAO JOSE DO POVO|-16.4549|-54.2487
MT|SAO JOSE DO RIO CLARO|-13.4398|-56.7218
MT|SAO JOSE DO XINGU|-10.7982|-52.7486
MT|SAO JOSE DOS QUATRO MARCOS|-15.6276|-58.1772
MT|SAO PEDRO DA CIPA|-16.0109|-54.9176
MT|SAPEZAL|-12.9892|-58.7645
MT|SERRA NOVA DOURADA|-12.0896|-51.4025
MT|SINOP|-11.8604|-55.5091
MT|SORRISO|-12.5425|-55.7211
MT|TABAPORA|-11.3007|-56.8312
MT|TANGARA DA SERRA|-14.6229|-57.4933
MT|TAPURAH|-12.6950|-56.5178
MT|TERRA NOVA DO NORTE|-10.5170|-55.2310
MT|TESOURO|-16.0809|-53.5590
MT|TORIXOREU|-16.2006|-52.5571
MT|UNIAO DO SUL|-11.5308|-54.3616
MT|VALE DE SAO DOMINGOS|-15.2860|-59.0683
MT|VARZEA GRANDE|-15.6458|-56.1322
MT|VERA|-12.3017|-55.3045
MT|VILA BELA DA SANTISSIMA TRINDADE|-15.0068|-59.9504
MT|VILA RICA|-10.0137|-51.1186
PA|ABAETETUBA|-1.7218|-48.8788
PA|ABEL FIGUEIREDO|-4.9533|-48.3933
PA|ACARA|-1.9538|-48.1985
PA|AFUA|-0.1549|-50.3861
PA|AGUA AZUL DO NORTE|-6.7905|-50.4791
PA|ALENQUER|-1.9462|-54.7384
PA|ALMEIRIM|-1.5290|-52.5788
PA|ALTAMIRA|-3.2041|-52.2100
PA|ANAJAS|-0.9968|-49.9354
PA|ANANINDEUA|-1.3639|-48.3743
PA|ANAPU|-3.4699|-51.2003
PA|AUGUSTO CORREA|-1.0511|-46.6147
PA|AURORA DO PARA|-2.1490|-47.5677
PA|AVEIRO|-3.6084|-55.3199
PA|BAGRE|-1.9006|-50.1987
PA|BAIAO|-2.7902|-49.6694
PA|BANNACH|-7.3478|-50.3959
PA|BARCARENA|-1.5119|-48.6195
PA|BELEM|-1.4554|-48.4898
PA|BELTERRA|-2.6361|-54.9374
PA|BENEVIDES|-1.3618|-48.2434
PA|BOM JESUS DO TOCANTINS|-5.0424|-48.6047
PA|BONITO|-1.3675|-47.3066
PA|BRAGANCA|-1.0613|-46.7826
PA|BRASIL NOVO|-3.2979|-52.5340
PA|BREJO GRANDE DO ARAGUAIA|-5.6982|-48.4103
PA|BREU BRANCO|-3.7719|-49.5735
PA|BREVES|-1.6804|-50.4791
PA|BUJARU|-1.5176|-48.0381
PA|CACHOEIRA DO ARARI|-1.0123|-48.9503
PA|CACHOEIRA DO PIRIA|-1.7597|-46.5459
PA|CAMETA|-2.2429|-49.4979
PA|CANAA DOS CARAJAS|-6.4966|-49.8776
PA|CAPANEMA|-1.2053|-47.1778
PA|CAPITAO POCO|-1.7478|-47.0629
PA|CASTANHAL|-1.2980|-47.9167
PA|CHAVES|-0.1642|-49.9870
PA|COLARES|-0.9364|-48.2803
PA|CONCEICAO DO ARAGUAIA|-8.2614|-49.2689
PA|CONCORDIA DO PARA|-1.9924|-47.9422
PA|CUMARU DO NORTE|-7.8110|-50.7698
PA|CURIONOPOLIS|-6.0996|-49.6068
PA|CURRALINHO|-1.8118|-49.7952
PA|CURUA|-1.8878|-55.1168
PA|CURUCA|-0.7332|-47.8515
PA|DOM ELISEU|-4.1994|-47.8245
PA|ELDORADO DO CARAJAS|-6.1039|-49.3553
PA|FARO|-2.1681|-56.7405
PA|FLORESTA DO ARAGUAIA|-7.5534|-49.7125
PA|GARRAFAO DO NORTE|-1.9299|-47.0505
PA|GOIANESIA DO PARA|-3.8434|-49.0974
PA|GURUPA|-1.4141|-51.6338
PA|IGARAPE ACU|-1.1254|-47.6260
PA|IGARAPE MIRI|-1.9753|-48.9575
PA|INHANGAPI|-1.4349|-47.9114
PA|IPIXUNA DO PARA|-2.5599|-47.5059
PA|IRITUIA|-1.7698|-47.4460
PA|ITAITUBA|-4.2667|-55.9926
PA|ITUPIRANGA|-5.1327|-49.3358
PA|JACAREACANGA|-6.2147|-57.7544
PA|JACUNDA|-4.4462|-49.1153
PA|JURUTI|-2.1635|-56.0889
PA|LIMOEIRO DO AJURU|-1.8985|-49.3903
PA|MAE DO RIO|-2.0568|-47.5601
PA|MAGALHAES BARATA|-0.8034|-47.6014
PA|MARABA|-5.3807|-49.1327
PA|MARACANA|-0.7789|-47.4520
PA|MARAPANIM|-0.7147|-47.7034
PA|MARITUBA|-1.3600|-48.3421
PA|MEDICILANDIA|-3.4464|-52.8875
PA|MELGACO|-1.8032|-50.7149
PA|MOCAJUBA|-2.5831|-49.5042
PA|MOJUI DOS CAMPOS|-2.6822|-54.6425
PA|MOJU|-1.8899|-48.7668
PA|MONTE ALEGRE|-1.9977|-54.0724
PA|MUANA|-1.5394|-49.2224
PA|NOVA ESPERANCA DO PIRIA|-2.2669|-46.9731
PA|NOVA IPIXUNA|-4.9162|-49.0822
PA|NOVA TIMBOTEUA|-1.2087|-47.3921
PA|NOVO PROGRESSO|-7.1435|-55.3786
PA|NOVO REPARTIMENTO|-4.2475|-49.9499
PA|OBIDOS|-1.9011|-55.5208
PA|OEIRAS DO PARA|-2.0036|-49.8628
PA|ORIXIMINA|-1.7599|-55.8579
PA|OUREM|-1.5417|-47.1126
PA|OURILANDIA DO NORTE|-6.7529|-51.0858
PA|PACAJA|-3.8354|-50.6399
PA|PALESTINA DO PARA|-5.7403|-48.3181
PA|PARAGOMINAS|-3.0021|-47.3527
PA|PARAUAPEBAS|-6.0678|-49.9037
PA|PAU D ARCO|-1.5977|-46.9268
PA|PEIXE BOI|-1.1938|-47.3240
PA|PICARRA|-6.4378|-48.8716
PA|PLACAS|-3.8681|-54.2124
PA|PONTA DE PEDRAS|-1.3959|-48.8661
PA|PORTEL|-1.9364|-50.8194
PA|PORTO DE MOZ|-1.7469|-52.2361
PA|PRAINHA|-1.7980|-53.4779
PA|PRIMAVERA|-0.9454|-47.1253
PA|QUATIPURU|-0.8996|-47.0134
PA|REDENCAO|-8.0253|-50.0317
PA|RIO MARIA|-7.3124|-50.0379
PA|RONDON DO PARA|-4.7779|-48.0670
PA|RUROPOLIS|-4.1003|-54.9092
PA|SALINOPOLIS|-0.6308|-47.3465
PA|SALVATERRA|-0.7584|-48.5139
PA|SANTA BARBARA DO PARA|-1.1922|-48.2380
PA|SANTA CRUZ DO ARARI|-0.6610|-49.1771
PA|SANTA IZABEL DO PARA|-1.2969|-48.1606
PA|SANTA LUZIA DO PARA|-1.5215|-46.9008
PA|SANTA MARIA DAS BARREIRAS|-8.8578|-49.7215
PA|SANTA MARIA DO PARA|-1.3539|-47.5712
PA|SANTANA DO ARAGUAIA|-9.3281|-50.3500
PA|SANTAREM NOVO|-0.9310|-47.3855
PA|SANTAREM|-2.4385|-54.6996
PA|SANTO ANTONIO DO TAUA|-1.1522|-48.1314
PA|SAO CAETANO DE ODIVELAS|-0.7473|-48.0246
PA|SAO DOMINGOS DO ARAGUAIA|-5.5373|-48.7366
PA|SAO DOMINGOS DO CAPIM|-1.6877|-47.7665
PA|SAO FELIX DO XINGU|-6.6425|-51.9904
PA|SAO FRANCISCO DO PARA|-1.1696|-47.7917
PA|SAO GERALDO DO ARAGUAIA|-6.3947|-48.5592
PA|SAO JOAO DA PONTA|-0.8579|-47.9180
PA|SAO JOAO DE PIRABAS|-0.7802|-47.1810
PA|SAO JOAO DO ARAGUAIA|-5.3633|-48.7926
PA|SAO MIGUEL DO GUAMA|-1.6131|-47.4784
PA|SAO SEBASTIAO DA BOA VISTA|-1.7160|-49.5249
PA|SAPUCAIA|-6.9402|-49.6834
PA|SENADOR JOSE PORFIRIO|-4.3124|-51.5764
PA|SOURE|-0.7303|-48.5015
PA|TAILANDIA|-2.9458|-48.9489
PA|TERRA ALTA|-1.0296|-47.9004
PA|TERRA SANTA|-2.1044|-56.4877
PA|TOME ACU|-2.4130|-48.1415
PA|TRACUATEUA|-1.0765|-46.9031
PA|TRAIRAO|-4.5735|-55.9429
PA|TUCUMA|-6.7469|-51.1626
PA|TUCURUI|-3.7657|-49.6773
PA|ULIANOPOLIS|-3.7501|-47.4892
PA|URUARA|-3.7152|-53.7396
PA|VIGIA|-0.8612|-48.1386
PA|VISEU|-1.1912|-46.1399
PA|VITORIA DO XINGU|-2.8792|-52.0088
PA|XINGUARA|-7.0983|-49.9437
PR|LONDRINA|-23.3040|-51.1691
RJ|DUQUE DE CAXIAS|-22.7858|-43.3049
RJ|RIO DE JANEIRO|-22.9129|-43.2003
RO|JARU|-10.4318|-62.4788
RO|OURO PRETO DO OESTE|-10.7167|-62.2565
RO|PIMENTA BUENO|-11.6720|-61.1980
RO|PORTO VELHO|-8.7608|-63.8999
RR|ALTO ALEGRE|2.9886|-61.3072
RR|AMAJARI|3.6457|-61.3692
RR|BOA VISTA|2.8238|-60.6753
RR|BONFIM|3.3616|-59.8333
RR|CANTA|2.6099|-60.6058
RR|CARACARAI|1.8277|-61.1304
RR|CAROEBE|0.8842|-59.6959
RR|IRACEMA|2.1831|-61.0415
RR|MUCAJAI|2.4400|-60.9096
RR|NORMANDIA|3.8853|-59.6204
RR|PACARAIMA|4.4799|-61.1477
RR|RORAINOPOLIS|0.9400|-60.4389
RR|SAO JOAO DA BALIZA|0.9517|-59.9133
RR|SAO LUIZ|1.0102|-60.0419
RR|UIRAMUTA|4.6031|-60.1815
SC|SAO JOSE|-27.6136|-48.6366
SE|SAO CRISTOVAO|-11.0084|-37.2044
SP|INDAIATUBA|-23.0816|-47.2101
SP|JAGUARIUNA|-22.7037|-46.9851
SP|SANTOS|-23.9535|-46.3350
SP|SAO PAULO|-23.5329|-46.6395
SP|VINHEDO|-23.0302|-46.9833
"""

# ==========================================================================
# Manaus: o bairro e a zona administrativa dele (Prefeitura de Manaus)
# ==========================================================================
_BAIRROS_MANAUS = {
    "CENTRO-SUL": ("ADRIANOPOLIS ALEIXO CACHOEIRINHA CENTRO CHAPADA "
                   "NOSSA SENHORA DAS GRACAS|PARQUE 10 DE NOVEMBRO|"
                   "PETROPOLIS|PRACA 14 DE JANEIRO|SAO GERALDO|SAO LAZARO"),
    "SUL": ("BETANIA|COLONIA OLIVEIRA MACHADO|COROADO|CRESPO|"
            "DISTRITO INDUSTRIAL I|EDUCANDOS|JAPIIM|MAUAZINHO|"
            "MORRO DA LIBERDADE|PURAQUEQUARA|RAIZ|SANTA LUZIA|"
            "SAO FRANCISCO|VILA BURITI"),
    "LESTE": ("ARMANDO MENDES|COLONIA ANTONIO ALEIXO|DISTRITO INDUSTRIAL II|"
              "GILBERTO MESTRINHO|JORGE TEIXEIRA|SAO JOSE OPERARIO|"
              "TANCREDO NEVES|ZUMBI DOS PALMARES"),
    "NORTE": ("CIDADE NOVA|CIDADE DE DEUS|COLONIA SANTO ANTONIO|"
              "LIRIO DO VALE|MANOA|MONTE DAS OLIVEIRAS|NOVA CIDADE|"
              "NOVO ALEIXO|NOVO ISRAEL|SANTA ETELVINA|TERRA NOVA|"
              "VIVER MELHOR|LAGO AZUL"),
    "OESTE": ("ALVORADA|COMPENSA|DA PAZ|DOM PEDRO|GLORIA|NOVA ESPERANCA|"
              "PLANALTO|PONTA NEGRA|REDENCAO|SANTO AGOSTINHO|SANTO ANTONIO|"
              "SAO JORGE|SAO RAIMUNDO|TARUMA|TARUMA ACU|VILA DA PRATA|"
              "VILA NOVA"),
    "CENTRO-OESTE": "FLORES|PARQUE DAS LARANJEIRAS",
}

# apelidos que a semelhanca de texto nao resolve sozinha, ou resolve errado
_APELIDOS_MANAUS = {
    "SAO JOSE": "LESTE",              # Sao Jose Operario, e nao Sao Jorge
    "SAO JOSE 2": "LESTE",
    "ZUMBI": "LESTE",
    "BAIRRO NOVO": "LESTE",
    "PARQUE 10": "CENTRO-SUL",
    "PARQUE DEZ": "CENTRO-SUL",
    "PRACA 14": "CENTRO-SUL",
    "DISTRITO AGROPECUARIO DA SUFRAMA": "NORTE",
    "ZONA RURAL": "",                 # nao e bairro: fica no fim da lista
}

# a ordem em que o vendedor anda pelas zonas de Manaus: sai do centro,
# desce para o sul, sobe pelo leste ate o norte e volta pelo oeste
ORDEM_ZONAS_MANAUS = ["CENTRO-SUL", "SUL", "LESTE", "NORTE",
                      "CENTRO-OESTE", "OESTE"]


@lru_cache(maxsize=20000)
def _normalizar_texto(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto)
    t = t.encode("ascii", "ignore").decode()
    t = t.replace("-", " ").replace("'", " ")
    return re.sub(r"\s+", " ", t).strip().upper()


def normalizar(texto) -> str:
    """
    Sem acento, sem hifen, em maiuscula e sem espaco sobrando.

    Guardado em cache: a ordenacao geografica chama isto dezenas de milhares
    de vezes por rota, sempre com os mesmos poucos milhares de nomes de
    cidade e de bairro. Sao sempre as mesmas respostas.
    """
    return _normalizar_texto(str(texto or ""))


def _montar_cidades():
    mapa = {}
    for linha in _CIDADES_TEXTO.strip().splitlines():
        uf, cidade, lat, lon = linha.split("|")
        mapa[(uf, cidade)] = (float(lat), float(lon))
    return mapa


def _montar_bairros():
    mapa = {}
    for zona, nomes in _BAIRROS_MANAUS.items():
        for nome in nomes.replace("ADRIANOPOLIS ALEIXO CACHOEIRINHA CENTRO "
                                  "CHAPADA ", "ADRIANOPOLIS|ALEIXO|"
                                  "CACHOEIRINHA|CENTRO|CHAPADA|").split("|"):
            if nome.strip():
                mapa[normalizar(nome)] = zona
    mapa.update({normalizar(k): v for k, v in _APELIDOS_MANAUS.items()})
    return mapa


CIDADES = _montar_cidades()
BAIRROS_MANAUS = _montar_bairros()
_CHAVES_BAIRRO = sorted((b for b in BAIRROS_MANAUS if BAIRROS_MANAUS[b]),
                        key=len, reverse=True)
_cache_bairro = {}

# ==========================================================================
# A TABELA DE COORDENADAS DA BAP
# ==========================================================================
# A tabela embutida acima tem a coordenada do MUNICIPIO, e so em Manaus
# sabe dividir a cidade por zona. O arquivo
#
#     COORDENADAS_CIDADES_BAIRRO_BAP.xlsx
#
# vai muito alem: tem a coordenada de CADA BAIRRO de cada cidade, em duas
# abas - "Cidades" (UF, IBGE, cidade, latitude, longitude) e "Bairros"
# (UF, cidade, bairro, zona, latitude, longitude).
#
# Com ele a rota deixa de andar por uma lista fixa de zonas e passa a
# andar pela distancia de verdade: dentro da cidade, os bairros sao
# encadeados pelo VIZINHO MAIS PROXIMO, do mesmo jeito que as cidades ja
# eram. O arquivo fica na pasta do programa e e lido na abertura; sem ele
# tudo continua funcionando pela tabela embutida, so com menos precisao
# dentro da cidade.
ARQUIVO_COORDENADAS = "COORDENADAS_CIDADES_BAIRRO_BAP.xlsx"

# (UF, CIDADE, BAIRRO) -> (lat, lon)
BAIRROS_COORD: dict[tuple, tuple] = {}
# (UF, CIDADE, BAIRRO) -> a zona que o arquivo declara ("Zona Norte"...)
BAIRROS_ZONA: dict[tuple, str] = {}
_cache_ordem_bairro: dict[tuple, dict] = {}
_origem_das_coordenadas = "tabela embutida (IBGE)"


def origem_das_coordenadas() -> str:
    """De onde vieram as coordenadas que estao valendo agora."""
    return _origem_das_coordenadas


def _numero_coord(v):
    if isinstance(v, (int, float)):
        return float(v)
    texto = str(v or "").strip().replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return None


def caminho_das_coordenadas(caminho=None) -> Path:
    return Path(caminho) if caminho else (
        Path(__file__).resolve().parent / ARQUIVO_COORDENADAS)


def impressao_das_coordenadas(caminho=None) -> str:
    """
    Tamanho e data do arquivo de coordenadas. Entra na chave do cache da
    rota: trocou o arquivo, a rota e refeita - senao voce troca as
    coordenadas com o programa aberto e a rota continua a de antes.
    """
    try:
        st = caminho_das_coordenadas(caminho).stat()
        return f"{st.st_size}|{int(st.st_mtime)}"
    except OSError:
        return "sem-arquivo"


def recarregar_coordenadas(caminho=None) -> int:
    """
    Le o arquivo de coordenadas de novo e joga fora tudo o que foi
    memorizado a partir dele. Use depois de trocar a planilha com o
    programa aberto.
    """
    for f in (_bairro_conhecido, _ordem_do_bairro, _caminho_dos_bairros,
              nome_canonico):
        try:
            f.cache_clear()
        except AttributeError:
            pass
    BAIRROS_COORD.clear()
    BAIRROS_ZONA.clear()
    carregar_coordenadas(caminho)
    return len(BAIRROS_COORD)


def carregar_coordenadas(caminho=None) -> dict:
    """
    Le o COORDENADAS_CIDADES_BAIRRO_BAP.xlsx e passa a usa-lo.

    Devolve um resumo do que entrou. Nao levanta erro: se o arquivo nao
    existir, ou vier torto, a tabela embutida continua valendo - a rota
    nunca deixa de sair por causa disto.
    """
    global _origem_das_coordenadas
    from pathlib import Path
    if caminho is None:
        caminho = Path(__file__).resolve().parent / ARQUIVO_COORDENADAS
    caminho = Path(caminho)
    resumo = {"arquivo": caminho, "cidades": 0, "bairros": 0, "erro": ""}
    if not caminho.exists():
        resumo["erro"] = "arquivo nao encontrado"
        return resumo
    try:
        try:  # leitura rapida com cache (sem o arquivo: openpyxl)
            from xlsx_rapido import load_workbook  # noqa: F811,PLC0415
        except ImportError:
            from openpyxl import load_workbook  # noqa: PLC0415
        wb = load_workbook(caminho, read_only=True, data_only=True)
    except Exception as erro:                              # noqa: BLE001
        resumo["erro"] = str(erro)
        return resumo

    def coluna(cab, *nomes):
        limpo = [normalizar(c) for c in cab]
        for n in nomes:
            if normalizar(n) in limpo:
                return limpo.index(normalizar(n))
        return None

    try:
        if "Cidades" in wb.sheetnames:
            ws = wb["Cidades"]
            it = ws.iter_rows(values_only=True)
            cab = list(next(it))
            i_uf = coluna(cab, "UF")
            i_cid = coluna(cab, "Cidade", "Municipio")
            i_lat = coluna(cab, "Latitude", "Lat")
            i_lon = coluna(cab, "Longitude", "Lon")
            if None not in (i_uf, i_cid, i_lat, i_lon):
                for r in it:
                    lat, lon = _numero_coord(r[i_lat]), _numero_coord(r[i_lon])
                    uf, cidade = normalizar(r[i_uf]), normalizar(r[i_cid])
                    if uf and cidade and lat is not None and lon is not None:
                        CIDADES[(uf, cidade)] = (lat, lon)
                        resumo["cidades"] += 1

        if "Bairros" in wb.sheetnames:
            ws = wb["Bairros"]
            it = ws.iter_rows(values_only=True)
            cab = list(next(it))
            i_uf = coluna(cab, "UF")
            i_cid = coluna(cab, "Cidade", "Municipio")
            i_bai = coluna(cab, "Bairro")
            i_zon = coluna(cab, "Zona")
            i_lat = coluna(cab, "Latitude", "Lat")
            i_lon = coluna(cab, "Longitude", "Lon")
            if None not in (i_uf, i_cid, i_bai, i_lat, i_lon):
                for r in it:
                    lat, lon = _numero_coord(r[i_lat]), _numero_coord(r[i_lon])
                    uf = normalizar(r[i_uf])
                    cidade = normalizar(r[i_cid])
                    bairro = normalizar(r[i_bai])
                    if not (uf and cidade and bairro):
                        continue
                    if lat is None or lon is None:
                        continue
                    # (07/10) o arquivo tem bairro repetido: a linha que so
                    # traz o CENTRO DA CIDADE nao apaga a coordenada certa
                    # do bairro que ja veio antes
                    chave_b = (uf, cidade, bairro)
                    if (lat, lon) == CIDADES.get((uf, cidade)) and \
                            chave_b in BAIRROS_COORD and \
                            BAIRROS_COORD[chave_b] != (lat, lon):
                        continue
                    BAIRROS_COORD[chave_b] = (lat, lon)
                    if i_zon is not None:
                        BAIRROS_ZONA[(uf, cidade, bairro)] = normalizar(r[i_zon])
                    resumo["bairros"] += 1
    except Exception as erro:                              # noqa: BLE001
        resumo["erro"] = str(erro)
    finally:
        wb.close()

    _cache_ordem_bairro.clear()
    _ordem_do_bairro.cache_clear()
    _bairro_conhecido.cache_clear()
    if resumo["bairros"] or resumo["cidades"]:
        _origem_das_coordenadas = (
            f"{caminho.name}: {resumo['cidades']} cidade(s) e "
            f"{resumo['bairros']} bairro(s)")
    return resumo


@lru_cache(maxsize=40000)
def _bairro_conhecido(uf: str, cidade: str, bairro: str):
    """
    Acha a coordenada do bairro aceitando o nome escrito de outro jeito:
    igual, comecando igual, contido, e por ultimo o mais parecido. E a
    mesma tolerancia que ja existia para os bairros de Manaus.
    """
    chave = (uf, cidade, bairro)
    if chave in BAIRROS_COORD:
        return BAIRROS_COORD[chave]
    da_cidade = [b for (u, c, b) in BAIRROS_COORD if u == uf and c == cidade]
    if not da_cidade:
        return None
    for oficial in sorted(da_cidade, key=len, reverse=True):
        if bairro.startswith(oficial) or oficial.startswith(bairro):
            return BAIRROS_COORD[(uf, cidade, oficial)]
    for oficial in sorted(da_cidade, key=len, reverse=True):
        if len(oficial) >= 6 and oficial in bairro:
            return BAIRROS_COORD[(uf, cidade, oficial)]
    perto = difflib.get_close_matches(bairro, da_cidade, n=1, cutoff=0.82)
    return BAIRROS_COORD[(uf, cidade, perto[0])] if perto else None


def coordenada_do_bairro(uf, cidade, bairro):
    """A coordenada daquele bairro, ou None se o arquivo nao a tiver."""
    if not BAIRROS_COORD:
        return None
    return _bairro_conhecido(normalizar(uf), normalizar(cidade),
                             normalizar(bairro))


def _caminho_dos_bairros(uf: str, cidade: str) -> dict:
    """
    A ordem em que se anda pelos bairros DAQUELA cidade: encadeados pelo
    vizinho mais proximo, partindo do bairro mais perto do centro do
    municipio. Devolve {bairro normalizado -> posicao}.
    """
    chave = (uf, cidade)
    if chave in _cache_ordem_bairro:
        return _cache_ordem_bairro[chave]
    bairros = [b for (u, c, b) in BAIRROS_COORD if u == uf and c == cidade]
    ordem = {}
    if bairros:
        centro = CIDADES.get((uf, cidade))
        restantes = list(bairros)
        if centro:
            atual = min(restantes,
                        key=lambda b: distancia_km(centro,
                                                   BAIRROS_COORD[(uf, cidade, b)]))
        else:
            atual = sorted(restantes)[0]
        restantes.remove(atual)
        caminho = [atual]
        while restantes:
            aqui = BAIRROS_COORD[(uf, cidade, caminho[-1])]
            restantes.sort(
                key=lambda b: distancia_km(aqui, BAIRROS_COORD[(uf, cidade, b)]))
            caminho.append(restantes.pop(0))
        ordem = {b: i for i, b in enumerate(caminho)}
    _cache_ordem_bairro[chave] = ordem
    return ordem


def coordenada(uf, cidade):
    """A coordenada do municipio, ou None quando ele nao esta na tabela."""
    return CIDADES.get((normalizar(uf), normalizar(cidade)))


def distancia_km(a, b) -> float:
    """Distancia em linha reta entre duas coordenadas (formula de Haversine)."""
    if not a or not b:
        return float("inf")
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * 6371.0 * math.asin(min(1.0, math.sqrt(h)))


def distancia_cidades(uf1, cidade1, uf2, cidade2) -> float:
    return distancia_km(coordenada(uf1, cidade1), coordenada(uf2, cidade2))


def zona_do_bairro(cidade, bairro) -> str:
    """
    A zona administrativa do bairro em Manaus. Fora de Manaus devolve ""
    (nas outras cidades a rota anda pelo nome do bairro mesmo).
    Aceita o nome escrito errado: CACHOEIRNHA, COLINIA OLIVEIRA MACHADO,
    CIDADE NOVA 2, L RIO DO VALE...
    """
    if normalizar(cidade) != "MANAUS":
        return ""
    b = normalizar(bairro)
    if b in _cache_bairro:
        return _cache_bairro[b]
    zona = BAIRROS_MANAUS.get(b)
    if zona is None:
        for oficial in _CHAVES_BAIRRO:
            if b.startswith(oficial):
                zona = BAIRROS_MANAUS[oficial]
                break
    if zona is None:
        for oficial in _CHAVES_BAIRRO:
            if len(oficial) >= 6 and oficial in b:
                zona = BAIRROS_MANAUS[oficial]
                break
    if zona is None:
        perto = difflib.get_close_matches(b, _CHAVES_BAIRRO, n=1, cutoff=0.82)
        zona = BAIRROS_MANAUS[perto[0]] if perto else ""
    _cache_bairro[b] = zona
    return zona


@lru_cache(maxsize=40000)
def _ordem_do_bairro(uf: str, cidade: str, bairro: str) -> tuple:
    # 1) COM A TABELA DE COORDENADAS: a ordem e a distancia de verdade -
    #    os bairros da cidade encadeados pelo vizinho mais proximo,
    #    comecando pelo mais perto do centro. Serve para QUALQUER cidade,
    #    nao so para Manaus.
    if BAIRROS_COORD:
        uf_n, cid_n, bai_n = normalizar(uf), normalizar(cidade), normalizar(bairro)
        caminho = _caminho_dos_bairros(uf_n, cid_n)
        if caminho:
            posicao = caminho.get(bai_n)
            if posicao is None:
                # nome escrito de outro jeito: acha pela coordenada
                coord = _bairro_conhecido(uf_n, cid_n, bai_n)
                if coord is not None:
                    for nome, i in caminho.items():
                        if BAIRROS_COORD.get((uf_n, cid_n, nome)) == coord:
                            posicao = i
                            break
            if posicao is not None:
                return (posicao, "", bai_n)
            # a cidade tem bairros na tabela, mas este nao: vai para o fim
            return (98, "", bai_n)

    # 2) sem o arquivo, a regra antiga: a zona da Prefeitura de Manaus
    zona = zona_do_bairro(cidade, bairro)
    if not zona:
        return (99, "", normalizar(bairro))
    return (ORDEM_ZONAS_MANAUS.index(zona) if zona in ORDEM_ZONAS_MANAUS
            else 98, zona, normalizar(bairro))


def ordem_do_bairro(cidade, bairro, uf="") -> tuple:
    """
    Chave de ordenacao do bairro dentro da cidade.

    Com o COORDENADAS_CIDADES_BAIRRO_BAP.xlsx na pasta, a ordem e a
    distancia real: os bairros daquela cidade encadeados pelo vizinho
    mais proximo. Sem ele, vale a regra antiga - a zona da Prefeitura,
    que so existe em Manaus.

    Bairro que nao da para localizar vai para o fim, mas nao se perde.
    Guardado em cache: e chamado uma vez por cliente em cada ordenacao.
    """
    return _ordem_do_bairro(str(uf or ""), str(cidade or ""),
                            str(bairro or ""))


# A tabela da BAP entra sozinha na abertura, se estiver na pasta. Fica
# depois de tudo definido, para poder usar as funcoes acima.
try:
    carregar_coordenadas()
except Exception:                                          # noqa: BLE001
    pass


def ordenar_cidades(cidades, partida=None) -> list:
    """
    Poe as cidades na ordem de quem visita: comeca pela cidade de partida
    (a base do vendedor, ou a maior carteira) e vai sempre para a cidade
    mais proxima da ultima - o vizinho mais proximo. Cidade sem
    coordenada entra no fim, em ordem alfabetica, sem sumir da rota.
    """
    com, sem = [], []
    for uf, cidade in cidades:
        (com if coordenada(uf, cidade) else sem).append((uf, cidade))
    if not com:
        return sorted(sem)
    atual = partida if partida in com else None
    if atual is None:
        atual = min(com, key=lambda x: (x[0], x[1]))
    restantes = [c for c in com if c != atual]
    caminho = [atual]
    while restantes:
        aqui = coordenada(*caminho[-1])
        restantes.sort(key=lambda c: distancia_km(aqui, coordenada(*c)))
        caminho.append(restantes.pop(0))
    return caminho + sorted(sem)


# ==========================================================================
# NOME CANONICO DE BAIRRO
# ==========================================================================
# "CIDADE NOVA", "CIDADE NOVA 1", "CIDADE NOVA I", "CJ CIDADE NOVA" e
# "CIDADE NOVA II" sao, para o cadastro de zona, o mesmo lugar: variam so
# no numeral e no prefixo do tipo de logradouro. O nome canonico junta
# todos eles, para o bairro sem zona herdar a zona do irmao que ja tem.
_PREFIXOS = ("CJ ", "CONJ ", "CONJUNTO ", "JD ", "JARDIM ", "VL ", "VILA ",
             "PQ ", "PARQUE ", "RES ", "RESIDENCIAL ", "LOT ",
             "LOTEAMENTO ", "NUCLEO ", "NC ", "SETOR ", "DISTRITO ",
             "BAIRRO ", "BR ", "COLONIA ", "COL ", "COND ", "CONDOMINIO ")

# os romanos e os por-extenso viram algarismo, para I / 1 / UM baterem
_NUMERAIS = {
    "I": "1", "II": "2", "III": "3", "IV": "4", "V": "5", "VI": "6",
    "VII": "7", "VIII": "8", "IX": "9", "X": "10",
    "UM": "1", "DOIS": "2", "TRES": "3", "QUATRO": "4", "CINCO": "5",
    "PRIMEIRO": "1", "SEGUNDO": "2", "TERCEIRO": "3",
}


@lru_cache(maxsize=8192)
def nome_canonico(bairro) -> str:
    """
    O nome do bairro sem o que so atrapalha a comparacao: acento, prefixo
    de tipo (CJ, JARDIM, VILA...), abreviacao e o numeral do fim.

        CIDADE NOVA      -> CIDADE NOVA
        CIDADE NOVA 1    -> CIDADE NOVA
        CIDADE NOVA I    -> CIDADE NOVA
        CJ CIDADE NOVA II-> CIDADE NOVA
        COLONIA STO ANTONIO -> SANTO ANTONIO
    """
    n = normalizar(bairro)
    if not n:
        return ""
    mudou = True
    while mudou:                      # CJ RES CIDADE NOVA -> CIDADE NOVA
        mudou = False
        for pre in _PREFIXOS:
            if n.startswith(pre) and len(n) > len(pre) + 2:
                n = n[len(pre):]
                mudou = True
    for troca, por in (("STO ", "SANTO "), ("STA ", "SANTA "),
                       ("N SRA ", "NOSSA SENHORA "),
                       ("PRES ", "PRESIDENTE "), ("GOV ", "GOVERNADOR "),
                       ("DR ", "DOUTOR "), ("PROF ", "PROFESSOR ")):
        if n.startswith(troca):
            n = por + n[len(troca):]
    partes = n.split()
    # tira o numeral do fim - mas so quando sobra nome de verdade, para
    # "SETOR 5" e "QUADRA 12" nao virarem todos a mesma coisa
    while len(partes) > 2 and (partes[-1].isdigit()
                               or partes[-1] in _NUMERAIS):
        partes.pop()
    if len(partes) == 2 and (partes[-1].isdigit() or partes[-1] in _NUMERAIS) \
            and len(partes[0]) > 6:
        partes.pop()
    return " ".join(partes) or n


def irmaos_do_bairro(uf, cidade, bairro, candidatos) -> list:
    """
    Entre os `candidatos` (trios uf/cidade/bairro), os que sao o MESMO
    lugar que este bairro: mesma cidade e mesmo nome canonico.
    """
    alvo = nome_canonico(bairro)
    if not alvo:
        return []
    cid = normalizar(cidade)
    uf_n = normalizar(uf)
    return [t for t in candidatos
            if normalizar(t[1]) == cid and normalizar(t[0]) == uf_n
            and nome_canonico(t[2]) == alvo
            and normalizar(t[2]) != normalizar(bairro)]


def bairro_mais_perto(uf, cidade, bairro, candidatos):
    """
    O bairro da MESMA CIDADE, entre os candidatos, que fica mais perto
    deste - pela coordenada. Devolve (trio, km) ou (None, None) quando
    nao ha coordenada dos dois lados.
    """
    aqui = coordenada_do_bairro(uf, cidade, bairro)
    if not aqui:
        return None, None
    cid, uf_n = normalizar(cidade), normalizar(uf)
    melhor, menor = None, None
    for t in candidatos:
        if normalizar(t[1]) != cid or normalizar(t[0]) != uf_n:
            continue
        la = coordenada_do_bairro(t[0], t[1], t[2])
        if not la:
            continue
        km = distancia_km(aqui, la)
        if menor is None or km < menor:
            melhor, menor = t, km
    return melhor, menor


# ==========================================================================
# O PONTO DE CADA CLIENTE E O CAMINHO MAIS CURTO (06/10)
# ==========================================================================
# Antes, a ordem dentro da cidade era a do BAIRRO (e, no fim da rota, a do
# nome do bairro - por isso parecia alfabetica). Agora cada cliente tem um
# PONTO no mapa: a LATITUDE/LONGITUDE da BASE_CLIENTE (o endereco
# geocodificado - geocodificar.py); sem ela, o centro do bairro
# (COORDENADAS_CIDADES_BAIRRO_BAP.xlsx); sem ele, o centro da cidade. A
# ordem e o caminho mais curto entre esses pontos: o vizinho mais proximo
# e depois o 2-opt (desfaz os cruzamentos).
def _num(v):
    try:
        x = float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def ponto_valido(lat, lon) -> bool:
    """Dentro do Brasil (e nao o 0,0 de cadastro vazio)."""
    return lat is not None and lon is not None and \
        -34.0 <= lat <= 5.5 and -74.5 <= lon <= -28.0 and \
        not (abs(lat) < 1e-6 and abs(lon) < 1e-6)


def ponto_do_cliente(c) -> tuple:
    """(lat, lon, precisao) do cliente: "endereco" (geocodificado),
    "endereco proximo" (vizinho na mesma rua / clientes do bairro - ver
    aproximar_pontos), "bairro", "cidade" ou (None, None, "")."""
    lat, lon = _num(c.get("LATITUDE")), _num(c.get("LONGITUDE"))
    if ponto_valido(lat, lon):
        return lat, lon, "endereco"
    ap = c.get("_PONTO_APROX")
    if ap:
        return ap
    b = coordenada_do_bairro(c.get("UF"), c.get("CIDADE"), c.get("BAIRRO"))
    if b:
        return b[0], b[1], "bairro"
    cc = coordenada(c.get("UF"), c.get("CIDADE"))
    if cc:
        return cc[0], cc[1], "cidade"
    return None, None, ""


def _rua_e_numero(c):
    """("AVENIDA AUTAZ MIRIM", 1020) do cadastro (sem o numero na rua)."""
    end_ = re.sub(r"[^A-Z0-9 ]", " ", unicodedata.normalize(
        "NFKD", str(c.get("ENDERECO") or "")).encode("ascii", "ignore")
        .decode().upper())
    try:
        import geocodificar as _gc                      # noqa: PLC0415
        rua = _gc.rua_por_extenso(end_)
        num = _gc.numero_de(c.get("NUMERO"), end_)
    except Exception:                                   # noqa: BLE001
        rua, num = " ".join(end_.split()), ""
    rua = re.sub(r"\s+\d{1,5}\s*$", "", rua).strip()
    try:
        return rua, int(num) if num else None
    except ValueError:
        return rua, None


def aproximar_pontos(clientes) -> int:
    """
    (15/10, Alexandre) A BASE agora tem coordenada de quase todo cliente:
    a rota usa ela. Quem ainda NAO tem ganha o ENDERECO MAIS PROXIMO, so
    para roteirizar (vai em "_PONTO_APROX"; o LATITUDE/LONGITUDE do
    cadastro continua vazio - o .json do Protheus nao leva ponto
    inventado):
      1) um vizinho na MESMA RUA (mesma cidade) ja localizado - o de numero
         mais perto; sem numero, o meio dos vizinhos da rua;
      2) o meio dos clientes localizados do MESMO BAIRRO;
      3) sem nada disso: o centro do bairro/cidade da planilha (como antes).
    Devolve quantos ganharam ponto aproximado.
    """
    def n_(v):
        return " ".join(re.sub(r"[^A-Z0-9 ]", " ", unicodedata.normalize(
            "NFKD", str(v or "")).encode("ascii", "ignore").decode()
            .upper()).split())
    por_rua, por_bairro = {}, {}
    sem = []
    for c in clientes:
        c.pop("_PONTO_APROX", None)
        lat, lon = _num(c.get("LATITUDE")), _num(c.get("LONGITUDE"))
        uf, cid = n_(c.get("UF")), n_(c.get("CIDADE"))
        if ponto_valido(lat, lon):
            rua, num = _rua_e_numero(c)
            if rua:
                por_rua.setdefault((uf, cid, rua), []).append((num, lat, lon))
            por_bairro.setdefault((uf, cid, n_(c.get("BAIRRO"))), []).append(
                (lat, lon))
        else:
            sem.append(c)

    def meio(pts):
        las = sorted(p[0] for p in pts)
        los = sorted(p[1] for p in pts)
        return las[len(las) // 2], los[len(los) // 2]   # mediana: sem outlier
    n = 0
    for c in sem:
        uf, cid = n_(c.get("UF")), n_(c.get("CIDADE"))
        rua, num = _rua_e_numero(c)
        viz = por_rua.get((uf, cid, rua)) if rua else None
        if viz:
            com_num = [v for v in viz if v[0] is not None]
            if num is not None and com_num:
                v = min(com_num, key=lambda x: abs(x[0] - num))
                c["_PONTO_APROX"] = (v[1], v[2], "endereco proximo")
            else:
                la, lo = meio([(v[1], v[2]) for v in viz])
                c["_PONTO_APROX"] = (la, lo, "endereco proximo")
            n += 1
            continue
        bai = por_bairro.get((uf, cid, n_(c.get("BAIRRO"))))
        if bai:
            la, lo = meio(bai)
            c["_PONTO_APROX"] = (la, lo, "bairro (clientes)")
            n += 1
    return n


def _xy(p, lat0):
    """O ponto em km num plano (equirretangular): para comparar distancia
    rapido. Vale bem dentro de uma cidade ou regiao."""
    return (p[1] * 111.32 * math.cos(math.radians(lat0)), p[0] * 110.57)


def caminho_mais_curto(pontos, inicio=None, segundos=1.5) -> list:
    """
    A ordem de visita de uma lista de pontos [(lat, lon)]: comeca no ponto
    mais perto de `inicio` (sem inicio: o primeiro da lista), vai sempre
    ao vizinho mais proximo e depois melhora com o 2-opt (desfaz cada
    cruzamento do trajeto) ate acabar ou passar do tempo. Devolve a
    lista de indices. Ponto None vai para o fim, na ordem em que veio.
    """
    import time as _t                                   # noqa: PLC0415
    com = [i for i, p in enumerate(pontos) if p and p[0] is not None]
    sem = [i for i, p in enumerate(pontos) if not (p and p[0] is not None)]
    if len(com) <= 2:
        if inicio and len(com) == 2:
            a, b = com
            if distancia_km(inicio, pontos[b]) < distancia_km(inicio,
                                                               pontos[a]):
                com = [b, a]
        return com + sem
    lat0 = sum(pontos[i][0] for i in com) / len(com)
    xy = {i: _xy(pontos[i], lat0) for i in com}

    def d(a, b):
        return math.hypot(xy[a][0] - xy[b][0], xy[a][1] - xy[b][1])
    if inicio:
        x0 = _xy(inicio, lat0)
        atual = min(com, key=lambda i: (math.hypot(xy[i][0] - x0[0],
                                                   xy[i][1] - x0[1]), i))
    else:
        atual = com[0]
    restantes = set(com)
    restantes.discard(atual)
    rota = [atual]
    while restantes:
        aqui = rota[-1]
        prox = min(restantes, key=lambda i: (d(aqui, i), i))
        restantes.discard(prox)
        rota.append(prox)
    # 2-opt no caminho ABERTO (o comeco fica onde esta)
    n = len(rota)
    janela = n if n <= 300 else 80
    fim = _t.time() + segundos
    melhorou = True
    while melhorou and _t.time() < fim:
        melhorou = False
        for i in range(1, n - 1):
            a, b = rota[i - 1], rota[i]
            for j in range(i + 1, min(n, i + janela)):
                c = rota[j]
                e = rota[j + 1] if j + 1 < n else None
                antes = d(a, b) + (d(c, e) if e is not None else 0.0)
                depois = d(a, c) + (d(b, e) if e is not None else 0.0)
                if depois < antes - 1e-9:
                    rota[i:j + 1] = reversed(rota[i:j + 1])
                    b = rota[i]
                    melhorou = True
            if _t.time() >= fim:
                break
    return rota + sem


def km_do_caminho(pontos, ordem, inicio=None) -> float:
    """Os km em linha reta de um trajeto (para comparar ordens)."""
    seq = [pontos[i] for i in ordem if pontos[i] and pontos[i][0] is not None]
    if inicio and seq:
        seq = [inicio] + seq
    return sum(distancia_km(a, b) for a, b in zip(seq, seq[1:]))
