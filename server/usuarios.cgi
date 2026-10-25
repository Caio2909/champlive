#!/usr/bin/python3
# API do painel de usuários (/api/usuarios), rodando como CGI no Apache.
#
# O Apache já autenticou a pessoa pela senha Digest e passa o nome em
# REMOTE_USER. Este script só edita dois arquivos:
#   htdigest  usuários e senhas (o mesmo arquivo do AuthUserFile)
#   admins    nomes dos admins, um por linha
# Só usa a biblioteca padrão do Python 3.
#
# GET  /api/usuarios  -> {"eu": "caio", "admin": true, "usuarios": [{"nome", "admin"}]}
#                        (quem não é admin recebe só o próprio nome em "usuarios")
# POST /api/usuarios  com JSON {"acao": ..., "nome": ..., ...}
#   criar   {nome, senha, admin?}  só admin
#   excluir {nome}                 só admin
#   senha   {nome, senha}          admin muda qualquer uma; os outros só a própria
#   admin   {nome, admin: bool}    só admin

import fcntl
import hashlib
import json
import os
import re
import sys
import tempfile

PASTA = os.environ.get('CHAMPLIVE_DADOS', '/var/lib/champlive')
ARQ_SENHAS = os.path.join(PASTA, 'htdigest')
ARQ_ADMINS = os.path.join(PASTA, 'admins')
ARQ_TRAVA = os.path.join(PASTA, '.trava')

NOME_VALIDO = re.compile(r'^[A-Za-z0-9._-]{1,32}$')
SENHA_MINIMA = 6


class Erro(Exception):
    def __init__(self, status, mensagem):
        super().__init__(mensagem)
        self.status = status
        self.mensagem = mensagem


def responder(status, dados):
    corpo = json.dumps(dados, ensure_ascii=False).encode('utf-8')
    sys.stdout.write('Status: %s\r\n' % status)
    sys.stdout.write('Content-Type: application/json; charset=utf-8\r\n')
    sys.stdout.write('Cache-Control: no-store\r\n')
    sys.stdout.write('Content-Length: %d\r\n\r\n' % len(corpo))
    sys.stdout.flush()
    sys.stdout.buffer.write(corpo)


def ler_linhas(caminho):
    try:
        with open(caminho, encoding='utf-8') as f:
            return [l.rstrip('\n') for l in f if l.strip()]
    except FileNotFoundError:
        return []


