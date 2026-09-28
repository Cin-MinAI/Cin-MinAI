# SPDX-License-Identifier: GPL-3.0-or-later
"""Search words for the help cards (transition.py, lessons.py), in the six v1 languages (PLAN D25).

`lookup_help(query)` gets a query the guide writes itself — in English or in the user's language, often
with the Windows name of the thing ("Add or Remove Programs", "Windows Fax and Scan"). The cards are in
English, with Mint's names filled in per language, so a German "Hintergrundbild ändern" would find
nothing in them. These words bridge that: per card, the ways people ask about it, in every language.
The daemon's retrieval (src/cin_minai/daemon/helpcards.py) indexes them with the card text, the Windows
description and Mint's own labels in all languages. Measured on labelled queries: tests/unit/test_helpcards.py.

Written by Claude (not a native speaker of es/pt/fr/de/ja): wants a native speaker's review (D36).
"""

KEYWORDS = {
    # --- transition.py ---------------------------------------------------------------------------
    "install": "install installing installer setup download exe msi program programs app apps software "
               "instalar instalación descargar programa aplicación instalação baixar programa aplicativo "
               "installer installation télécharger logiciel programme installieren installation herunterladen "
               "programm anwendung software インストール ダウンロード ソフト アプリ 導入",
    "uninstall": "uninstall remove delete program add remove programs apps features "
                 "desinstalar quitar eliminar programa agregar quitar programas remover excluir "
                 "désinstaller supprimer programme programmes fonctionnalités deinstallieren entfernen "
                 "löschen programm programme features アンインストール 削除 プログラムの追加と削除",
    "store": "microsoft store app store shop tienda de aplicaciones loja de aplicativos magasin boutique "
             "d'applications app-store laden ストア アプリストア",
    "office": "microsoft office word excel powerpoint libreoffice documents spreadsheet slides "
              "ofimática documentos hoja de cálculo diapositivas planilha escritório bureautique tableur "
              "diapositives büro tabellenkalkulation folien オフィス ワード エクセル パワーポイント "
              # boot check 1 (2026-09-28): "open something for me to write a document in" found word count
              "write a document write something write a letter program to write word processor typing "
              "escribir un documento escribir una carta procesador de texto escrever um documento escrever "
              "uma carta editor de texto écrire un document écrire une lettre traitement de texte "
              "dokument schreiben brief schreiben textverarbeitung 文書を書く 手紙を書く 文書作成",
    "games": "games gaming steam play juegos jugar jogos jogar jeux jouer spiele spielen ゲーム steam counter-strike visual c++ redistributable directx",
    "control_panel": "control panel settings windows settings configuration panel de control configuración "
                     "ajustes painel de controle configurações panneau de configuration paramètres réglages "
                     "systemsteuerung einstellungen コントロールパネル 設定",
    "start_menu": "start menu start button menú inicio botón inicio menu iniciar botão iniciar menu démarrer "
                  "bouton démarrer startmenü startknopf start-menü スタートメニュー スタートボタン",
    "explorer": "file explorer this pc my computer c: drive drives disk files explorador de archivos este equipo "
                "mi pc unidad explorador de arquivos este computador meu computador unidade explorateur de "
                "fichiers ce pc poste de travail lecteur explorer dieser pc arbeitsplatz laufwerk dateien "
                "エクスプローラー マイコンピュータ ドライブ Cドライブ where are my files personal files home folder stored",
    "task_manager": "task manager ctrl alt del end task processes running programs administrador de tareas "
                    "finalizar tarea gerenciador de tarefas finalizar tarefa gestionnaire des tâches fin de "
                    "tâche task-manager taskmanager aufgabe beenden prozesse タスクマネージャー プロセス 終了",
    "frozen": "frozen not responding hang hung stuck crash force quit close program congelado no responde "
              "colgado cerrar programa travado não responde fechar programa figé ne répond pas bloqué fermer "
              "programme eingefroren reagiert nicht hängt abgestürzt beenden 応答なし フリーズ 固まった 強制終了",
    "notepad": "notepad text editor txt plain text bloc de notas editor de texto bloco de notas bloc-notes "
               "éditeur de texte editor texteditor メモ帳 テキストエディター",
    "paint": "paint ms paint drawing draw picture image dibujar dibujo pintar desenhar desenho dessiner "
             "dessin peindre zeichnen malen zeichenprogramm ペイント お絵かき 絵を描く",
    "photos": "photos pictures images photo viewer albums import camera phone fotos imágenes álbum cámara "
              "fotos imagens álbum câmera photos images albums appareil photo bilder fotos alben kamera "
              "写真 画像 アルバム フォト",
    "media": "media player movies tv video music play windows media player vlc reproductor video música "
             "películas reprodutor vídeo música filmes lecteur multimédia vidéo musique films mediaplayer "
             "video musik filme abspielen メディアプレーヤー 動画 音楽 ビデオ 映画",
    "calculator": "calculator calculate sums fractions calculadora calcular calculatrice calculer "
                  "taschenrechner rechner rechnen 電卓 計算機 計算",
    "sticky": "sticky notes note post-it reminder notas adhesivas nota recordatorio notas autoadesivas lembrete "
              "pense-bête notes post-it haftnotizen notizzettel notiz 付箋 メモ",
    "outlook": "outlook mail email e-mail inbox account thunderbird correo electrónico cuenta de correo e-mail "
               "correio conta de e-mail courriel messagerie boîte mail compte e-mail postfach konto "
               "メール 電子メール アウトルック メールアカウント email program mail program check email read email programa de correo programa de e-mail programme de messagerie e-mail-programm",
    "pdf": "pdf adobe reader acrobat edge open pdf form fill abrir pdf formulario rellenar preencher "
           "formulário ouvrir pdf formulaire remplir öffnen formular ausfüllen PDF 開く フォーム",
    "zip": "zip unzip extract compressed archive rar 7z descomprimir extraer comprimido extrair compactado "
           "décompresser extraire archive compressé entpacken extrahieren komprimiert archiv 解凍 圧縮 zipファイル",
    "browser": "browser web browser edge internet explorer chrome firefox navegador navegador web "
               "navigateur webbrowser ブラウザー ブラウザ インターネット",
    "recycle_bin": "recycle bin trash deleted files restore empty papelera reciclaje restaurar vaciar lixeira "
                   "restaurar esvaziar corbeille restaurer vider papierkorb wiederherstellen leeren ごみ箱 復元",
    "char_map": "character map special characters symbols accents emoji mapa de caracteres caracteres "
                "especiales símbolos acentos caracteres especiais símbolos table des caractères caractères "
                "spéciaux symboles zeichentabelle sonderzeichen symbole 文字コード表 特殊文字 記号 besondere zeichen © ® ™",
    "scanner": "scan scanner scanning fax and scan document letter escanear escáner digitalizar escanear "
               "scanner documento numériser scanner télécopie document scannen einscannen scanner dokument "
               "スキャン スキャナー",
    "nearby_share": "nearby sharing share files send files another computer same wifi network transfer "
                    "compartir archivos enviar otro ordenador compartilhar arquivos enviar outro computador "
                    "partage de proximité partager fichiers envoyer autre ordinateur dateien teilen senden "
                    "anderen computer übertragen ファイル共有 近距離共有 転送 送る",
    "onscreen_kb": "on-screen keyboard onscreen virtual keyboard touchscreen teclado en pantalla teclado virtual "
                   "clavier visuel clavier virtuel bildschirmtastatur virtuelle tastatur スクリーンキーボード "
                   "ソフトウェアキーボード",
    "windows_update": "windows update updates update system upgrade actualizar actualizaciones actualización "
                      "atualizar atualizações mise à jour mettre à jour aktualisieren aktualisierung updates "
                      "アップデート 更新 Windows Update check for updates install updates look for updates buscar actualizaciones procurar atualizações rechercher des mises à jour nach updates suchen",
    "antivirus": "antivirus windows defender virus protection malware security antivirus protección "
                 "seguridad proteção segurança protection sécurité virenschutz virenscanner sicherheit "
                 "ウイルス対策 アンチウイルス ウイルス セキュリティ",
    "firewall": "firewall defender firewall cortafuegos protección de red pare-feu pare feu brandmauer "
                "ファイアウォール",
    "system_restore": "system restore restore point snapshot go back undo update restaurar sistema punto de "
                      "restauración restauração do sistema ponto de restauração restauration du système point "
                      "de restauration systemwiederherstellung wiederherstellungspunkt システムの復元 復元ポイント",
    "backup": "backup back up file history copy documents usb disk copia de seguridad respaldo historial "
              "cópia de segurança backup sauvegarde historique des fichiers sicherung datensicherung "
              "dateiversionsverlauf バックアップ ファイル履歴",
    "microsoft_account": "microsoft account onedrive sign in login online account cloud cuenta de microsoft "
                         "iniciar sesión conta microsoft entrar compte microsoft se connecter microsoft-konto "
                         "anmelden マイクロソフトアカウント サインイン ワンドライブ OneDrive",
    "admin_password": "administrator admin password user account control uac asks password sudo contraseña "
                      "administrador control de cuentas senha administrador mot de passe administrateur "
                      "contrôle de compte passwort administrator benutzerkontensteuerung kennwort "
                      "管理者 パスワード ユーザーアカウント制御",
    "lock_screen": "lock screen lock computer windows+l win+l bloquear pantalla bloquear equipo bloquear tela "
                   "verrouiller écran verrouiller sperren bildschirm sperren 画面ロック ロック",
    "drivers": "drivers driver device manager graphics card nvidia amd hardware controladores administrador "
               "de dispositivos tarjeta gráfica drivers gerenciador de dispositivos placa de vídeo pilotes "
               "gestionnaire de périphériques carte graphique treiber geräte-manager gerätemanager grafikkarte "
               "ドライバー デバイスマネージャー グラフィック",
    "wallpaper": "wallpaper background desktop picture personalize fondo de pantalla fondo de escritorio "
                 "personalizar papel de parede plano de fundo área de trabalho fond d'écran arrière-plan "
                 "bureau personnaliser hintergrundbild hintergrund desktop 壁紙 背景 デスクトップ",
    "dark_mode": "dark mode dark theme night theme modo oscuro tema oscuro modo escuro tema escuro mode sombre "
                 "thème sombre dunkelmodus dunkles design dunkler modus ダークモード ダークテーマ",
    "display_scale": "display resolution scale scaling screen size make everything bigger monitor resolución "
                     "escala pantalla tamaño resolução escala tela tamanho résolution échelle mise à "
                     "l'échelle écran taille auflösung skalierung bildschirm größe 解像度 拡大縮小 スケール 画面 ディスプレイ",
    "text_size": "text size bigger text font size larger text ease of access tamaño del texto letra más grande "
                 "tamanho do texto letra maior taille du texte police plus grand texte schriftgröße "
                 "textgröße größere schrift 文字サイズ 文字を大きく フォントサイズ",
    "screen_timeout": "screen turns off sleep power screen timeout goes black energy suspend pantalla se apaga "
                      "suspender energía tela desliga suspensão energia écran s'éteint veille énergie "
                      "bildschirm geht aus ruhezustand energie standby 画面が消える スリープ 電源",
    "night_light": "night light blue light warm evening luz nocturna luz noturna éclairage nocturne veilleuse "
                   "nachtlicht nachtmodus blaulicht 夜間モード ナイトライト",
    "mouse": "mouse pointer speed left-handed buttons double-click touchpad ratón puntero velocidad zurdo "
             "mouse ponteiro velocidade canhoto souris pointeur vitesse gaucher maus zeiger geschwindigkeit "
             "linkshänder マウス ポインター 速度 左利き mausgeschwindigkeit mausknopf maustaste mauszeiger",
    "keyboard_layout": "keyboard layout keyboard language input language add keyboard teclado distribución "
                       "idioma del teclado layout do teclado idioma do teclado clavier disposition langue du "
                       "clavier tastatur tastaturlayout tastatursprache キーボード配列 キーボード レイアウト",
    "system_language": "display language system language change language interface language idioma del "
                       "sistema cambiar idioma idioma do sistema mudar idioma langue du système changer la "
                       "langue systemsprache sprache ändern anzeigesprache 表示言語 言語 言語設定 画面の言語 言語を変更 英語に変更 表示言語を変更",
    "typing_japanese": "japanese ime typing japanese input method mozc ibus japonés teclado japonés japonês "
                       "digitar japonês japonais saisie japonaise japanisch japanisch tippen eingabemethode "
                       "日本語入力 日本語 IME 入力方法",
    "clock": "clock date time time zone timezone reloj fecha hora zona horaria relógio data hora fuso horário "
             "horloge date heure fuseau horaire uhr datum uhrzeit zeitzone 時計 日付 時刻 タイムゾーン",
    "startup_apps": "startup programs startup apps start automatically login boot inicio automático programas "
                    "de inicio inicialização automática programas de inicialização démarrage automatique "
                    "programmes au démarrage autostart startprogramme 自動起動 スタートアップ",
    "default_apps": "default apps default browser default program open with predeterminado navegador "
                    "predeterminado aplicaciones predeterminadas padrão navegador padrão par défaut navigateur "
                    "par défaut standard standardbrowser standardprogramme 既定のアプリ 既定のブラウザー",
    "wifi": "wi-fi wifi wireless internet connect network password conectar red inalámbrica conectar rede "
            "sem fio se connecter réseau sans fil wlan verbinden drahtlos netzwerk 無線LAN ワイファイ 接続 Wi-Fi",
    "bluetooth": "bluetooth pair pairing headphones earbuds speaker mouse emparejar auriculares emparelhar "
                 "fones appairer casque écouteurs koppeln kopfhörer ブルートゥース ペアリング イヤホン ヘッドホン 接続 ワイヤレス",
    "sound_output": "sound speakers headphones volume audio output no sound sonido altavoces auriculares "
                    "volumen som alto-falantes fones volume son haut-parleurs casque volume ton lautsprecher "
                    "kopfhörer lautstärke 音 スピーカー ヘッドホン 音量",
    "screen_reader": "narrator screen reader read aloud blind accessibility narrador lector de pantalla leer "
                     "en voz alta leitor de tela ler em voz alta narrateur lecteur d'écran lire à voix haute "
                     "sprachausgabe bildschirmleser vorlesen ナレーター スクリーンリーダー 読み上げ",
    "web_app": "web app pin website taskbar website as app shortcut site aplicación web anclar sitio "
               "aplicativo web fixar site application web épingler site web-app webseite anheften "
               "ウェブアプリ サイト ピン留め website shortcut web app shortcut site shortcut",
    "screenshot": "screenshot snipping tool print screen prtsc capture captura de pantalla recortes captura "
                  "de tela capture d'écran outil capture bildschirmfoto screenshot bildschirmaufnahme "
                  "スクリーンショット 画面キャプチャ",
    "desktop_shortcut": "desktop shortcut desktop icon shortcut acceso directo escritorio ícono atalho área "
                        "de trabalho raccourci bureau icône verknüpfung desktop symbol "
                        "ショートカット デスクトップ アイコン",
    "switch_windows": "switch windows alt tab alt+tab change window cambiar ventanas alternar janelas changer "
                      "de fenêtre basculer fenster wechseln ウィンドウ切り替え switch between open windows quickly",
    "taskbar": "taskbar panel bar bottom move taskbar size barra de tareas barra de tarefas barre des tâches "
               "taskleiste leiste タスクバー パネル",
    "scam_email": "scam phishing email bank link pin password fake email fraud estafa correo banco enlace "
                  "fraude golpe e-mail banco link arnaque hameçonnage courriel banque lien betrug phishing "
                  "bank link 詐欺 フィッシング 銀行 メール",
    "scam_phone": "phone call scam microsoft support caller tech support remote access llamada estafa soporte "
                  "técnico ligação golpe suporte técnico appel arnaque support technique anruf betrug "
                  "technischer support 電話 詐欺 サポート詐欺 phishing call suspicious call scam call",
    "scam_popup": "popup pop-up virus warning infected call number fake warning alert ventana emergente "
                  "advertencia virus infectado aviso vírus janela alerte virus infecté fenêtre warnung virus "
                  "infiziert ウイルス警告 偽の警告 ポップアップ 感染 suspicious website suspicious web page sitio sospechoso site suspeito site suspect verdächtige webseite 怪しいサイト",
    "privacy_assistant": "privacy assistant ai sends data internet typing online spy tracking privacidad "
                         "asistente datos privacidade assistente dados vie privée assistant données "
                         "datenschutz assistent daten プライバシー アシスタント データ 送信 does it send what i type user input sent to the internet listen record ネットに送る 送ってる 入力内容",
    "offline_mode": "offline disconnect internet no internet airplane keep offline desconectar sin internet "
                    "desconectar sem internet hors ligne déconnecter sans internet offline trennen ohne "
                    "internet オフライン 切断 インターネットを切る disable internet turn off internet disable network network adapter no connection desligar a internet desactivar internet désactiver internet internet ausschalten",
    "updates_why": "why updates important updates matter security updates ignore por qué actualizar "
                   "importancia por que atualizar importância pourquoi mettre à jour importance warum "
                   "aktualisieren wichtig なぜ更新 アップデートの重要性 bother worth skip need updates should i update",
    "word_files": "word files docx doc open word document save as word archivo word abrir docx arquivo word "
                  "fichier word ouvrir docx word-datei öffnen docx ワードファイル docx 開く",
    # --- lessons.py ------------------------------------------------------------------------------
    "copy_paste": "copy paste ctrl+c ctrl+v copiar pegar copiar colar copier coller kopieren einfügen "
                  "コピー 貼り付け",
    "new_folder": "new folder create folder make folder organize carpeta nueva crear carpeta pasta nova criar "
                  "pasta nouveau dossier créer dossier neuer ordner ordner erstellen 新しいフォルダー フォルダー作成",
    "usb_remove": "usb stick remove safely eject flash drive memory stick pendrive memoria usb expulsar "
                  "extraer quitar sacar pen drive ejetar remover retirar clé usb éjecter retirer usb-stick "
                  "auswerfen entfernen USBメモリー 取り外し 安全に取り外す tirar com segurança safely remove hardware",
    "save_file": "save saving document ctrl+s save as guardar documento salvar documento enregistrer "
                 "sauvegarder speichern dokument 保存 上書き保存",
    "files_folders": "file folder what is a file what is a folder archivo carpeta arquivo pasta fichier "
                     "dossier datei ordner ファイル フォルダー",
    "downloads": "downloads downloaded files where download descargas archivos descargados downloads "
                 "transferências téléchargements fichiers téléchargés downloads heruntergeladen "
                 "ダウンロード ダウンロードしたファイル",
    "zoom_text": "zoom in zoom out bigger text browser ctrl + ampliar zoom texto más grande aumentar zoom "
                 "agrandir zoom texte plus grand vergrößern zoom schrift größer 拡大 ズーム 文字を大きく browser browsers web page website font size in browser página web page web webseite",
    "right_click": "right-click right click right mouse button context menu clic derecho botón derecho "
                   "clique direito botão direito clic droit bouton droit rechtsklick rechte maustaste "
                   "右クリック",
    "delete_files": "delete files remove files erase borrar archivos eliminar apagar arquivos excluir "
                    "supprimer fichiers effacer dateien löschen entfernen ファイル削除 削除",
    "printers": "printer add printer print devices and printers impresora agregar impresora imprimir "
                "impressora adicionar impressora imprimante ajouter imprimante drucker hinzufügen drucken "
                "プリンター 印刷",
    "word_count": "word count count words characters number of words contar palabras contar palavras "
                  "nombre de mots compter mots wörter zählen wortanzahl 文字数 単語数",
    "what_is_linux": "what is linux linux mint cin-minai operating system compared difference differs qué es linux sistema operativo o "
                     "que é linux qu'est-ce que linux système d'exploitation was ist linux betriebssystem "
                     "Linuxとは オペレーティングシステム",
    "dvd": "dvd play dvd disc movie cd reproducir dvd disco assistir dvd lire dvd disque dvd abspielen "
           "DVD 再生",
    "chart": "chart graph diagram budget excel chart gráfico diagrama gráfico graphique diagramme diagramm "
             "grafik tabelle グラフ チャート",
    "video_call": "video call zoom teams skype whatsapp google meet camera microphone videollamada "
                  "videochamada chamada de vídeo appel vidéo visioconférence videoanruf videokonferenz "
                  "ビデオ通話 テレビ会議 カメラ",
}
