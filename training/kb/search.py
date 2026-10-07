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
    "vpn": "vpn virtual private network openvpn ovpn wireguard proxy hide ip address public wifi privacy "
           "red privada virtual ocultar ip rede privada virtual esconder ip réseau privé virtuel masquer "
           "adresse ip virtuelles privates netzwerk ip verbergen vpnを使う 仮想プライベートネットワーク IPアドレス",
    "keyring": "keyring key ring keyring password unlock login keyring credential manager saved passwords "
               "key vault seahorse llavero contraseña del llavero desbloquear chaveiro senha do chaveiro "
               "desbloquear trousseau mot de passe du trousseau déverrouiller schlüsselbund schlüsselbund "
               "passwort entsperren キーリング キーリングのパスワード ロック解除",
    "hidden_files": "hidden dotfiles dot .config ctrl+h invisible ocultos archivos ocultos arquivos ocultos "
                    "cachés fichiers cachés versteckte dateien 隠し 隠しファイル",
    "user_accounts": "user account new user add user family member child account another person "
                     "standard administrator cuenta de usuario nuevo usuario añadir usuario conta de usuário novo "
                     "usuário adicionar usuário compte nouveau compte ajouter un compte "
                     "benutzerkonto neuer benutzer benutzer hinzufügen ユーザーアカウント ユーザーを追加 新しいユーザー "
                     "son daughter kid kids hijo hija niño filho filha criança fils fille enfant sohn tochter kind "
                     "子供 息子 娘 家族",
    "bootable_usb": "bootable usb boot usb live usb iso write iso burn iso rufus media creation tool etcher "
                    "disk image installer stick usb booteable grabar iso imagen de disco "
                    "pendrive bootável gravar iso imagem de disco clé usb bootable graver iso "
                    "image disque bootfähiger usb-stick iso schreiben abbild "
                    "起動用USB ブータブルUSB ISOを書き込む ディスクイメージ",
    "aicui": "aicui coding ide code editor programming vs code visual studio code ai coding agent develop "
             "programar entorno de desarrollo editor de código programação ambiente de desenvolvimento "
             "programmer environnement de développement éditeur de code programmieren entwicklungsumgebung "
             "code-editor プログラミング 開発環境 コードエディター",
    "usb_format": "format usb stick formatting wipe stick fat32 exfat ntfs file system reuse stick formatear "
                  "memoria usb sistema de archivos formatar pendrive sistema de arquivos formater clé usb système "
                  "de fichiers usb-stick formatieren dateisystem USBメモリをフォーマット フォーマット ファイルシステム",
    "software_sources": "software sources repository repositories ppa mirror download server trusted source where "
                        "to download safely fuentes de software repositorio servidor espejo fontes de programas "
                        "repositório espelho sources de logiciels dépôt miroir miroirs changer de miroir paketquellen paketquellen "
                        "quellen ändern spiegelserver "
                        "softwarequellen ソフトウェアソース リポジトリ ミラー",
    "panel": "taskbar panel pin program pin to taskbar move taskbar applets tray barra de tareas anclar "
             "barra de tarefas fixar barre des tâches épingler taskleiste anheften leiste タスクバー パネル ピン留め",
    "online_accounts": "online accounts google account calendar sync cuentas en línea "
                       "cuenta de google contas online conta google comptes en ligne compte google internetkonten "
                       "google-konto オンラインアカウント グーグルアカウント",
    "notifications": "notifications focus assist do not disturb silence alerts notificaciones no molestar "
                     "notificações não perturbe notifications ne pas déranger benachrichtigungen nicht stören "
                     "通知 おやすみモード",
    "auto_login": "automatic login auto login without password sign in automatically autologin inicio de sesión "
                  "automático login automático connexion automatique automatische anmeldung ohne passwort sin contraseña "
                  "sem senha sans mot de passe 自動ログイン パスワードなし "
                  "パスワードなしでログイン",
    "disk_health": "disk health hard drive health smart chkdsk failing drive ssd health salud del disco "
                   "saúde do disco santé du disque festplatte zustand smart-werte ディスクの健康状態 SMART",
    "specs": "specs specifications what processor how much ram memory graphics card hardware about my pc system "
             "information especificaciones procesador memoria tarjeta gráfica especificações placa de vídeo "
             "caractéristiques processeur mémoire carte graphique prozessor arbeitsspeicher grafikkarte grafikkarte "
             "habe ich gpu "
             "スペック プロセッサー メモリ メモリ容量 どのくらい グラフィックカード",
    "battery": "battery battery life laptop battery saver lid close power percentage batería portátil bateria "
               "notebook batterie portable akku laptop deckel バッテリー 電池",
    "live_usb": "live usb try without installing test drive live session before installing probar sin instalar "
                "sesión en vivo testar sem instalar sessão live essayer sans installer session live ohne "
                "installation testen live-sitzung ライブセッション お試し",
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
    # --- terminal.py (M3): the error words themselves, and how the guide phrases its lookups -------------------
    "cmd_not_found": "command not found unknown command typo misspelled update sudo update terminal doesn't know "
                     "comando no encontrado orden desconocida comando não encontrado commande introuvable "
                     "befehl nicht gefunden unbekannter befehl コマンドが見つかりません",
    "permission_denied": "permission denied script run script execute executable chmod not allowed access denied "
                         "./script sh file permissions permiso denegado permissão negada permission refusée "
                         "keine berechtigung zugriff verweigert 許可がありません 権限",
    "spaces_in_names": "too many arguments space spaces in name folder name with space cd quotes quote filename "
                       "demasiados argumentos espacio en el nombre muitos argumentos espaço trop d'arguments "
                       "espace dans le nom zu viele argumente leerzeichen 引数が多すぎます 空白 スペース",
    "apt_locate": "unable to locate package apt install package not found cannot find package apt-get chromium "
                  "no se puede encontrar el paquete paquete no encontrado impossível encontrar o pacote "
                  "impossible de trouver le paquet paket nicht gefunden パッケージが見つかりません",
    "python_module": "modulenotfounderror no module named import error python module missing library pip install "
                     "pygame venv externally-managed-environment importerror python library install "
                     "módulo no encontrado biblioteca módulo não encontrado module introuvable modul nicht "
                     "gefunden モジュールが見つかりません",
    "venv_create": "ensurepip is not available virtual environment was not created successfully python3-venv venv "
                   "create virtual environment python3 -m venv fails entorno virtual ambiente virtual "
                   "environnement virtuel virtuelle umgebung 仮想環境",
    "venv_missing": "no such file or directory .venv/bin/python .venv/bin/pip .venv/bin/activate no venv missing venv "
                    "venv doesn't exist no virtual environment make a venv create venv here python3 -m venv "
                    "no existe el entorno virtual ambiente virtual não existe pas d'environnement virtuel "
                    "keine virtuelle umgebung 仮想環境がない",
    "venv_use": "venv .venv activate source activate virtual environment deactivate bad interpreter broken venv "
                "moved folder renamed project .venv/bin/pip .venv/bin/python requirements.txt permission denied "
                "activate entorno virtual activar ambiente virtual ativar environnement virtuel activer "
                "virtuelle umgebung aktivieren 仮想環境 有効化",
    "tkinter": "tkinter tinkter tkinker tk _tkinter python3-tk gui window toolkit install tkinter in a virtual "
               "environment venv .venv pip install tkinter no matching "
               "distribution found for tkinter could not find a version that satisfies the requirement tkinter "
               "interfaz gráfica interface gráfica interface graphique grafische oberfläche ウィンドウ",
    "dpkg_lock": "could not get lock dpkg lock lock-frontend unable to acquire another process is using "
                 "apt busy waiting for cache lock bloqueo bloqueio verrou sperre ロック",
    "no_such_file": "no such file or directory file not found folder not found wrong path pwd ls cd "
                    "no existe el archivo o el directorio arquivo ou diretório não encontrado "
                    "aucun fichier ou dossier de ce type datei oder verzeichnis nicht gefunden "
                    "そのようなファイルやディレクトリはありません",
    "compile_error": "compile error compiler error gcc g++ make build error undeclared identifier was not declared "
                     "expected semicolon error 1 build failed c program c++ error de compilación erro de compilação "
                     "erreur de compilation kompilierfehler übersetzungsfehler コンパイルエラー",
    "sudo_password": "sudo password not shown typing password nothing appears sudoers not in the sudoers file "
                     "administrator password contraseña sudo senha sudo mot de passe sudo sudo passwort "
                     "パスワード 管理者",
}
