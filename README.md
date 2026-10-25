# ChampLive

Servidor próprio de transmissão de tela para assistir lives entre amigos, criado como alternativa ao Go Live do Discord. Roda em uma VPS Oracle Cloud com MediaMTX e Apache, acessível em https://champbr.com.

## O que tem

- Player WebRTC de baixa latência, com menu das lives ativas e contador de viewers em tempo real
- Transmissão Rápida pelo navegador (`getDisplayMedia`), sem precisar do OBS
- Transmissão pelo OBS via RTMP
- Acesso protegido por senha (Digest) e HTTPS (Let's Encrypt)
- Painel de usuários em `/admin.html`: admins criam e excluem usuários, trocam senhas e definem outros admins; quem não é admin pode trocar a própria senha

## Estrutura

```
site/index.html                 página principal (player + transmissão rápida)
site/admin.html                 painel de usuários
server/usuarios.cgi             API do painel (CGI em Python, edita o htdigest)
server/apache-champlive.conf    proxies e senha do Apache
server/mediamtx-ajustes.yml     chaves alteradas no mediamtx.yml
server/mediamtx.service         serviço systemd do MediaMTX
.github/workflows/deploy.yml    deploy automático no servidor
```

## Transmitir pelo OBS

- Servidor: `rtmp://champbr.com:1935/live`
- Chave: um nome único por pessoa (ex.: `caio`)
- Saída: H264, perfil `main`, keyframe a cada 2 s, sem B-frames (`bframes=0 repeat_headers=1` no x264)

## Portas abertas na VPS

| Porta | Protocolo | Uso |
|---|---|---|
| 443 | TCP | Site (HTTPS) |
| 1935 | TCP | RTMP (OBS) |
| 8189 | UDP | Mídia WebRTC |

## Deploy

Todo push em `main` que mexe em `site/` publica o site em `/var/www/html` na VPS pelo GitHub Actions. O workflow usa três secrets do repositório: `SSH_HOST`, `SSH_USER` e `SSH_KEY`.

O mesmo workflow instala `server/usuarios.cgi` em `/usr/local/lib/champlive/` (usa `sudo` na VPS).

## Painel de usuários

O painel (`/admin.html`) chama `/api/usuarios`, um CGI em Python 3 (só biblioteca padrão) que o Apache roda depois de conferir a senha Digest. Ele edita dois arquivos em `/var/lib/champlive/`, que pertencem ao `www-data`:

- `htdigest`: usuários e senhas, o mesmo arquivo do `AuthUserFile`. O Apache relê o arquivo a cada acesso, então não precisa recarregar nada.
- `admins`: nomes dos admins, um por linha.

Ninguém consegue excluir o próprio usuário nem tirar o próprio admin, então sempre sobra pelo menos um admin. Quem troca a própria senha precisa logar de novo no navegador.

### Ativar na VPS (uma vez)

1. Ver o realm e os usuários atuais (formato `usuario:realm:hash`):
   ```sh
   sudo cut -d: -f1,2 /etc/apache2/.htdigest
   ```
2. Criar a pasta de dados, copiar as senhas atuais e definir o primeiro admin (troque `caio` pelo seu usuário, escrito igual ao do passo 1):
   ```sh
   sudo install -d -o www-data -g www-data -m 750 /var/lib/champlive
   sudo install -o www-data -g www-data -m 640 /etc/apache2/.htdigest /var/lib/champlive/htdigest
   echo caio | sudo install -o www-data -g www-data -m 640 /dev/stdin /var/lib/champlive/admins
   ```
3. Ativar o CGI no Apache: `sudo a2enmod cgid`
4. Em `/etc/apache2/sites-enabled/000-default-le-ssl.conf`, trocar o `AuthUserFile` para `/var/lib/champlive/htdigest` e colar o bloco do `ScriptAlias /api/usuarios` de `server/apache-champlive.conf`, usando o realm real no `AuthName` e no `CHAMPLIVE_REALM`.
5. Conferir e recarregar:
   ```sh
   sudo apache2ctl configtest && sudo systemctl reload apache2
   ```
6. Se o deploy ainda não instalou o CGI, rode o workflow "Deploy no servidor" pela aba Actions. Depois abra https://champbr.com/admin.html.

O arquivo antigo `/etc/apache2/.htdigest` fica como backup e deixa de ser usado.
