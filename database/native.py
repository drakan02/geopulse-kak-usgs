"""Portable PostgreSQL/TimescaleDB for Windows; no Windows service is installed."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

HERE = Path(__file__).resolve().parent
LOCAL = HERE / '.local'
PG = LOCAL / 'pgsql'
DATA = LOCAL / 'pgdata'
CONFIG = LOCAL / 'credentials.json'
PACKAGES = LOCAL / 'packages'
SOURCES = {
    'postgresql-17.11.zip': 'https://get.enterprisedb.com/postgresql/postgresql-17.11-1-windows-x64-binaries.zip',
    'timescaledb-2.30.2.zip': 'https://github.com/timescale/timescaledb/releases/download/2.30.2/timescaledb-postgresql-17-windows-amd64.zip',
}


def run(command, env=None, capture=False):
    # pg_ctl starts a background server. A file avoids inherited pipe handles
    # keeping communicate() blocked after pg_ctl itself has already exited.
    output = ''
    with tempfile.TemporaryFile() as log:
        result = subprocess.run(command, env=env,
            stdout=log if capture else None, stderr=log if capture else None,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        if capture:
            log.seek(0)
            output=log.read().decode('utf-8',errors='replace')
    if result.returncode:
        if capture:
            print(output, file=sys.stderr)
        raise RuntimeError(f'Command failed: {Path(command[0]).name} (exit {result.returncode})')
    if capture and output.strip():
        print(output.strip())
    return result


def load_config():
    if not CONFIG.is_file():
        raise RuntimeError('Run windows-native.ps1 setup first.')
    return json.loads(CONFIG.read_text(encoding='utf-8'))


def environment(config):
    env = os.environ.copy()
    env.update(PGHOST='127.0.0.1', PGPORT=str(config['port']), PGUSER='geopulse',
        PGPASSWORD=config['admin_password'], PGDATABASE='geopulse',
        PG_READER_PASSWORD=config['reader_password'], PYTHONPATH=str(PACKAGES))
    # PostgreSQL can resolve its own bundled dependency DLLs.
    env['PATH'] = str(PG / 'bin') + os.pathsep + env.get('PATH','')
    return env


def setup(downloads_dir=None):
    if os.name != 'nt':
        raise RuntimeError('Native helper is for Windows; use Compose on Linux/macOS.')
    if sys.version_info < (3,10):
        raise RuntimeError('Python 3.10 or newer is required.')
    if CONFIG.is_file() and (DATA/'PG_VERSION').is_file() and (PG/'bin/postgres.exe').is_file():
        print('Using existing project-local runtime; preserving binaries and data.')
        start(load_config())
        return
    LOCAL.mkdir(exist_ok=True)
    downloads = downloads_dir or LOCAL / 'downloads'
    downloads.mkdir(parents=True, exist_ok=True)
    for filename, url in SOURCES.items():
        path = downloads / filename
        if not path.is_file():
            print(f'Downloading official package: {filename}', flush=True)
            urllib.request.urlretrieve(url,path)
        # Only install to this project-local runtime; never run an installer exe.
        with zipfile.ZipFile(path) as archive:
            for entry in archive.infolist():
                if entry.is_dir():
                    continue
                parts = Path(entry.filename).parts
                if filename.startswith('postgresql'):
                    if not (entry.filename.startswith(('pgsql/bin/','pgsql/lib/','pgsql/share/')) or entry.filename == 'pgsql/server_license.txt'):
                        continue
                    destination = LOCAL / entry.filename
                else:
                    basename = Path(entry.filename).name
                    if basename.endswith('.dll'):
                        destination = PG / 'lib' / basename
                    elif basename.endswith(('.sql','.control')):
                        destination = PG / 'share' / 'extension' / basename
                    else:
                        continue
                if '..' in parts or not destination.resolve().is_relative_to(LOCAL.resolve()):
                    raise RuntimeError('Unexpected archive path')
                destination.parent.mkdir(parents=True,exist_ok=True)
                with archive.open(entry) as source, destination.open('wb') as target:
                    shutil.copyfileobj(source,target)
    run([sys.executable,'-m','pip','install','--target',str(PACKAGES),'-r',str(HERE/'requirements.txt')])
    if not CONFIG.is_file():
        config={'python':sys.executable,'port':5433,'admin_password':secrets.token_hex(32),'reader_password':secrets.token_hex(32)}
        CONFIG.write_text(json.dumps(config,indent=2),encoding='utf-8')
    config=load_config()
    config['python']=sys.executable
    CONFIG.write_text(json.dumps(config,indent=2),encoding='utf-8')
    if not (DATA/'PG_VERSION').is_file():
        password_file=LOCAL/'init-password.txt'
        password_file.write_text(config['admin_password'],encoding='utf-8')
        try:
            run([str(PG/'bin/initdb.exe'),'-D',str(DATA),'-U','geopulse','-A','scram-sha-256',
                 '--pwfile',str(password_file),'--encoding=UTF8','--locale=C'],capture=True)
        finally:
            password_file.unlink(missing_ok=True)
        with (DATA/'postgresql.conf').open('a',encoding='utf-8') as out:
            out.write("\n# GeoPulse project-local settings\nlisten_addresses='127.0.0.1'\nport=5433\n"
                "timezone='UTC'\nshared_preload_libraries='timescaledb'\nshared_buffers='256MB'\nwork_mem='16MB'\n"
                "max_worker_processes=16\nmax_parallel_workers=4\ntimescaledb.max_background_workers=8\n"
                "timescaledb.telemetry_level='off'\n")
    print('Portable runtime ready. Local credentials are in database/.local/credentials.json.')
    start(config)


def is_running(config):
    result=subprocess.run([str(PG/'bin/pg_ctl.exe'),'status','-D',str(DATA)],
        env=environment(config),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    return result.returncode==0


def cli(action, config):
    command=[config['python'],str(HERE/'cli.py'),'--data-dir',str(HERE.parent/'data/clean'),
             '--report-dir',str(HERE/'reports'),action]
    if action=='verify':
        command+=['--full']
    if action=='archive-raw':
        command+=['--raw-dir',str(HERE.parent/'data/raw')]
    run(command,env=environment(config),capture=True)


def start(config):
    if not is_running(config):
        with socket.socket() as probe:
            try:
                probe.bind(('127.0.0.1',config['port']))
            except OSError:
                raise RuntimeError('Port 5433 is in use. Stop the other instance before starting this runtime.')
        run([str(PG/'bin/pg_ctl.exe'),'start','-D',str(DATA),'-l',str(LOCAL/'postgresql.log'),'-w','-t','60'],env=environment(config),capture=True)
    sys.path.insert(0,str(PACKAGES))
    import psycopg
    from psycopg import sql
    with psycopg.connect(host='127.0.0.1',port=config['port'],user='geopulse',password=config['admin_password'],dbname='postgres',autocommit=True) as conn:
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname='geopulse'").fetchone():
            conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier('geopulse')))
    cli('init',config)
    print('Database: localhost:5433 / geopulse. Reader account: geopulse_reader.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['setup','start','stop','status','inspect','import','verify','benchmark','refresh','archive-raw','test'])
    parser.add_argument('--downloads-dir',type=Path)
    args=parser.parse_args()
    if args.action=='setup':
        setup(args.downloads_dir)
        return
    config=load_config()
    if args.action=='start':
        start(config)
    elif args.action=='stop':
        if is_running(config):
            run([str(PG/'bin/pg_ctl.exe'),'stop','-D',str(DATA),'-m','fast','-w'],env=environment(config),capture=True)
        else:
            print('Database is already stopped. Data is preserved.')
    elif args.action=='status':
        print('Running: localhost:5433/geopulse' if is_running(config) else 'Stopped; run start.')
    else:
        if args.action!='inspect' and not is_running(config):
            raise RuntimeError('Database is stopped; run start first.')
        cli(args.action,config)


if __name__=='__main__':
    try:
        main()
    except (RuntimeError,OSError,zipfile.BadZipFile) as error:
        print(f'Native runtime: {error}',file=sys.stderr)
        sys.exit(1)
