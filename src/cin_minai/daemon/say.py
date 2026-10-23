# SPDX-License-Identifier: GPL-3.0-or-later
"""What the daemon itself says around searches, the news and watches, in the six v1 languages (PLAN D25). The model
writes none of this. Error details from the network ({e}) stay as the system gave them.

Written by Claude (not a native speaker of es/pt/fr/de/ja): wants a native speaker's review (D36).
"""

from __future__ import annotations

SAY = {
    "en": {
        "driver_offer": "Your graphics card's recommended driver is {pkg}, the same one Driver Manager would pick. The card below installs it: click {allow}, then type your password. When it's done, restart the computer so the new driver starts.",
        "driver_none": "This computer doesn't need an extra graphics driver: the one it uses now is the right one.",
        "driver_have": 'The recommended driver ({pkg}) is already installed. If the screen or the assistant still seem slow, restart the computer once so the driver starts.',
        "driver_reason": "the recommended driver for this computer's graphics card (the one Driver Manager lists)",
        "cuda_reason": "a faster engine for your NVIDIA card: the assistant reads your questions several times faster ({size}, about 1.1 GB on disk). No: it keeps working as it does now, and won't ask again.",
        "size_mb": 'about {mb} MB to download',
        "size_unknown": 'a few hundred MB to download',
        "search_offer": "I can look that up on the web. Below is exactly what would be sent; nothing leaves this "
                        "computer until you click Search.",
        "search_offline": "I'd need to look that up on the web, and this computer isn't online right now. Connect "
                          "to the internet, then click Search below.",
        "memory_intro": "This is what I have in memory about {subject}:",
        "memory_more": "Would you like me to look online for more information? Below is exactly what would be sent; nothing leaves this computer until you click Search.",
        "memory_more_offline": "To look online for more information, connect to the internet, then click Search below.",
        "wiki_none": "Wikipedia has no article on that. I can search the web instead: below is exactly what would be sent; nothing leaves this computer until you click Search.",
        "not_in_article": "The article doesn't say.",
        "not_in_pages": "The pages don't say.",
        "news_only": "what people on {only} say about {topic}",
        "news_all": "what the press, social media and official pages say about {topic}",
        "news_top": "today's top stories",
        "news_offer": "I'll look up {what} and show you each source's own words with its date. I don't say what "
                      "happened, only who says what. ",
        "send_online": "Below is exactly what would be sent; nothing leaves this computer until you click Search.",
        "send_offline": "This computer isn't online right now: connect, then click Search below.",
        "news_failed": "The news search didn't work: {e}.",
        "official_trouble": "(Couldn't search official pages right now: {e}.)",
        "watch_news": "the news about {topic}",
        "watch_top": "the top stories",
        "watch_offer": "I can watch {what} for you: every day at {at} I'll look again and show you only what's "
                       "new, each source in its own words. The card below says exactly what would be sent and where; "
                       "nothing is set up until you click Set up. You can pause or delete it any time under Standing "
                       "tasks.",
        "watch_set": "Set up: every day at {at} I'll show you only what's new. This is where it starts:",
        "watch_failed": "The watch is set up, but the first look didn't work: {e}. It tries again at {at}.",
        "notify_title": "News watch",
        "notify_body": "{n} new about {what}. Open the assistant to read them.",
        "upd_on": 'The card below switches on daily updates: once a day, the updates nothing holds install by themselves, with the same checks as the Updates window, and never on battery. Click {allow}, then type your password.',
        "upd_wait": ' New updates will wait {days} days first, so others have time to find a problem in them.',
        "upd_nowait": " If you'd like new updates to wait a few days first, so others have time to find a problem in them, say so (“and wait 2 days”) or tick it in Updates.",
        "upd_off": 'The card below stops the daily updates; nothing else changes. Click {allow}, then type your password. You can still install updates yourself in Updates.',
        "upd_already_on": 'Daily updates are already on. Standing tasks and Updates show what the last run did.',
        "upd_already_off": "Daily updates are already off. Updates shows what's waiting, whenever you want to look.",
        "upd_missing": "Daily updates come with the Updates window, which isn't installed on this computer.",
        "upd_reason_on": 'you asked to keep this computer updated',
        "upd_reason_off": 'you asked to stop the daily updates',
        "upd_wait_on": "The card below lets new updates wait {days} days before they can be installed, so others have time to find a problem in them; a security fix Debian's security team confirms still goes early. Click {allow}, then type your password. To hold one update or one program instead, open Updates and use its Hold menu.",
        "upd_wait_off": 'The card below ends the wait: new updates can be installed as soon as they come. Your holds on single updates or programs stay. Click {allow}, then type your password.',
        "upd_already_wait": 'New updates already wait {days} days. Updates shows when each one is ready, and its Hold menu holds one update or program for longer.',
        "upd_already_nowait": "New updates don't wait now. Updates shows what's waiting.",
        "upd_reason_wait": 'you asked to put a hold on new updates',
        "upd_reason_nowait": 'you asked to end the hold on new updates',
    },
    "es": {
        "driver_offer": 'El controlador recomendado para tu tarjeta gráfica es {pkg}, el mismo que elegiría el Gestor de controladores. La tarjeta de abajo lo instala: haz clic en {allow} y escribe tu contraseña. Cuando termine, reinicia el equipo para que arranque el nuevo controlador.',
        "driver_none": 'Este equipo no necesita un controlador gráfico adicional: el que usa ahora es el adecuado.',
        "driver_have": 'El controlador recomendado ({pkg}) ya está instalado. Si la pantalla o el asistente siguen lentos, reinicia el equipo una vez para que arranque.',
        "driver_reason": 'el controlador recomendado para la tarjeta gráfica de este equipo (el que muestra el Gestor de controladores)',
        "cuda_reason": 'un motor más rápido para tu tarjeta NVIDIA: el asistente lee tus preguntas varias veces más rápido ({size}, unos 1,1 GB en disco). No: sigue funcionando como ahora y no vuelve a preguntar.',
        "size_mb": 'unos {mb} MB de descarga',
        "size_unknown": 'unos cientos de MB de descarga',
        "search_offer": "Puedo buscarlo en la web. Abajo está exactamente lo que se enviaría; nada sale de este "
                        "equipo hasta que hagas clic en Buscar.",
        "search_offline": "Tendría que buscarlo en la web, y este equipo no tiene conexión ahora. Conéctate a "
                          "internet y luego haz clic en Buscar abajo.",
        "memory_intro": "Esto es lo que tengo en memoria sobre {subject}:",
        "memory_more": "¿Quieres que busque más información en internet? Abajo está exactamente lo que se enviaría; nada sale de este equipo hasta que hagas clic en Buscar.",
        "memory_more_offline": "Para buscar más información en internet, conéctate y luego haz clic en Buscar abajo.",
        "wiki_none": "Wikipedia no tiene ningún artículo sobre eso. Puedo buscarlo en la web: abajo está exactamente lo que se enviaría; nada sale de este equipo hasta que hagas clic en Buscar.",
        "not_in_article": "El artículo no lo dice.",
        "not_in_pages": "Las páginas no lo dicen.",
        "news_only": "lo que dice la gente en {only} sobre {topic}",
        "news_all": "lo que dicen la prensa, las redes sociales y las páginas oficiales sobre {topic}",
        "news_top": "las noticias principales de hoy",
        "news_offer": "Buscaré {what} y te mostraré las palabras de cada fuente con su fecha. No digo qué pasó, solo "
                      "quién dice qué. ",
        "send_online": "Abajo está exactamente lo que se enviaría; nada sale de este equipo hasta que hagas clic en "
                       "Buscar.",
        "send_offline": "Este equipo no tiene conexión ahora: conéctate y luego haz clic en Buscar abajo.",
        "news_failed": "La búsqueda de noticias no funcionó: {e}.",
        "official_trouble": "(No se pudieron consultar las páginas oficiales ahora: {e}.)",
        "watch_news": "las noticias sobre {topic}",
        "watch_top": "las noticias principales",
        "watch_offer": "Puedo seguir {what} por ti: cada día a las {at} volveré a mirar y te mostraré solo lo nuevo, "
                       "cada fuente con sus propias palabras. La tarjeta de abajo dice exactamente qué se enviaría y "
                       "adónde; no se configura nada hasta que hagas clic en Configurar. Puedes pausarlo o eliminarlo "
                       "cuando quieras en Tareas permanentes.",
        "watch_set": "Listo: cada día a las {at} te mostraré solo lo nuevo. Este es el punto de partida:",
        "watch_failed": "El seguimiento está configurado, pero la primera búsqueda no funcionó: {e}. Volverá a "
                        "intentarlo a las {at}.",
        "notify_title": "Seguimiento de noticias",
        "notify_body": "{n} novedades sobre {what}. Abre el asistente para leerlas.",
        "upd_on": 'La tarjeta de abajo activa las actualizaciones diarias: una vez al día, las actualizaciones que nada retiene se instalan solas, con las mismas comprobaciones que la ventana Actualizaciones, y nunca con batería. Haz clic en {allow} y escribe tu contraseña.',
        "upd_wait": ' Las actualizaciones nuevas esperarán {days} días antes, para que otros tengan tiempo de encontrar un problema en ellas.',
        "upd_nowait": ' Si quieres que las actualizaciones nuevas esperen unos días antes, para que otros tengan tiempo de encontrar un problema, dilo («y espera 2 días») o márcalo en Actualizaciones.',
        "upd_off": 'La tarjeta de abajo detiene las actualizaciones diarias; nada más cambia. Haz clic en {allow} y escribe tu contraseña. Puedes seguir instalando actualizaciones tú mismo en Actualizaciones.',
        "upd_already_on": 'Las actualizaciones diarias ya están activadas. Tareas permanentes y Actualizaciones muestran lo que hizo la última vez.',
        "upd_already_off": 'Las actualizaciones diarias ya están desactivadas. Actualizaciones muestra lo que espera, cuando quieras mirarlo.',
        "upd_missing": 'Las actualizaciones diarias vienen con la ventana Actualizaciones, que no está instalada en este equipo.',
        "upd_reason_on": 'pediste mantener este equipo actualizado',
        "upd_reason_off": 'pediste detener las actualizaciones diarias',
        "upd_wait_on": 'La tarjeta de abajo hace que las actualizaciones nuevas esperen {days} días antes de poder instalarse, para que otros tengan tiempo de encontrar un problema; una corrección de seguridad que confirma el equipo de seguridad de Debian sigue yendo antes. Haz clic en {allow} y escribe tu contraseña. Para retener una sola actualización o un programa, abre Actualizaciones y usa su menú Retener.',
        "upd_wait_off": 'La tarjeta de abajo quita la espera: las actualizaciones nuevas pueden instalarse en cuanto llegan. Lo que retienes tú se queda. Haz clic en {allow} y escribe tu contraseña.',
        "upd_already_wait": 'Las actualizaciones nuevas ya esperan {days} días. Actualizaciones muestra cuándo está lista cada una, y su menú Retener retiene una actualización o un programa más tiempo.',
        "upd_already_nowait": 'Ahora las actualizaciones nuevas no esperan. Actualizaciones muestra lo que espera.',
        "upd_reason_wait": 'pediste retener las actualizaciones nuevas',
        "upd_reason_nowait": 'pediste quitar la espera de las actualizaciones nuevas',
    },
    "pt": {
        "driver_offer": 'O driver recomendado para a sua placa de vídeo é {pkg}, o mesmo que o Gerenciador de drivers escolheria. O cartão abaixo o instala: clique em {allow} e digite sua senha. Quando terminar, reinicie o computador para o novo driver iniciar.',
        "driver_none": 'Este computador não precisa de um driver de vídeo extra: o que ele usa agora é o certo.',
        "driver_have": 'O driver recomendado ({pkg}) já está instalado. Se a tela ou o assistente ainda parecerem lentos, reinicie o computador uma vez para ele iniciar.',
        "driver_reason": 'o driver recomendado para a placa de vídeo deste computador (o que o Gerenciador de drivers mostra)',
        "cuda_reason": 'um motor mais rápido para a sua placa NVIDIA: o assistente lê suas perguntas várias vezes mais rápido ({size}, cerca de 1,1 GB no disco). Não: ele continua funcionando como agora e não pergunta de novo.',
        "size_mb": 'cerca de {mb} MB para baixar',
        "size_unknown": 'algumas centenas de MB para baixar',
        "search_offer": "Posso pesquisar isso na web. Abaixo está exatamente o que seria enviado; nada sai deste "
                        "computador até você clicar em Pesquisar.",
        "search_offline": "Eu precisaria pesquisar isso na web, e este computador está sem internet agora. "
                          "Conecte-se e clique em Pesquisar abaixo.",
        "memory_intro": "Isto é o que tenho na memória sobre {subject}:",
        "memory_more": "Quer que eu procure mais informações na internet? Abaixo está exatamente o que seria enviado; nada sai deste computador até você clicar em Pesquisar.",
        "memory_more_offline": "Para procurar mais informações na internet, conecte-se e clique em Pesquisar abaixo.",
        "wiki_none": "A Wikipédia não tem nenhum artigo sobre isso. Posso pesquisar na web: abaixo está exatamente o que seria enviado; nada sai deste computador até você clicar em Pesquisar.",
        "not_in_article": "O artigo não diz.",
        "not_in_pages": "As páginas não dizem.",
        "news_only": "o que as pessoas no {only} dizem sobre {topic}",
        "news_all": "o que a imprensa, as redes sociais e as páginas oficiais dizem sobre {topic}",
        "news_top": "as principais notícias de hoje",
        "news_offer": "Vou procurar {what} e mostrar as palavras de cada fonte com a data. Não digo o que "
                      "aconteceu, só quem diz o quê. ",
        "send_online": "Abaixo está exatamente o que seria enviado; nada sai deste computador até você clicar em "
                       "Pesquisar.",
        "send_offline": "Este computador está sem internet agora: conecte-se e clique em Pesquisar abaixo.",
        "news_failed": "A busca de notícias não funcionou: {e}.",
        "official_trouble": "(Não foi possível consultar as páginas oficiais agora: {e}.)",
        "watch_news": "as notícias sobre {topic}",
        "watch_top": "as principais notícias",
        "watch_offer": "Posso acompanhar {what} para você: todos os dias às {at} vou olhar de novo e mostrar só o "
                       "que é novo, cada fonte com as próprias palavras. O cartão abaixo diz exatamente o que seria "
                       "enviado e para onde; nada é configurado até você clicar em Configurar. Você pode pausar ou "
                       "excluir quando quiser em Tarefas permanentes.",
        "watch_set": "Pronto: todos os dias às {at} vou mostrar só o que é novo. Este é o ponto de partida:",
        "watch_failed": "O acompanhamento está configurado, mas a primeira busca não funcionou: {e}. Tenta de novo "
                        "às {at}.",
        "notify_title": "Acompanhamento de notícias",
        "notify_body": "{n} novidades sobre {what}. Abra o assistente para ler.",
        "upd_on": 'O cartão abaixo liga as atualizações diárias: uma vez por dia, as atualizações que nada retém se instalam sozinhas, com as mesmas verificações da janela Atualizações, e nunca na bateria. Clique em {allow} e digite sua senha.',
        "upd_wait": ' As atualizações novas vão esperar {days} dias antes, para que outros tenham tempo de achar um problema nelas.',
        "upd_nowait": ' Se quiser que as atualizações novas esperem alguns dias antes, para que outros tenham tempo de achar um problema, diga (“e espere 2 dias”) ou marque em Atualizações.',
        "upd_off": 'O cartão abaixo para as atualizações diárias; nada mais muda. Clique em {allow} e digite sua senha. Você ainda pode instalar atualizações em Atualizações.',
        "upd_already_on": 'As atualizações diárias já estão ligadas. Tarefas permanentes e Atualizações mostram o que a última fez.',
        "upd_already_off": 'As atualizações diárias já estão desligadas. Atualizações mostra o que está esperando, quando quiser olhar.',
        "upd_missing": 'As atualizações diárias vêm com a janela Atualizações, que não está instalada neste computador.',
        "upd_reason_on": 'você pediu para manter este computador atualizado',
        "upd_reason_off": 'você pediu para parar as atualizações diárias',
        "upd_wait_on": 'O cartão abaixo faz as atualizações novas esperarem {days} dias antes de poderem ser instaladas, para que outros tenham tempo de achar um problema; uma correção de segurança que a equipe de segurança do Debian confirma ainda vai antes. Clique em {allow} e digite sua senha. Para reter uma só atualização ou um programa, abra Atualizações e use o menu Segurar.',
        "upd_wait_off": 'O cartão abaixo tira a espera: as atualizações novas podem ser instaladas assim que chegam. O que você retém continua. Clique em {allow} e digite sua senha.',
        "upd_already_wait": 'As atualizações novas já esperam {days} dias. Atualizações mostra quando cada uma fica pronta, e o menu Segurar segura uma atualização ou um programa por mais tempo.',
        "upd_already_nowait": 'Agora as atualizações novas não esperam. Atualizações mostra o que está esperando.',
        "upd_reason_wait": 'você pediu para reter as atualizações novas',
        "upd_reason_nowait": 'você pediu para tirar a espera das atualizações novas',
    },
    "fr": {
        "driver_offer": "Le pilote recommandé pour votre carte graphique est {pkg}, celui que choisirait le Gestionnaire de pilotes. La carte ci-dessous l'installe : cliquez sur {allow}, puis saisissez votre mot de passe. Une fois terminé, redémarrez l'ordinateur pour que le nouveau pilote démarre.",
        "driver_none": "Cet ordinateur n'a pas besoin d'un pilote graphique supplémentaire : celui qu'il utilise est le bon.",
        "driver_have": "Le pilote recommandé ({pkg}) est déjà installé. Si l'écran ou l'assistant semblent encore lents, redémarrez l'ordinateur une fois pour qu'il démarre.",
        "driver_reason": 'le pilote recommandé pour la carte graphique de cet ordinateur (celui que liste le Gestionnaire de pilotes)',
        "cuda_reason": "un moteur plus rapide pour votre carte NVIDIA : l'assistant lit vos questions plusieurs fois plus vite ({size}, environ 1,1 Go sur le disque). Non : il continue comme maintenant et ne redemande pas.",
        "size_mb": 'environ {mb} Mo à télécharger',
        "size_unknown": 'quelques centaines de Mo à télécharger',
        "search_offer": "Je peux le chercher sur le web. Ci-dessous, exactement ce qui serait envoyé ; rien ne quitte "
                        "cet ordinateur avant que vous cliquiez sur Rechercher.",
        "search_offline": "Il faudrait le chercher sur le web, et cet ordinateur n'est pas en ligne pour l'instant. "
                          "Connectez-vous, puis cliquez sur Rechercher ci-dessous.",
        "memory_intro": "Voici ce que j'ai en mémoire sur {subject} :",
        "memory_more": "Voulez-vous que je cherche plus d'informations en ligne ? Ci-dessous, exactement ce qui serait envoyé ; rien ne quitte cet ordinateur avant que vous cliquiez sur Rechercher.",
        "memory_more_offline": "Pour chercher plus d'informations en ligne, connectez-vous, puis cliquez sur Rechercher ci-dessous.",
        "wiki_none": "Wikipédia n'a pas d'article à ce sujet. Je peux chercher sur le web : ci-dessous, exactement ce qui serait envoyé ; rien ne quitte cet ordinateur avant que vous cliquiez sur Rechercher.",
        "not_in_article": "L'article ne le dit pas.",
        "not_in_pages": "Les pages ne le disent pas.",
        "news_only": "ce que disent les gens sur {only} à propos de {topic}",
        "news_all": "ce que disent la presse, les réseaux sociaux et les pages officielles à propos de {topic}",
        "news_top": "les principaux titres du jour",
        "news_offer": "Je vais chercher {what} et vous montrer les mots de chaque source avec sa date. Je ne dis pas "
                      "ce qui s'est passé, seulement qui dit quoi. ",
        "send_online": "Ci-dessous, exactement ce qui serait envoyé ; rien ne quitte cet ordinateur avant que vous "
                       "cliquiez sur Rechercher.",
        "send_offline": "Cet ordinateur n'est pas en ligne : connectez-vous, puis cliquez sur Rechercher ci-dessous.",
        "news_failed": "La recherche d'actualités n'a pas marché : {e}.",
        "official_trouble": "(Impossible de consulter les pages officielles pour l'instant : {e}.)",
        "watch_news": "les nouvelles sur {topic}",
        "watch_top": "les principaux titres",
        "watch_offer": "Je peux surveiller {what} pour vous : chaque jour à {at}, je regarderai à nouveau et ne vous "
                       "montrerai que les nouveautés, chaque source avec ses propres mots. La carte ci-dessous dit "
                       "exactement ce qui serait envoyé et où ; rien n'est configuré avant que vous cliquiez sur "
                       "Configurer. Vous pouvez la suspendre ou la supprimer quand vous voulez dans Tâches "
                       "permanentes.",
        "watch_set": "C'est fait : chaque jour à {at}, je ne vous montrerai que les nouveautés. Voici le point de "
                     "départ :",
        "watch_failed": "La veille est configurée, mais la première recherche n'a pas marché : {e}. Nouvel essai à "
                        "{at}.",
        "notify_title": "Veille d'actualités",
        "notify_body": "{n} nouveautés sur {what}. Ouvrez l'assistant pour les lire.",
        "upd_on": "La carte ci-dessous active les mises à jour quotidiennes : une fois par jour, les mises à jour que rien ne retient s'installent seules, avec les mêmes vérifications que la fenêtre Mises à jour, et jamais sur batterie. Cliquez sur {allow}, puis tapez votre mot de passe.",
        "upd_wait": " Les nouvelles mises à jour attendront {days} jours, pour que d'autres aient le temps d'y trouver un problème.",
        "upd_nowait": " Si vous voulez que les nouvelles mises à jour attendent quelques jours, pour que d'autres aient le temps d'y trouver un problème, dites-le (« et attends 2 jours ») ou cochez-le dans Mises à jour.",
        "upd_off": "La carte ci-dessous arrête les mises à jour quotidiennes ; rien d'autre ne change. Cliquez sur {allow}, puis tapez votre mot de passe. Vous pouvez toujours installer les mises à jour vous-même dans Mises à jour.",
        "upd_already_on": "Les mises à jour quotidiennes sont déjà activées. Tâches permanentes et Mises à jour montrent ce qu'a fait la dernière.",
        "upd_already_off": 'Les mises à jour quotidiennes sont déjà désactivées. Mises à jour montre ce qui attend, quand vous voulez.',
        "upd_missing": "Les mises à jour quotidiennes viennent avec la fenêtre Mises à jour, qui n'est pas installée sur cet ordinateur.",
        "upd_reason_on": 'vous avez demandé de garder cet ordinateur à jour',
        "upd_reason_off": "vous avez demandé d'arrêter les mises à jour quotidiennes",
        "upd_wait_on": "La carte ci-dessous fait attendre les nouvelles mises à jour {days} jours avant de pouvoir être installées, pour que d'autres aient le temps d'y trouver un problème ; un correctif de sécurité confirmé par l'équipe de sécurité de Debian passe toujours plus tôt. Cliquez sur {allow}, puis tapez votre mot de passe. Pour retenir une seule mise à jour ou un programme, ouvrez Mises à jour et utilisez son menu Retenir.",
        "upd_wait_off": "La carte ci-dessous enlève l'attente : les nouvelles mises à jour peuvent s'installer dès qu'elles arrivent. Ce que vous retenez reste retenu. Cliquez sur {allow}, puis tapez votre mot de passe.",
        "upd_already_wait": 'Les nouvelles mises à jour attendent déjà {days} jours. Mises à jour montre quand chacune est prête, et son menu Retenir garde une mise à jour ou un programme plus longtemps.',
        "upd_already_nowait": "Les nouvelles mises à jour n'attendent pas pour l'instant. Mises à jour montre ce qui attend.",
        "upd_reason_wait": 'vous avez demandé de retenir les nouvelles mises à jour',
        "upd_reason_nowait": "vous avez demandé d'enlever l'attente des nouvelles mises à jour",
    },
    "de": {
        "driver_offer": 'Der empfohlene Treiber für Ihre Grafikkarte ist {pkg}, derselbe, den die Treiberverwaltung wählen würde. Die Karte unten installiert ihn: Klicken Sie auf {allow} und geben Sie Ihr Passwort ein. Starten Sie den Computer danach neu, damit der neue Treiber startet.',
        "driver_none": 'Dieser Computer braucht keinen zusätzlichen Grafiktreiber: Der aktuelle ist der richtige.',
        "driver_have": 'Der empfohlene Treiber ({pkg}) ist schon installiert. Wenn Bildschirm oder Assistent noch langsam wirken, starten Sie den Computer einmal neu, damit er startet.',
        "driver_reason": 'der empfohlene Treiber für die Grafikkarte dieses Computers (der in der Treiberverwaltung)',
        "cuda_reason": 'ein schnellerer Motor für Ihre NVIDIA-Karte: Der Assistent liest Ihre Fragen mehrfach schneller ({size}, etwa 1,1 GB auf der Festplatte). Nein: Er arbeitet weiter wie jetzt und fragt nicht noch einmal.',
        "size_mb": 'etwa {mb} MB zum Herunterladen',
        "size_unknown": 'einige hundert MB zum Herunterladen',
        "search_offer": "Ich kann das im Web nachschlagen. Unten steht genau, was gesendet würde; nichts verlässt "
                        "diesen Computer, bevor Sie auf Suchen klicken.",
        "search_offline": "Ich müsste das im Web nachschlagen, und dieser Computer ist gerade offline. Verbinden Sie "
                          "sich mit dem Internet und klicken Sie dann unten auf Suchen.",
        "memory_intro": "Das habe ich über {subject} im Gedächtnis:",
        "memory_more": "Soll ich online nach mehr Informationen suchen? Unten steht genau, was gesendet würde; nichts verlässt diesen Computer, bevor Sie auf Suchen klicken.",
        "memory_more_offline": "Um online nach mehr Informationen zu suchen, verbinden Sie sich mit dem Internet und klicken Sie dann unten auf Suchen.",
        "wiki_none": "Wikipedia hat keinen Artikel dazu. Ich kann im Web suchen: Unten steht genau, was gesendet würde; nichts verlässt diesen Computer, bevor Sie auf Suchen klicken.",
        "not_in_article": "Der Artikel sagt das nicht.",
        "not_in_pages": "Die Seiten sagen das nicht.",
        "news_only": "was Leute auf {only} über {topic} sagen",
        "news_all": "was Presse, soziale Medien und offizielle Seiten über {topic} sagen",
        "news_top": "die Top-Meldungen von heute",
        "news_offer": "Ich suche {what} und zeige Ihnen die Worte jeder Quelle mit Datum. Ich sage nicht, was "
                      "passiert ist, nur wer was sagt. ",
        "send_online": "Unten steht genau, was gesendet würde; nichts verlässt diesen Computer, bevor Sie auf Suchen "
                       "klicken.",
        "send_offline": "Dieser Computer ist gerade offline: Verbinden Sie sich und klicken Sie dann unten auf Suchen.",
        "news_failed": "Die Nachrichtensuche hat nicht funktioniert: {e}.",
        "official_trouble": "(Offizielle Seiten konnten gerade nicht abgefragt werden: {e}.)",
        "watch_news": "die Nachrichten zu {topic}",
        "watch_top": "die Top-Meldungen",
        "watch_offer": "Ich kann {what} für Sie beobachten: Jeden Tag um {at} schaue ich wieder nach und zeige Ihnen "
                       "nur Neues, jede Quelle mit ihren eigenen Worten. Die Karte unten sagt genau, was wohin "
                       "gesendet würde; nichts wird eingerichtet, bevor Sie auf Einrichten klicken. Pausieren oder "
                       "löschen können Sie es jederzeit unter Daueraufgaben.",
        "watch_set": "Eingerichtet: Jeden Tag um {at} zeige ich Ihnen nur Neues. Hier ist der Ausgangspunkt:",
        "watch_failed": "Die Beobachtung ist eingerichtet, aber die erste Suche hat nicht funktioniert: {e}. Neuer "
                        "Versuch um {at}.",
        "notify_title": "Nachrichtenbeobachtung",
        "notify_body": "{n} neu zu {what}. Öffnen Sie den Assistenten, um sie zu lesen.",
        "upd_on": 'Die Karte unten schaltet die täglichen Updates ein: Einmal am Tag installieren sich die Updates, die nichts zurückhält, von selbst, mit denselben Prüfungen wie im Fenster Updates, und nie im Akkubetrieb. Klicken Sie auf {allow} und geben Sie Ihr Passwort ein.',
        "upd_wait": ' Neue Updates warten zuerst {days} Tage, damit andere Zeit haben, ein Problem darin zu finden.',
        "upd_nowait": ' Wenn neue Updates zuerst ein paar Tage warten sollen, damit andere Zeit haben, ein Problem zu finden, sagen Sie es („und warte 2 Tage“) oder kreuzen Sie es in Updates an.',
        "upd_off": 'Die Karte unten beendet die täglichen Updates; sonst ändert sich nichts. Klicken Sie auf {allow} und geben Sie Ihr Passwort ein. In Updates können Sie Updates weiterhin selbst installieren.',
        "upd_already_on": 'Die täglichen Updates sind schon eingeschaltet. Daueraufgaben und Updates zeigen, was der letzte Lauf getan hat.',
        "upd_already_off": 'Die täglichen Updates sind schon ausgeschaltet. Updates zeigt, was wartet, wann immer Sie nachsehen möchten.',
        "upd_missing": 'Die täglichen Updates gehören zum Fenster Updates, das auf diesem Computer nicht installiert ist.',
        "upd_reason_on": 'Sie haben gebeten, diesen Computer aktuell zu halten',
        "upd_reason_off": 'Sie haben gebeten, die täglichen Updates zu beenden',
        "upd_wait_on": 'Die Karte unten lässt neue Updates {days} Tage warten, bevor sie installiert werden können, damit andere Zeit haben, ein Problem darin zu finden; eine Sicherheitskorrektur, die das Sicherheitsteam von Debian bestätigt, kommt weiterhin früher. Klicken Sie auf {allow} und geben Sie Ihr Passwort ein. Um nur ein Update oder ein Programm zurückzuhalten, öffnen Sie Updates und nutzen Sie dort das Menü Zurückhalten.',
        "upd_wait_off": 'Die Karte unten beendet die Wartezeit: Neue Updates können installiert werden, sobald sie kommen. Was Sie selbst zurückhalten, bleibt. Klicken Sie auf {allow} und geben Sie Ihr Passwort ein.',
        "upd_already_wait": 'Neue Updates warten schon {days} Tage. Updates zeigt, wann jedes bereit ist, und sein Menü Zurückhalten hält ein Update oder Programm länger zurück.',
        "upd_already_nowait": 'Neue Updates warten zurzeit nicht. Updates zeigt, was wartet.',
        "upd_reason_wait": 'Sie haben gebeten, neue Updates zurückzuhalten',
        "upd_reason_nowait": 'Sie haben gebeten, die Wartezeit für neue Updates zu beenden',
    },
    "ja": {
        "driver_offer": 'お使いのグラフィックカードの推奨ドライバーは{pkg}です（ドライバーマネージャーが選ぶものと同じ）。下のカードでインストールします。「{allow}」を押してからパスワードを入力してください。終わったら、新しいドライバーを使うためにコンピューターを再起動してください。',
        "driver_none": 'このコンピューターに追加のグラフィックドライバーは必要ありません。今のドライバーで適切です。',
        "driver_have": '推奨ドライバー（{pkg}）はすでにインストールされています。画面やアシスタントがまだ遅い場合は、一度再起動してください。',
        "driver_reason": 'このコンピューターのグラフィックカードの推奨ドライバー（ドライバーマネージャーに表示されるもの）',
        "cuda_reason": 'NVIDIAカード用の高速エンジン：アシスタントが質問を数倍速く読み込みます（{size}、ディスク約1.1 GB）。「いいえ」の場合は今のまま動作し、再度は尋ねません。',
        "size_mb": 'ダウンロード約{mb} MB',
        "size_unknown": 'ダウンロード数百MB',
        "search_offer": "ウェブで調べられます。送信される内容は下のとおりです。「検索」を押すまで、このコンピューターからは"
                        "何も送られません。",
        "search_offline": "ウェブで調べる必要がありますが、今はオフラインです。インターネットに接続してから、下の「検索」を"
                          "押してください。",
        "memory_intro": "{subject}について、私が覚えていることです：",
        "memory_more": "インターネットでさらに調べましょうか？送信される内容は下にそのまま表示されています。「検索」を押すまで、何もこのコンピューターから出ません。",
        "memory_more_offline": "インターネットでさらに調べるには、接続してから下の「検索」を押してください。",
        "wiki_none": "Wikipediaにはその記事がありません。代わりにウェブで検索できます。送信される内容は下にそのまま表示されています。「検索」を押すまで、何もこのコンピューターから出ません。",
        "not_in_article": "記事には書かれていません。",
        "not_in_pages": "ページには書かれていません。",
        "news_only": "{only}で人々が{topic}について言っていること",
        "news_all": "報道・SNS・公式ページが{topic}について言っていること",
        "news_top": "今日の主なニュース",
        "news_offer": "{what}を調べ、各情報源の言葉を日付付きでお見せします。何が起きたかは言いません。誰が何を言って"
                      "いるかだけです。",
        "send_online": "送信される内容は下のとおりです。「検索」を押すまで、このコンピューターからは何も送られません。",
        "send_offline": "今はオフラインです。接続してから、下の「検索」を押してください。",
        "news_failed": "ニュースの検索がうまくいきませんでした：{e}。",
        "official_trouble": "（公式ページを今は検索できませんでした：{e}）",
        "watch_news": "{topic}のニュース",
        "watch_top": "主なニュース",
        "watch_offer": "{what}を見守れます。毎日{at}にもう一度調べ、新しいものだけを、各情報源の言葉のままお見せします。"
                       "何がどこに送られるかは下のカードのとおりです。「設定する」を押すまで何も設定されません。"
                       "定期タスクからいつでも一時停止・削除できます。",
        "watch_set": "設定しました。毎日{at}に新しいものだけをお見せします。ここが出発点です：",
        "watch_failed": "見守りは設定しましたが、最初の検索がうまくいきませんでした：{e}。{at}にもう一度試します。",
        "notify_title": "ニュースの見守り",
        "notify_body": "{what}について新着{n}件。アシスタントを開いて読んでください。",
        "upd_on": '下のカードで毎日の更新をオンにします。1日1回、何にも保留されていない更新が、更新ウィンドウと同じ確認を経て自動でインストールされます（バッテリー駆動中は行いません）。{allow}を押してから、パスワードを入力してください。',
        "upd_wait": '新しい更新はまず{days}日待ちます。そのあいだに、ほかの人が問題を見つけられるようにするためです。',
        "upd_nowait": '新しい更新を数日待たせたい場合は（ほかの人が問題を見つける時間のため）、そう言うか（「2日待って」）、更新ウィンドウでチェックしてください。',
        "upd_off": '下のカードで毎日の更新を止めます。ほかは何も変わりません。{allow}を押してから、パスワードを入力してください。更新ウィンドウから自分で更新を入れることはこれまでどおりできます。',
        "upd_already_on": '毎日の更新はすでにオンです。前回の結果は定期タスクと更新ウィンドウで見られます。',
        "upd_already_off": '毎日の更新はすでにオフです。待っている更新は、更新ウィンドウでいつでも見られます。',
        "upd_missing": '毎日の更新は更新ウィンドウに含まれていますが、このコンピューターにはインストールされていません。',
        "upd_reason_on": 'このコンピューターを最新に保つよう頼まれました',
        "upd_reason_off": '毎日の更新を止めるよう頼まれました',
        "upd_wait_on": '下のカードで、新しい更新をインストールできるまで{days}日待たせます。そのあいだに、ほかの人が問題を見つけられるようにするためです。Debianのセキュリティチームが確認したセキュリティ修正は、これまでどおり先に入ります。{allow}を押してから、パスワードを入力してください。1つの更新や1つのプログラムだけを保留したい場合は、更新ウィンドウの「保留」メニューを使ってください。',
        "upd_wait_off": '下のカードで待ち時間をなくします。新しい更新は届いたらすぐにインストールできます。あなたが個別に保留しているものはそのままです。{allow}を押してから、パスワードを入力してください。',
        "upd_already_wait": '新しい更新はすでに{days}日待つ設定です。それぞれがいつ準備できるかは更新ウィンドウで見られ、「保留」メニューで1つの更新やプログラムをもっと長く保留できます。',
        "upd_already_nowait": '今は新しい更新は待たずに入ります。待っている更新は更新ウィンドウで見られます。',
        "upd_reason_wait": '新しい更新を保留するよう頼まれました',
        "upd_reason_nowait": '新しい更新の保留をやめるよう頼まれました',
    },
}


def say(lang: str, key: str, **kw) -> str:
    return SAY.get(lang, SAY["en"])[key].format(**kw)


def quoted(topic: str, lang: str) -> str:
    return f"「{topic}」" if lang == "ja" else f"« {topic} »" if lang == "fr" else f"„{topic}“" if lang == "de" else \
        f"“{topic}”"