def gravar_linhas(caminho, linhas):
    # Grava num temporário e renomeia: o Apache nunca lê um arquivo pela metade
    fd, tmp = tempfile.mkstemp(dir=PASTA, prefix='.tmp-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(''.join(l + '\n' for l in linhas))
        os.chmod(tmp, 0o640)
        os.replace(tmp, caminho)
    except BaseException:
        os.unlink(tmp)
        raise


def ler_senhas():
    # Linhas do htdigest: usuario:realm:md5(usuario:realm:senha)
    usuarios = {}
    for linha in ler_linhas(ARQ_SENHAS):
        partes = linha.split(':')
        if len(partes) == 3:
            usuarios[partes[0]] = (partes[1], partes[2])
    return usuarios


def realm_atual(usuarios):
    realm = os.environ.get('CHAMPLIVE_REALM')
    if realm:
        return realm
    for r, _ in usuarios.values():
        return r
    raise Erro(500, 'Realm desconhecido: defina CHAMPLIVE_REALM no Apache.')


def gravar_senhas(usuarios):
    gravar_linhas(ARQ_SENHAS, ['%s:%s:%s' % (n, r, h) for n, (r, h) in sorted(usuarios.items())])


def hash_digest(nome, realm, senha):
    return hashlib.md5(('%s:%s:%s' % (nome, realm, senha)).encode('utf-8')).hexdigest()


def ler_admins():
    return set(ler_linhas(ARQ_ADMINS))


def gravar_admins(admins):
    gravar_linhas(ARQ_ADMINS, sorted(admins))


def validar_nome(nome):
    if not isinstance(nome, str) or not NOME_VALIDO.match(nome):
        raise Erro(400, 'Nome inválido: use de 1 a 32 letras, números, ponto, hífen ou _.')
    return nome


def validar_senha(senha):
    if not isinstance(senha, str) or len(senha) < SENHA_MINIMA:
        raise Erro(400, 'A senha precisa ter pelo menos %d caracteres.' % SENHA_MINIMA)
    if ':' in senha or '\n' in senha:
        raise Erro(400, 'A senha não pode ter ":" nem quebra de linha.')
    return senha


def listar(eu):
    usuarios = ler_senhas()
    admins = ler_admins()
    souAdmin = eu in admins
    nomes = sorted(usuarios, key=str.lower) if souAdmin else [eu]
    return {
        'eu': eu,
        'admin': souAdmin,
        'usuarios': [{'nome': n, 'admin': n in admins} for n in nomes],
    }


def executar(eu, pedido):
    acao = pedido.get('acao')
    nome = validar_nome(pedido.get('nome'))
    usuarios = ler_senhas()
    admins = ler_admins()
    souAdmin = eu in admins

    if acao == 'senha':
        if not souAdmin and nome != eu:
            raise Erro(403, 'Só admins podem mudar a senha de outra pessoa.')
        if nome not in usuarios:
            raise Erro(404, 'Usuário não encontrado.')
        realm = usuarios[nome][0]
        usuarios[nome] = (realm, hash_digest(nome, realm, validar_senha(pedido.get('senha'))))
        gravar_senhas(usuarios)
        return

    if not souAdmin:
        raise Erro(403, 'Só admins podem fazer isso.')

    if acao == 'criar':
        if nome in usuarios:
            raise Erro(409, 'Já existe um usuário com esse nome.')
        realm = realm_atual(usuarios)
        usuarios[nome] = (realm, hash_digest(nome, realm, validar_senha(pedido.get('senha'))))
        gravar_senhas(usuarios)
        if pedido.get('admin') is True:
            admins.add(nome)
            gravar_admins(admins)
    elif acao == 'excluir':
        if nome == eu:
            raise Erro(400, 'Você não pode excluir o próprio usuário.')
        if nome not in usuarios:
            raise Erro(404, 'Usuário não encontrado.')
        del usuarios[nome]
        gravar_senhas(usuarios)
        if nome in admins:
            admins.discard(nome)
            gravar_admins(admins)
    elif acao == 'admin':
        tornar = pedido.get('admin')
        if not isinstance(tornar, bool):
            raise Erro(400, 'Campo "admin" precisa ser true ou false.')
        if nome not in usuarios:
            raise Erro(404, 'Usuário não encontrado.')
        if not tornar and nome == eu:
            raise Erro(400, 'Você não pode tirar o próprio admin.')
        if tornar:
            admins.add(nome)
        else:
            admins.discard(nome)
        gravar_admins(admins)
    else:
        raise Erro(400, 'Ação desconhecida.')


def principal():
    eu = os.environ.get('REMOTE_USER', '')
    if not eu:
        raise Erro(401, 'Sem usuário autenticado (a senha Digest não está ativa nesta rota?).')

    metodo = os.environ.get('REQUEST_METHOD', 'GET')
    if metodo == 'GET':
        responder('200 OK', listar(eu))
        return
    if metodo != 'POST':
        raise Erro(405, 'Método não permitido.')

    # Proteção contra CSRF: o navegador manda a senha Digest sozinho, então
    # exigimos JSON + cabeçalho próprio (um site de fora não consegue mandar
    # isso sem preflight de CORS) e, se vier Origin, que seja o próprio site.
    if not os.environ.get('CONTENT_TYPE', '').startswith('application/json'):
        raise Erro(415, 'Envie JSON.')
    if os.environ.get('HTTP_X_CHAMPLIVE') != '1':
        raise Erro(403, 'Cabeçalho X-ChampLive ausente.')
    origem = os.environ.get('HTTP_ORIGIN')
    if origem and origem != 'https://' + os.environ.get('HTTP_HOST', ''):
        raise Erro(403, 'Origem não permitida.')

    try:
        tamanho = min(int(os.environ.get('CONTENT_LENGTH') or 0), 10000)
        pedido = json.loads(sys.stdin.buffer.read(tamanho) or b'{}')
    except ValueError:
        raise Erro(400, 'JSON inválido.')
    if not isinstance(pedido, dict):
        raise Erro(400, 'JSON inválido.')

    with open(ARQ_TRAVA, 'a') as trava:
        fcntl.flock(trava, fcntl.LOCK_EX)
        executar(eu, pedido)
        resposta = listar(eu)
    responder('200 OK', resposta)


if __name__ == '__main__':
    try:
        principal()
    except Erro as e:
        responder('%d Erro' % e.status, {'erro': e.mensagem})
    except Exception as e:
        print('usuarios.cgi: %r' % e, file=sys.stderr)
        responder('500 Erro', {'erro': 'Erro interno no servidor.'})
