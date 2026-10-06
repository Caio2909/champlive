# ChampLive

Servidor próprio de transmissão de tela para assistir lives entre amigos, criado como alternativa ao Go Live do Discord. Roda em uma VPS Oracle Cloud com MediaMTX e Apache, acessível em https://champlive.duckdns.org.

## O que tem

- Player WebRTC de baixa latência, com menu das lives ativas e contador de viewers em tempo real
- Transmissão Rápida pelo navegador (`getDisplayMedia`), sem precisar do OBS
- Transmissão pelo OBS via RTMP
- Acesso protegido por senha (Digest) e HTTPS (Let's Encrypt)

## Estrutura

```
site/index.html                 página única (player + transmissão rápida)
server/apache-champlive.conf    proxies e senha do Apache
server/mediamtx-ajustes.yml     chaves alteradas no mediamtx.yml
server/mediamtx.service         serviço systemd do MediaMTX
.github/workflows/deploy.yml    deploy automático no servidor
```

## Transmitir pelo OBS

- Servidor: `rtmp://144.22.199.64:1935/live`
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
