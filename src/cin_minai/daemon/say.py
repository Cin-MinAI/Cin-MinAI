# SPDX-License-Identifier: GPL-3.0-or-later
"""What the daemon itself says around searches, the news and watches, in the six v1 languages (PLAN D25). The model
writes none of this. Error details from the network ({e}) stay as the system gave them.

Written by Claude (not a native speaker of es/pt/fr/de/ja): wants a native speaker's review (D36).
"""

from __future__ import annotations

SAY = {
    "en": {
        "search_offer": "I can look that up on the web. Below is exactly what would be sent; nothing leaves this "
                        "computer until you click Search.",
        "search_offline": "I'd need to look that up on the web, and this computer isn't online right now. Connect "
                          "to the internet, then click Search below.",
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
    },
    "es": {
        "search_offer": "Puedo buscarlo en la web. Abajo está exactamente lo que se enviaría; nada sale de este "
                        "equipo hasta que hagas clic en Buscar.",
        "search_offline": "Tendría que buscarlo en la web, y este equipo no tiene conexión ahora. Conéctate a "
                          "internet y luego haz clic en Buscar abajo.",
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
    },
    "pt": {
        "search_offer": "Posso pesquisar isso na web. Abaixo está exatamente o que seria enviado; nada sai deste "
                        "computador até você clicar em Pesquisar.",
        "search_offline": "Eu precisaria pesquisar isso na web, e este computador está sem internet agora. "
                          "Conecte-se e clique em Pesquisar abaixo.",
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
    },
    "fr": {
        "search_offer": "Je peux le chercher sur le web. Ci-dessous, exactement ce qui serait envoyé ; rien ne quitte "
                        "cet ordinateur avant que vous cliquiez sur Rechercher.",
        "search_offline": "Il faudrait le chercher sur le web, et cet ordinateur n'est pas en ligne pour l'instant. "
                          "Connectez-vous, puis cliquez sur Rechercher ci-dessous.",
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
    },
    "de": {
        "search_offer": "Ich kann das im Web nachschlagen. Unten steht genau, was gesendet würde; nichts verlässt "
                        "diesen Computer, bevor Sie auf Suchen klicken.",
        "search_offline": "Ich müsste das im Web nachschlagen, und dieser Computer ist gerade offline. Verbinden Sie "
                          "sich mit dem Internet und klicken Sie dann unten auf Suchen.",
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
    },
    "ja": {
        "search_offer": "ウェブで調べられます。送信される内容は下のとおりです。「検索」を押すまで、このコンピューターからは"
                        "何も送られません。",
        "search_offline": "ウェブで調べる必要がありますが、今はオフラインです。インターネットに接続してから、下の「検索」を"
                          "押してください。",
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
    },
}


def say(lang: str, key: str, **kw) -> str:
    return SAY.get(lang, SAY["en"])[key].format(**kw)


def quoted(topic: str, lang: str) -> str:
    return f"「{topic}」" if lang == "ja" else f"« {topic} »" if lang == "fr" else f"„{topic}“" if lang == "de" else \
        f"“{topic}”"
