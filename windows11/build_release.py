"""Builds public v11 installers from hash-pinned public v10 runtimes."""
from pathlib import Path
import os,sys,hashlib,json,urllib.request,subprocess,shutil,winreg
ROOT=Path(__file__).resolve().parents[1];SRC=ROOT/'windows11';BUILD=ROOT/'build11';OUT=ROOT/'out';BUILD.mkdir(exist_ok=True);OUT.mkdir(exist_ok=True)
manifest=json.loads((SRC/'source_sha256.json').read_text(encoding='utf-8'))
inno=Path('C:/Program Files (x86)/Inno Setup 6/ISCC.exe');assert inno.exists()
compiler=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
bases=[('Principal','01_PRINCIPAL','1a671d19a6786d300fada5494a5dea4f6eb6d5ef2ea094fc264b2ee9662adab7'),('Cliente','02_CLIENTE','1a866a2e59e4faf7b80c057a95692c389c6943091c051da4e96ff93015244ea5')]
reports=[]
for kind,folder,expected in bases:
    base=BUILD/f'base_{kind}.exe';url=f'https://github.com/sbarria1209-droid/MODIX-Descargas/releases/download/v10.0.0/MODIX_{kind}_10_Instalador.exe'
    urllib.request.urlretrieve(url,base);assert hashlib.sha256(base.read_bytes()).hexdigest()==expected,'Base checksum mismatch'
    target=BUILD/folder
    subprocess.run([str(base),'/MODIX_QA=1','/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-','/NOICONS','/TASKS=','/DIR='+str(target)],check=True,timeout=360)
    shutil.copytree(SRC/'source'/folder,target,dirs_exist_ok=True)
    for relative,digest in manifest.items():
        if relative.startswith(folder+'/'):assert hashlib.sha256((target/Path(relative).name).read_bytes()).hexdigest()==digest,relative
    # No station secrets or camera calibration can enter the public payload.
    for name in ('bridge.json','estacion_privada.json','estacion_privada.dat','multicam11.json'):assert not (target/name).exists(),name
    subprocess.run([str(compiler),'/nologo','/target:winexe','/optimize+','/reference:System.Windows.Forms.dll','/win32icon:'+str(target/'modix.ico'),'/out:'+str(target/f'MODIX_{kind}_11.exe'),str(target/'launcher.cs')],check=True)
    spec=(SRC/'specs'/f'{kind}.iss').read_text(encoding='utf-8-sig').replace('@SOURCE@',str(target)).replace('@OUTPUT@',str(OUT)).replace('@DOCS@',str(SRC/'docs'))
    # station_config is the already-sanitized v10 file from the public base.
    docs=BUILD/f'docs_{kind}';shutil.copytree(SRC/'docs',docs,dirs_exist_ok=True)
    if kind=='Principal':shutil.copy2(target/'station_config.py',docs/'station_config.py')
    spec=spec.replace(str(SRC/'docs'),str(docs));iss=BUILD/f'{kind}.iss';iss.write_text(spec,encoding='utf-8-sig');subprocess.run([str(inno),str(iss)],check=True,timeout=600)
    artifact=OUT/f'MODIX_{kind}_11_Instalador.exe';assert artifact.exists()
    # Install the exact final artifact into a separate slot and verify its payload.
    verified=BUILD/f'qa_{kind}';subprocess.run([str(artifact),'/MODIX_QA=1','/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-','/NOICONS','/TASKS=','/DIR='+str(verified)],check=True,timeout=360)
    for relative,digest in manifest.items():
        if relative.startswith(folder+'/'):assert hashlib.sha256((verified/Path(relative).name).read_bytes()).hexdigest()==digest,relative
    for name in ('bridge.json','estacion_privada.json','estacion_privada.dat','multicam11.json'):assert not (verified/name).exists(),name
    assert not any((verified/'_obs/config').rglob('*.*'))
    env={**os.environ,'MODIX_AUTOTEST':'1','MODIX_DATA_DIR':str(BUILD/f'data_{kind}'),'MODIX_CLIENT_DATA_DIR':str(BUILD/f'client_{kind}'),'MODIX_LOG_DIR':str(BUILD/f'logs_{kind}'),'PYTHONHOME':'C:/inexistente','PYTHONPATH':'C:/inexistente'};Path(env['MODIX_LOG_DIR']).mkdir(exist_ok=True)
    subprocess.run([str(verified/f'MODIX_{kind}_11.exe'),'--smoke'],env=env,check=True,timeout=90)
    reports.append({'app':kind,'file':artifact.name,'bytes':artifact.stat().st_size,'sha256':hashlib.sha256(artifact.read_bytes()).hexdigest(),'source_hashes_match':True,'exact_installer_smoke_passed':True});print(json.dumps(reports[-1]),flush=True)
for name in ('LEEME_PRIMERO.md','VERIFICACIONES.md'):shutil.copy2(SRC/'docs'/name,OUT/name)
(OUT/'MODIX_11_SHA256.txt').write_text(''.join(r['sha256']+'  '+r['file']+'\n' for r in reports),encoding='utf-8');(OUT/'BUILD_VERIFICADO.json').write_text(json.dumps(reports,indent=2),encoding='utf-8')
